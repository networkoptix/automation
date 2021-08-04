from dataclasses import dataclass, field
from datetime import datetime
from functools import namedtuple
from typing import Any
import time
import uuid

from gitlab.exceptions import GitlabMRClosedError

from automation_tools.tests.mocks.git_mocks import BOT_USERNAME
from tests.mocks.gitlab import GitlabManagerMock
from tests.mocks.pipeline import PipelineMock
from tests.mocks.commit import CommitMock
from tests.robocat_constants import (
    DEFAULT_COMMIT, DEFAULT_PROJECT_ID, USERS, DEFAULT_REQUIRED_APPROVALS_COUNT)

DEFAULT_APPROVERS_NUMBER = 2


@dataclass
class AwardEmojiManagerMock:
    emojis: set = field(default_factory=dict)
    username: str = BOT_USERNAME

    AwardEmojiMock = namedtuple("Emoji", ["name", "id", "user"])

    def list(self, **_):
        return self.emojis.values()

    def _key(self, name):
        return f"{self.username}:{name}"

    def create(self, params, **_):
        key = self._key(params["name"])
        assert key not in self.emojis, (
            f"Emoji {params['name']} for user {self.username} already exists.")
        self.emojis[key] = self.AwardEmojiMock(
            name=params["name"], id=params["name"], user={"username": self.username})

    def delete(self, name, **_):
        key = self._key(name)
        assert key in self.emojis, f"Emoji {name} for user {self.username} doesn't exist."
        del self.emojis[key]


@dataclass
class ApprovalsMock:
    approvals_left: int = 999
    approvals_required: int = DEFAULT_REQUIRED_APPROVALS_COUNT
    approved_by: list = field(default_factory=list)


@dataclass
class ApprovalsManagerMock:
    approvals: ApprovalsMock = field(default_factory=ApprovalsMock)

    def get(self):
        return self.approvals

    def update(self, new_data):
        if "approvals_required" not in new_data:
            pass

        approvals_count_change = new_data["approvals_required"] - self.approvals.approvals_required
        self.approvals.approvals_required += approvals_count_change
        self.approvals.approvals_left = max(
            0, self.approvals.approvals_left - approvals_count_change)


@dataclass
class VersionsManagerMock:
    merge_request: Any

    @dataclass
    class VersionMock:
        head_commit_sha: str
        base_commit_sha: str
        start_commit_sha: str
        diffs: list = field(default_factory=list)
        id: int = 0

    def list(self, **_):
        return [self.VersionMock(
            head_commit_sha=self.merge_request.commits_list[-1]["sha"],
            start_commit_sha=self.merge_request.commits_list[0]["sha"],
            base_commit_sha=self.merge_request.mock_base_commit_sha)]

    def get(self, id, **_):
        files = []
        for c in self.merge_request.commits_list:
            files.extend(c["files"])
        return self.VersionMock(
            id=id,
            head_commit_sha=self.merge_request.commits_list[-1]["sha"],
            diffs=[{"new_path": f, "deleted_file": False} for f in files])


@dataclass
class NotesManagerMock:
    merge_request: Any
    notes: list = field(default_factory=list)

    def create(self, params, mock_discussion=None):
        if params["body"] == "/draft":
            self.merge_request.work_in_progress = True
            return

        note = {
            "body": params["body"],
            "created_at": datetime.now().isoformat(),
            "author": {"username": params.get("author", BOT_USERNAME)},
            "resolvable": params.get("resolvable", False),
            "resolved": params.get("resolved", None),
            "resolved_by": params.get("resolved_by", None),
        }

        if not mock_discussion:
            discussion_params = {"body": params["body"], "position": None, "mock_resolved": True}
            mock_discussion = self.merge_request.discussions.create(
                discussion_params, mock_note=note)

        self.notes.append(note)
        return note

    def list(self):
        return list(reversed(self.notes))  # Gitlab returns notes in the reversed order.


@dataclass
class DiscussionsManagerMock:
    merge_request: Any
    discussions: list = field(default_factory=list)

    @dataclass
    class DiscussionMock:
        manager: Any
        position: dict = field(default_factory=dict)
        resolved: bool = False
        mock_is_visible: bool = True  # Fake field for testing purposes.
        id: str = field(default_factory=lambda: uuid.uuid1().hex, init=False)
        notes: list = field(default_factory=list, init=False)

        @property
        def attributes(self):
            return {"notes": self.notes}

        def save(self):
            for d in self.manager.discussions:
                if not d.resolved:
                    self.manager.merge_request.blocking_discussions_resolved = False
                    return

            self.manager.merge_request.blocking_discussions_resolved = True

    def create(self, params, mock_is_visible: bool = True, mock_note: str = None):
        is_resolved = params.get("mock_resolved", False)
        discussion = self.DiscussionMock(
            manager=self, position=params["position"], mock_is_visible=mock_is_visible)

        if not mock_note:
            note_params = {"body": params["body"], "resolvable": True, "resolved": is_resolved}
            mock_note = self.merge_request.notes.create(note_params, mock_discussion=discussion)

        discussion.notes.append(mock_note)
        self.discussions.append(discussion)
        self.merge_request.blocking_discussions_resolved &= is_resolved
        return discussion

    def list(self, **_):
        return [d for d in self.discussions if d.mock_is_visible]


@dataclass
class MergeRequestMock:
    project: Any  # ProjectMock

    iid: int = field(default_factory=time.time_ns)
    title: str = "Do Zorz at work"
    has_conflicts: bool = False
    work_in_progress: bool = False
    blocking_discussions_resolved: bool = True
    assignees: list = field(default_factory=list)
    reviewers: list = field(default_factory=list)
    squash: bool = True
    description: str = ""
    state: str = "opened"
    source_branch: str = "feature1"
    target_branch: str = "master"
    author: dict = field(default_factory=lambda: USERS[0])
    web_url: str = ""
    squash_commit_sha: str = None
    source_project_id: int = DEFAULT_PROJECT_ID
    target_project_id: int = DEFAULT_PROJECT_ID

    # Fake fields for testing purposes.
    mock_needs_rebase: bool = False
    mock_rebased: bool = field(default=False, init=False)
    mock_huge_mr: bool = False
    mock_base_commit_sha: str = "000000000000"

    emojis_list: list = field(default_factory=list)
    approvers_list: list = field(default_factory=list)
    needed_approvers_number: int = DEFAULT_APPROVERS_NUMBER
    pipelines_list: list = field(default_factory=lambda: [(DEFAULT_COMMIT["sha"], "manual")])
    commits_list: list = field(default_factory=lambda: [DEFAULT_COMMIT])
    assignee_ids: list = field(default_factory=list)
    reviewer_ids: list = field(default_factory=list)

    # Managers, must not be directly initialized.
    awardemojis: AwardEmojiManagerMock = field(default_factory=AwardEmojiManagerMock, init=False)
    approvals: ApprovalsManagerMock = field(default_factory=ApprovalsManagerMock, init=False)
    notes: NotesManagerMock = field(default=None, init=False)
    discussions: DiscussionsManagerMock = field(default=None, init=False)
    manager: GitlabManagerMock = field(default_factory=GitlabManagerMock, init=False)
    diffs: VersionsManagerMock = field(default=None, init=False)

    def __post_init__(self):
        # Bind to "self.project".
        self.manager.gitlab = self.project.manager.gitlab
        self.project.mergerequests.add_mock_mr(self)

        # Create notes manager and bind it to itself.
        self.notes = NotesManagerMock(merge_request=self)

        # Create discussions manager and bind it to itself.
        self.discussions = DiscussionsManagerMock(merge_request=self)
        if not self.blocking_discussions_resolved:
            self.discussions.create(
                {"body": "default discussion", "position": None}, mock_is_visible=False)

        # Create versions ("diff" in gitlab library terminology) manager and bind it to itself.
        self.diffs = VersionsManagerMock(merge_request=self)

        # Initialize other fields.
        for name in self.emojis_list:
            self.awardemojis.create({'name': name})

        approvals = self.approvals.get()
        approvals.approvals_left = max(
            self.needed_approvers_number - len(set(self.approvers_list)), 0)
        for approver in set(self.approvers_list):
            approvals.approved_by.append({"user": {"username": approver}})

        for p_id, p_data in enumerate(self.pipelines_list):
            pipeline = PipelineMock(project=self.project, id=p_id, sha=p_data[0], status=p_data[1])
            self.project.pipelines.add_mock_pipeline(pipeline)

        for commit_data in self.commits_list:
            self._register_commit(commit_data)

        for assignee in self.assignees:
            assignee = self.project.users.list(username=assignee["username"])[0]
            self.assignee_ids.append(assignee.id)

        for reviewer in self.reviewers:
            reviewer = self.project.users.list(username=reviewer["username"])[0]
            self.reviewer_ids.append(reviewer.id)

    def _register_commit(self, commit_data):
        commit = CommitMock(**commit_data)
        self.project.commits.add_mock_commit(commit)
        # Add to current commit files all the files from the previous commits.
        for listed_commit in self.commits_list:
            for path, file_data in listed_commit.get("files", {}).items():
                self.project.files.add_mock_file(
                    ref=commit.sha, path=path, data=file_data["raw_data"])

    def add_mock_commit(self, commit_data: dict):
        self.commits_list.append(commit_data)
        self._register_commit(commit_data)

    # Gitlab library merge request interface implementation.
    @property
    def sha(self):
        if not self.commits_list:
            return None
        return self.commits_list[-1]["sha"]

    @property
    def approvals_left(self):
        return self.approvals.get().approvals_left

    @property
    def project_id(self):
        return self.project.id

    def pipelines(self):
        result = []
        for pipeline in sorted(self.project.pipelines.list(), key=lambda p: p.id):
            result.append({
                "id": pipeline.id,
                "sha": pipeline.sha,
                "status": pipeline.status,
                "web_url": pipeline.web_url
            })
        # NOTE: Gitlab returns pipeline with the highest ID first
        return list(reversed(result))

    def rebase(self):
        self.mock_rebased = True

    def merge(self, **_):
        if self.mock_needs_rebase:
            raise GitlabMRClosedError()
        self.state = "merged"
        self.squash_commit_sha = self.commits_list[-1]["sha"]

    def changes(self):
        files = {}
        for c in self.commits_list:
            files = {**files, **c["files"]}
        return {
            "changes": [
                {
                    "new_path": name,
                    "deleted_file": False,
                    "new_file": descr.get("is_new"),
                    "renamed_file": False,
                } for name, descr in files.items()],
            "changes_count": str(len(files)) + ("+" if self.mock_huge_mr else ""),
        }

    def save(self):
        users = self.project.users.list()

        for assignee_id in self.assignee_ids:
            assignee = [u for u in users if u.id == assignee_id][0]
            self.assignees.append({"username": assignee.username})

        for reviewer_id in self.reviewer_ids:
            reviewer = [u for u in users if u.id == reviewer_id][0]
            self.reviewers.append({"username": reviewer.username})

    def mock_comments(self):
        # Reverse notes list for the more convinient order (from the earliest note to the lateset).
        return [n["body"] for n in reversed(self.notes.list())]

    def commits(self):
        return [self.project.commits.get(c["sha"]) for c in reversed(self.commits_list)]

    def approve(self):
        pass
