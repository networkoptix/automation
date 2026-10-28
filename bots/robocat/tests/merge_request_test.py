## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import http
import json
import urllib.parse
from typing import Any
from unittest.mock import MagicMock

import gitlab
import pytest
import requests
from automation_tools.tests.gitlab_constants import BOT_USERNAME
from gitlab.exceptions import GitlabHttpError, GitlabMRRebaseError
from gitlab.v4.objects import ProjectMergeRequest
from requests.adapters import BaseAdapter
from robocat.comments import Comment, Emoji
from robocat.merge_request import MergeRequest
from robocat.merge_request_manager import MergeRequestManager
from robocat.note import NoteDetails

MERGE_REQUEST_DATA = {  # The fields of the merge request GET that the tests read.
    "iid": 5,
    "title": "VMS-1: Fix the bug",
    "author": {"username": "developer", "name": "Developer"},
    "sha": "0123456789abcdef0123456789abcdef01234567",
}
APPROVAL_ANSWER = {  # GitLab answers approve and unapprove with the approval state only.
    "iid": 5,
    "title": "VMS-1: Fix the bug",
    "approvals_left": 0,
    "approved_by": [],
}
GITLAB_URL = "https://gitlab.example.com"
MERGE_REQUEST_PATH = "/projects/1/merge_requests/5"
OPEN_MERGE_REQUEST_DATA = {  # The fields that the rebase and merge code reads.
    **MERGE_REQUEST_DATA,
    "project_id": 1,
    "state": "opened",
    "detailed_merge_status": "mergeable",
}
PUSHED_SHA = "fedcba9876543210fedcba9876543210fedcba98"  # The MR head after a new push.
FORBIDDEN_REBASE = "403 Forbidden - Cannot push to source branch"  # GitLab's text (nx!41328).
MISSING_BRANCH_REBASE = "403 Forbidden - Source branch does not exist"  # RebaseService.validate.
PROTECTED_BRANCH_REBASE = "403 Forbidden - Source branch is protected from force push"  # Same.
LOCKED_REBASE = "409 Conflict: Resource lock"  # GitLab's text (nx!41278).
REJECTED_MERGE = "400 Bad request - Failed to merge"  # GitLab's text (cloud_portal!11053).


class TestApprovalKeepsMergeRequestData:
    """python-gitlab replaces the MR data with the approval answer: Robocat must keep its data."""

    @pytest.fixture
    def merge_request(self, monkeypatch) -> MergeRequest:
        """An MR of the real python-gitlab classes; only the GitLab server is fake."""
        raw_gitlab = gitlab.Gitlab("https://gitlab.example.com", private_token="token")
        monkeypatch.setattr(raw_gitlab, "http_post", lambda *_, **__: dict(APPROVAL_ANSWER))
        monkeypatch.setattr(  # Robocat must not need to read the MR again.
            raw_gitlab, "http_get", MagicMock(side_effect=AssertionError("Unexpected GET")))
        monkeypatch.setattr(raw_gitlab, "http_list", lambda *_, **__: [])  # No discussions.
        manager = raw_gitlab.projects.get(1, lazy=True).mergerequests
        return MergeRequest(ProjectMergeRequest(manager, dict(MERGE_REQUEST_DATA)), BOT_USERNAME)

    @pytest.mark.parametrize("action", ["ensure_approve", "ensure_unapprove"])
    def test_merge_request_data_stays(self, merge_request, action):
        """After a successful approve or unapprove, the MR author and commit are still known."""
        assert getattr(merge_request, action)() is True

        assert merge_request.author.username == "developer"
        assert merge_request.sha == MERGE_REQUEST_DATA["sha"]


def mock_gitlab_response(
        request: requests.PreparedRequest, status: int, body: Any) -> requests.Response:
    """A GitLab HTTP answer: the status and a JSON body (no body for None)."""
    response = requests.Response()
    response.status_code = status
    response.reason = http.HTTPStatus(status).phrase
    response._content = b"" if body is None else json.dumps(body).encode()
    response.headers["Content-Type"] = "application/json"
    response.url = str(request.url)
    response.request = request
    return response


class FakeGitLabServer(BaseAdapter):
    """A fake GitLab server under a real requests session: python-gitlab and Robocat stay real."""

    def __init__(self, answers: dict[tuple[str, str], tuple[int, Any]]) -> None:
        """Keep the fixed answers by (method, path); notes and award emoji change as on GitLab."""
        super().__init__()
        self.answers = answers
        self.notes: list[dict[str, Any]] = []
        self.award_emoji: list[dict[str, Any]] = [{  # Robocat sets it before it merges.
            "id": 7, "name": Emoji.UNFINISHED_POST_MERGING, "user": {"username": BOT_USERNAME}}]
        self.calls: list[tuple[str, str]] = []

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        """Answer one request like GitLab; fail the test on a request it does not expect."""
        method = str(request.method)
        path = urllib.parse.urlsplit(str(request.url)).path.removeprefix("/api/v4")
        self.calls.append((method, path))
        if (method, path) == ("GET", f"{MERGE_REQUEST_PATH}/discussions"):
            return mock_gitlab_response(request, 200, [
                {"id": f"discussion-{note['id']}", "individual_note": True, "notes": [note]}
                for note in self.notes])
        if (method, path) == ("POST", f"{MERGE_REQUEST_PATH}/notes"):
            sent = request.body
            assert isinstance(sent, bytes | str), f"Unexpected note request body: {sent!r}"
            note = {
                "id": len(self.notes) + 1,
                "body": json.loads(sent)["body"],
                "author": {"username": BOT_USERNAME},
                "created_at": f"2026-10-28T12:00:{len(self.notes):02d}.000Z",
                "system": False,
            }
            self.notes.append(note)
            return mock_gitlab_response(request, 201, note)
        if (method, path) == ("GET", f"{MERGE_REQUEST_PATH}/award_emoji"):
            return mock_gitlab_response(request, 200, self.award_emoji)
        if method == "DELETE" and path.startswith(f"{MERGE_REQUEST_PATH}/award_emoji/"):
            emoji_id = int(path.rsplit("/", 1)[1])
            self.award_emoji = [emoji for emoji in self.award_emoji if emoji["id"] != emoji_id]
            return mock_gitlab_response(request, 204, None)
        if (method, path) not in self.answers:
            raise AssertionError(f"Unexpected GitLab request: {method} {path}")
        status, body = self.answers[(method, path)]
        return mock_gitlab_response(request, status, body)

    def close(self):
        """Nothing to close."""


def merge_request_manager(
        server: FakeGitLabServer,
        merge_request_data: dict[str, Any] = OPEN_MERGE_REQUEST_DATA) -> MergeRequestManager:
    """An MR manager of the real classes that talks to the fake GitLab server."""
    session = requests.Session()
    session.mount(GITLAB_URL, server)
    raw_gitlab = gitlab.Gitlab(GITLAB_URL, private_token="token", session=session)
    gitlab_merge_requests = raw_gitlab.projects.get(1, lazy=True).mergerequests
    merge_request = MergeRequest(
        ProjectMergeRequest(gitlab_merge_requests, dict(merge_request_data)), BOT_USERNAME)
    return MergeRequestManager(merge_request, BOT_USERNAME)


def posted_comments(server: FakeGitLabServer) -> list[Comment | None]:
    """The comments of the posted notes, read the way Robocat reads them."""
    return [NoteDetails.create_from_text(note["body"]).message_id for note in server.notes]


class TestRebaseRefusedByGitLab:
    """GitLab refuses the rebase of an MR that is behind its target branch."""

    @staticmethod
    def server(status: int, message: str) -> FakeGitLabServer:
        """A GitLab where the MR is behind and the rebase gets this answer."""
        return FakeGitLabServer({
            ("GET", MERGE_REQUEST_PATH): (200, {**OPEN_MERGE_REQUEST_DATA,
                                                "diverged_commits_count": 2}),
            ("PUT", f"{MERGE_REQUEST_PATH}/rebase"): (status, {"message": message}),
        })

    def test_forbidden_rebase_is_explained_once_per_commit(self):
        """A 403 (fork without member access) gets one comment with GitLab's reason, no crash."""
        server = self.server(403, FORBIDDEN_REBASE)
        manager = merge_request_manager(server)

        assert manager.ensure_rebase() is True  # Robocat waits: the author must act.
        assert manager.ensure_rebase() is True  # The next event, same commit.

        assert server.calls.count(("PUT", f"{MERGE_REQUEST_PATH}/rebase")) == 2
        assert posted_comments(server) == [Comment.RebaseRejectedCannotPush]
        body = server.notes[0]["body"]
        assert f"GitLab refused to rebase this Merge Request: {FORBIDDEN_REBASE}." in body
        assert f"Sha: {OPEN_MERGE_REQUEST_DATA['sha']}" in body

    def test_forbidden_rebase_is_explained_again_after_a_push(self):
        """A push makes a new MR head; GitLab refuses its rebase too: one more comment."""
        server = self.server(403, FORBIDDEN_REBASE)
        merge_request_manager(server).ensure_rebase()
        pushed_data = {**OPEN_MERGE_REQUEST_DATA, "sha": PUSHED_SHA}
        server.answers[("GET", MERGE_REQUEST_PATH)] = (200, {**pushed_data,
                                                             "diverged_commits_count": 2})
        pushed = merge_request_manager(server, pushed_data)  # The event of the push.

        assert pushed.ensure_rebase() is True
        assert pushed.ensure_rebase() is True  # The next event, same new commit.

        assert posted_comments(server) == [
            Comment.RebaseRejectedCannotPush, Comment.RebaseRejectedCannotPush]
        assert f"Sha: {PUSHED_SHA}" in server.notes[1]["body"]

    def test_forbidden_rebase_before_the_merge_is_explained(self):
        """The rebase in prepare_to_merge() gets the same comment, no crash."""
        server = self.server(403, FORBIDDEN_REBASE)
        manager = merge_request_manager(server, {
            **OPEN_MERGE_REQUEST_DATA, "squash": False, "detailed_merge_status": "need_rebase"})

        assert manager.prepare_to_merge(repo=MagicMock()) is False  # Robocat does not merge.

        assert posted_comments(server) == [Comment.RebaseRejectedCannotPush]

    @pytest.mark.parametrize(("message", "comment", "asks_for_process"), [
        (MISSING_BRANCH_REBASE, Comment.RebaseRejectedSourceBranchMissing, False),
        (FORBIDDEN_REBASE, Comment.RebaseRejectedCannotPush, True),
        (PROTECTED_BRANCH_REBASE, Comment.RebaseRejectedForcePushProtected, True),
    ])
    def test_each_forbidden_reason_gets_its_own_comment(self, message, comment, asks_for_process):
        """GitLab sends one reason per 403: Robocat posts the comment with the fix for it."""
        server = self.server(403, message)

        merge_request_manager(server).ensure_rebase()

        assert posted_comments(server) == [comment]
        body = server.notes[0]["body"]
        assert f"GitLab refused to rebase this Merge Request: {message}." in body
        assert "Robocat tries again after the push." in body
        assert (f"`@{BOT_USERNAME} process`" in body) is asks_for_process  # A setting needs it.

    def test_new_reason_on_the_same_commit_gets_a_new_comment(self):
        """The author fixes one reason in the settings, with no push; GitLab sends the next one."""
        server = self.server(403, FORBIDDEN_REBASE)
        manager = merge_request_manager(server)
        manager.ensure_rebase()
        server.answers[("PUT", f"{MERGE_REQUEST_PATH}/rebase")] = (
            403, {"message": PROTECTED_BRANCH_REBASE})

        manager.ensure_rebase()
        manager.ensure_rebase()  # The next event, same commit and reason.

        assert posted_comments(server) == [
            Comment.RebaseRejectedCannotPush, Comment.RebaseRejectedForcePushProtected]

    def test_forbidden_rebase_with_unknown_reason_asks_for_a_manual_rebase(self):
        """A 403 text that Robocat does not know gets GitLab's text and the manual rebase."""
        server = self.server(403, "403 Forbidden")

        merge_request_manager(server).ensure_rebase()

        assert posted_comments(server) == [Comment.RebaseRejected]
        body = server.notes[0]["body"]
        assert "GitLab refused to rebase this Merge Request: 403 Forbidden." in body
        assert "To fix it, rebase the branch yourself." in body
        assert f"`@{BOT_USERNAME} process`" not in body

    def test_locked_rebase_posts_nothing(self):
        """A 409 "Resource lock" means GitLab is busy: no comment, no crash, wait."""
        server = self.server(409, LOCKED_REBASE)
        manager = merge_request_manager(server)

        assert manager.ensure_rebase() is True
        assert manager.rebase_in_progress
        assert server.notes == []

    def test_other_rebase_error_is_raised(self):
        """Any other answer, e.g. a server error, stays an exception."""
        server = self.server(500, "500 Internal Server Error")
        manager = merge_request_manager(server)

        with pytest.raises(GitlabMRRebaseError) as error:
            manager.ensure_rebase()
        assert error.value.response_code == 500
        assert server.notes == []


class TestMergeRejectedByGitLab:
    """GitLab refuses to add the MR to the merge train."""

    @staticmethod
    def server(status: int, message: str) -> FakeGitLabServer:
        """A GitLab with merge trains where adding the MR gets this answer."""
        return FakeGitLabServer({
            ("GET", "/projects/1"): (200, {"id": 1, "merge_trains_enabled": True}),
            ("POST", "/projects/1/merge_trains/merge_requests/5"): (status, {"message": message}),
        })

    def test_rejected_merge_is_explained_once_per_commit(self):
        """A 400 gets one comment with GitLab's reason; the unfinished post-merge flag goes."""
        server = self.server(400, REJECTED_MERGE)
        manager = merge_request_manager(server)

        assert manager.merge() is False
        assert manager.merge() is False  # The next event, same commit.

        assert len(server.notes) == 1
        body = server.notes[0]["body"]
        assert f"Message Id: {Comment.MergeRejected.name}" in body
        assert f"GitLab refused to merge this Merge Request: {REJECTED_MERGE}." in body
        assert f"`@{BOT_USERNAME} process`" in body
        assert server.award_emoji == []  # Nothing was merged: no post-merge work is left.

    def test_rejected_merge_is_explained_again_after_a_push(self):
        """A push makes a new MR head; GitLab rejects its merge too: one more comment."""
        server = self.server(400, REJECTED_MERGE)
        merge_request_manager(server).merge()
        pushed = merge_request_manager(  # The event of the push.
            server, {**OPEN_MERGE_REQUEST_DATA, "sha": PUSHED_SHA})

        assert pushed.merge() is False
        assert pushed.merge() is False  # The next event, same new commit.

        assert posted_comments(server) == [Comment.MergeRejected, Comment.MergeRejected]
        assert f"Sha: {PUSHED_SHA}" in server.notes[1]["body"]

    @pytest.mark.parametrize(("status", "message"), [
        (403, "403 Forbidden"),
        (500, "500 Internal Server Error"),
    ])
    def test_other_merge_error_is_raised(self, status, message):
        """Any other answer, e.g. no access or a server error, stays an exception."""
        server = self.server(status, message)
        manager = merge_request_manager(server)

        with pytest.raises(GitlabHttpError) as error:
            manager.merge()
        assert error.value.response_code == status
        assert server.notes == []
