## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from typing import Any, Optional
import logging
import re

from gitlab.exceptions import GitlabError
from gitlab.v4.objects import ProjectMergeRequestDiff
import gitlab

from automation_tools.mr_data_structures import ApprovalsInfo
from robocat.award_emoji_manager import AwardEmojiManager
import automation_tools.utils

logger = logging.getLogger(__name__)


class MergeRequest:
    DISCUSSIONS_PAGE_SIZE = 100
    _ISSUE_PATTERN_RE = re.compile(r"\b([A-Z][A-Z0-9_]+-\d+)\b")
    _ISSUE_CLOSING_PATTERN_RE = re.compile(
        r"\b(?:[Cc]los(?:e[sd]?|ing)|\b[Ff]ix(?:e[sd]|ing)?|\b[Rr]esolv(?:e[sd]?|ing)|"
        r"\b[Ii]mplement(?:s|ed|ing)?)(?::?) +(?:issues? )?"
        r"(?P<issue_refs>(?: *,? +and +| *,? *[A-Z][A-Z0-9_]+-\d+)+)",
        flags=re.M)

    def __init__(self, gitlab_mr, current_user):
        self._gitlab_mr = gitlab_mr
        self._award_emoji = AwardEmojiManager(gitlab_mr.awardemojis, current_user)
        self._discussions = []
        self.rebase_in_progress = False
        self._has_unloaded_notes = True
        self._current_user = current_user
        self.load_discussions()

    def __str__(self):
        return f"MR!{self.id}"

    def __eq__(self, other):
        return self._gitlab_mr.iid == other._gitlab_mr.iid

    def __hash__(self):
        return int(self._gitlab_mr.iid)

    def load_discussions(self):
        self._discussions = []
        current_page = 1
        while True:
            current_page_discussions = self._gitlab_mr.discussions.list(
                page=current_page, per_page=self.DISCUSSIONS_PAGE_SIZE)
            self._discussions += current_page_discussions
            if len(current_page_discussions) < self.DISCUSSIONS_PAGE_SIZE:
                break
            current_page += 1
        self._has_unloaded_notes = False

    def notes_data(self) -> list[dict[str, Any]]:
        if self._has_unloaded_notes:
            self.load_discussions()

        result = []
        for discussion in self._discussions:
            for note in discussion.attributes["notes"]:
                note_copy = note.copy()
                note_copy["_discussion_id"] = discussion.id
                result.append(note_copy)
        return sorted(result, key=lambda n: n["created_at"])

    def note_data(self, note_id: int) -> Optional[dict[str, Any]]:
        try:
            # TODO: Get rid of using _attrs - better to have an explicit list of the needed fields
            # - most likely the place for this list is in Note class.
            return self._gitlab_mr.notes.get(note_id)._attrs
        except gitlab.exceptions.GitlabGetError as e:
            if e.response_code == 404:
                return None
            raise e

    def update_note(self, note_id: int, body: str):
        logger.debug(f'{self}: Updating comment {note_id}. Message: {body!r}')
        self._gitlab_mr.notes.update(id=note_id, new_data={"body": body})
        self._has_unloaded_notes = True

    @property
    def id(self) -> int:
        return int(self._gitlab_mr.iid)

    @property
    def title(self) -> str:
        return self._gitlab_mr.title

    @property
    def description(self) -> str:
        return self._gitlab_mr.description if self._gitlab_mr.description is not None else ""

    @description.setter
    def description(self, value: str):
        self._gitlab_mr.description = value
        self._gitlab_mr.save()

    @property
    def target_branch(self) -> str:
        return self._gitlab_mr.target_branch

    @property
    def source_branch(self) -> str:
        return self._gitlab_mr.source_branch

    @property
    def work_in_progress(self) -> bool:
        return self._gitlab_mr.work_in_progress

    @property
    def award_emoji(self):
        return self._award_emoji

    def get_approvals_info(self) -> ApprovalsInfo:
        approvals = self._gitlab_mr.approvals.get()
        return ApprovalsInfo(
            is_approved=approvals.approved,
            approvals_left=approvals.approvals_left,
            approvals_required=approvals.approvals_required)

    @property
    def has_conflicts(self) -> bool:
        return self._gitlab_mr.has_conflicts

    @property
    def blocking_discussions_resolved(self) -> bool:
        return self._gitlab_mr.blocking_discussions_resolved

    @property
    def sha(self) -> str:
        return self._gitlab_mr.sha

    @property
    def has_commits(self) -> bool:
        return bool(self.sha)

    @property
    def project_id(self) -> int:
        return self._gitlab_mr.project_id

    @property
    def source_branch_project_id(self) -> int:
        return self._gitlab_mr.source_project_id

    @property
    def target_branch_project_id(self) -> int:
        return self._gitlab_mr.target_project_id

    @property
    def raw_gitlab_object(self) -> gitlab.Gitlab:
        return self._gitlab_mr.manager.gitlab

    @property
    def squash_commit_sha(self) -> str:
        return self._gitlab_mr.squash_commit_sha

    @property
    def squash(self) -> bool:
        return self._gitlab_mr.squash

    @property
    def issue_keys(self) -> list[str]:
        """Extract Jira issue names from the Merge Request title and description"""
        title = (self.title if not self.title.startswith("Draft:") else self.title[6:]).strip()
        issue_keys = self.extract_issue_keys(title, self.description)
        return list(issue_keys)

    def extract_issue_keys(self, header: str, description: str) -> set[str]:
        title_issues_part, _, _ = header.partition(":")
        issue_keys = list(self._ISSUE_PATTERN_RE.findall(title_issues_part))
        for keys_group in self._ISSUE_CLOSING_PATTERN_RE.finditer(description):
            issue_keys += list(self._ISSUE_PATTERN_RE.findall(keys_group["issue_refs"]))
        return set(issue_keys)

    def raw_pipelines_list(self) -> list[dict]:
        return self._gitlab_mr.pipelines()

    def rebase(self):
        logger.debug(f"{self}: Rebasing")
        self.rebase_in_progress = True
        self._gitlab_mr.rebase()

    def merge(self):
        project = self.raw_gitlab_object.projects.get(self.project_id, lazy=False)
        merge_trains_enabled = project.attributes.get("merge_pipelines_enabled", False)

        if merge_trains_enabled:
            logger.debug(f"{self}: Adding to merge train")
            endpoint = (
                f"/projects/{self.project_id}/merge_trains/merge_requests/{self._gitlab_mr.iid}"
            )
            self._gitlab_mr.manager.gitlab.http_post(endpoint)
        else:
            logger.debug(f"{self}: Merging")
            squash_commit_message = None
            if self._gitlab_mr.squash:
                squash_commit_message = f"{self._gitlab_mr.title}\n\n{self._gitlab_mr.description}"
            self._gitlab_mr.merge(squash_commit_message=squash_commit_message)

    def create_discussion(
            self, body: str, position: dict = None, autoresolve: bool = False) -> bool:
        logger.debug(f'{self}: Creating discussion at {position}. Message: "{body}"')

        try:
            discussion = self._gitlab_mr.discussions.create({"body": body, "position": position})
            if autoresolve:
                discussion.resolved = True
                discussion.save()

        except GitlabError as e:
            # This is workaround for the case when gitlab refuses to create discussion at the
            # position explicitly stated with "new_line" and "new_path" parameters. TODO: Fix this
            # workaround - find a way to reliably create a discussion, bonded to the file and line
            # number. Stating "old_path" and "old_line" fields in the "position" parameter can
            # help, but there is a problem of detection what "old_line" should be and also there
            # could be problems in the case when the file is removed/renamed.
            is_new_position_in_params = (
                position is not None and "new_line" in position and "new_path" in position)
            if is_new_position_in_params and e.response_code == 500:
                # Most likely the discussion is created, so log the error and return True.
                logger.info(
                    f"{self}: Internal gitlab error while creating a discussion at line number "
                    f"{position['new_line']} for file {position['new_path']}: {e}.")
                return True

            if is_new_position_in_params:
                logger.info(
                    f"{self}: Cannot create a discussion at line number "
                    f"{position['new_line']} for file {position['new_path']}: {e}.")
            else:
                logger.warning(f"{self}: Cannot create a discussion: {e}.")
            return False

        self._has_unloaded_notes = True
        return True

    def approved_by(self) -> set[str]:
        approvals = self._gitlab_mr.approvals.get()
        return {approver["user"]["username"] for approver in approvals.approved_by}

    def ensure_approve(self) -> bool:
        try:
            self._gitlab_mr.approve()
        except gitlab.exceptions.GitlabAuthenticationError:
            # If the Merge Request is already approved by the user, the GitLab API returns error
            # 401 in response for the "approve" call from the same user. Return False if it is not
            # the case.
            if self._current_user not in self.approved_by():
                logger.warning(f"{self}: User is not authorized to approve the MR.")
                return False
            logger.debug(f"{self}: Already approved by {self.approved_by()}.")

        return True

    def ensure_unapprove(self) -> bool:
        try:
            self._gitlab_mr.unapprove()
        except gitlab.exceptions.GitlabMRApprovalError:
            # If the Merge Request is not approved by the user, the gitlab module throws an
            # exception in response for the "unapprove" call from the same user. Return False if it
            # is not the case and there is another reason for the exception.
            if self._current_user in self.approved_by():
                logger.warning(f"{self}: Resource is not found when trying to unapprove the MR.")
                return False
            logger.debug(f"{self}: Not approved by {self.approved_by()}.")

        return True

    @property
    def assignees(self) -> set[str]:
        return {assignee["username"] for assignee in self._gitlab_mr.assignees}

    @property
    def reviewers(self) -> set[str]:
        return {reviewer["username"] for reviewer in self._gitlab_mr.reviewers}

    def set_assignees_by_ids(self, assignee_ids: set[int]) -> None:
        # "assignee_ids" must consist of unique values so we use "set" type for the function
        # parameter to enforce this, but "assignee_ids" must be of type "list".
        self._gitlab_mr.assignee_ids = list(assignee_ids)
        self._gitlab_mr.save()

    def latest_diff(self) -> ProjectMergeRequestDiff:
        lateset_diffs_list = self._gitlab_mr.diffs.list(per_page=1)
        assert len(lateset_diffs_list) > 0, (
            f"No diffs in {self}. "
            "We should not call this method for merge requests without commits")
        return lateset_diffs_list[0]

    def create_note(self, body: str) -> None:
        logger.debug(f'{self}: Creating comment. Message: {body!r}')
        self._gitlab_mr.notes.create({'body': body})
        self._has_unloaded_notes = True

    def set_draft_flag(self):
        if self.work_in_progress:
            return
        self.create_note("/draft")

    @property
    def is_merged(self):
        return self._gitlab_mr.state == "merged"

    @property
    def is_closed(self):
        return self._gitlab_mr.state == "closed"

    @property
    def author(self) -> automation_tools.utils.User:
        return automation_tools.utils.User(
            username=self._gitlab_mr.author["username"], name=self._gitlab_mr.author["name"])

    @property
    def url(self):
        return self._gitlab_mr.web_url

    # Commits in the chronological order: from the earliest to the latest.
    def commits(self):
        return reversed(list(self._gitlab_mr.commits()))

    def set_approvers_count(self, approvers_count):
        self._gitlab_mr.approvals.update(new_data={"approvals_required": approvers_count})

    def get_approvers_count(self):
        return self._gitlab_mr.approvals.get().approvals_required

    @property
    def is_rebase_needed(self) -> bool:
        return self._gitlab_mr.detailed_merge_status == "need_rebase"

    @property
    def is_pipeline_run_needed(self) -> bool:
        return self._gitlab_mr.detailed_merge_status == "ci_must_pass"

    @property
    def is_mergeable(self) -> bool:
        return self._gitlab_mr.detailed_merge_status == "mergeable"
