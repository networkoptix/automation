import logging
from typing import Any, Dict, List, Set
import re
import gitlab

from robocat.award_emoji_manager import AwardEmojiManager

logger = logging.getLogger(__name__)


class MergeRequest:
    DISCUSSIONS_PAGE_SIZE = 100

    def __init__(self, gitlab_mr, current_user):
        self._gitlab_mr = gitlab_mr
        self._award_emoji = AwardEmojiManager(gitlab_mr.awardemojis, current_user)
        self._discussions = []
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

    def notes_data(self) -> List[Dict[str, Any]]:
        result = []
        for discussion in self._discussions:
            for note in discussion.attributes["notes"]:
                note_copy = note.copy()
                note_copy["_discussion_id"] = discussion.id
                result.append(note_copy)
        return sorted(result, key=lambda n: n["created_at"])

    @property
    def id(self):
        return self._gitlab_mr.iid

    @property
    def title(self) -> str:
        return self._gitlab_mr.title

    @property
    def description(self) -> str:
        return self._gitlab_mr.description

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

    @property
    def approvals_left(self) -> int:
        approvals = self._gitlab_mr.approvals.get()
        return approvals.approvals_left

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
    def issue_keys(self) -> List[str]:
        """Extract Jira issue names from the merge request title"""
        title_issues_part, _, _ = self.title.partition(":")
        keys_from_title = re.findall(r"\b(\w+-\d+)\b", title_issues_part)
        if keys_from_title:
            return keys_from_title
        return []

    def raw_pipelines_list(self) -> List[Dict]:
        return self._gitlab_mr.pipelines()

    def rebase(self):
        logger.debug(f"{self}: Rebasing")
        self._gitlab_mr.rebase()

    def merge(self):
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

        except gitlab.exceptions.GitlabError as e:
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
                    f"{self}: Internal gitlab errror while creating a discussion at line number "
                    f"{position['new_line']} for file {position['new_path']}: {e}.")
                return True

            if is_new_position_in_params:
                logger.info(
                    f"{self}: Cannot create a discussion at line number "
                    f"{position['new_line']} for file {position['new_path']}: {e}.")
            else:
                logger.warning(f"{self}: Cannot create a discussion: {e}.")
            return False
        return True

    def approved_by(self) -> Set[str]:
        approvals = self._gitlab_mr.approvals.get()
        return {approver["user"]["username"] for approver in approvals.approved_by}

    def approve(self):
        self._gitlab_mr.approve()

    @property
    def assignees(self) -> Set[str]:
        return {assignee["username"] for assignee in self._gitlab_mr.assignees}

    @property
    def reviewers(self) -> Set[str]:
        return {reviewer["username"] for reviewer in self._gitlab_mr.reviewers}

    def set_assignees_by_ids(self, assignee_ids: Set[int]) -> None:
        # "assignee_ids" must consist of unique values so we use "set" type for the function
        # parameter to enforce this, but "assignee_ids" must be of type "list".
        self._gitlab_mr.assignee_ids = list(assignee_ids)
        self._gitlab_mr.save()

    def latest_diff(self):
        lateset_diffs_list = self._gitlab_mr.diffs.list(per_page=1)
        assert len(lateset_diffs_list) > 0, (
            f"No diffs in {self}. "
            "We should not call this method for merge requests without commits")
        return lateset_diffs_list[0]

    def create_note(self, body: str) -> None:
        logger.debug(f'{self}: Creating comment. Message: {body!r}')
        self._gitlab_mr.notes.create({'body': body})

    def set_draft_flag(self, state: bool = True):
        if self.work_in_progress:
            return
        self.create_note("/draft")

    @property
    def is_merged(self):
        return self._gitlab_mr.state == "merged"

    @property
    def author_name(self) -> str:
        return self._gitlab_mr.author["username"]

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
