import logging
from typing import Set, List, Dict
import re
import gitlab

from robocat.pipeline import Pipeline
from robocat.award_emoji_manager import AwardEmojiManager

logger = logging.getLogger(__name__)


class MergeRequest:
    def __init__(self, gitlab_mr, current_user, dry_run=False):
        self._gitlab_mr = gitlab_mr
        self._current_user = current_user
        self._dry_run = dry_run
        self._award_emoji = AwardEmojiManager(gitlab_mr.awardemojis, current_user, dry_run)

    def __str__(self):
        return f"MR!{self.id}"

    def __eq__(self, other):
        return self._gitlab_mr.iid == other._gitlab_mr.iid

    def __hash__(self):
        return int(self._gitlab_mr.iid)

    @property
    def id(self):
        return self._gitlab_mr.iid

    @property
    def title(self):
        return self._gitlab_mr.title

    @property
    def description(self):
        return self._gitlab_mr.description

    @property
    def target_branch(self):
        return self._gitlab_mr.target_branch

    @property
    def source_branch(self):
        return self._gitlab_mr.source_branch

    @property
    def squash_sha(self):
        return self._gitlab_mr.squash_commit_sha

    @property
    def work_in_progress(self):
        return self._gitlab_mr.work_in_progress

    @property
    def award_emoji(self):
        return self._award_emoji

    @property
    def approvals_left(self):
        approvals = self._gitlab_mr.approvals.get()
        return approvals.approvals_left

    @property
    def has_conflicts(self):
        return self._gitlab_mr.has_conflicts

    @property
    def blocking_discussions_resolved(self):
        return self._gitlab_mr.blocking_discussions_resolved

    @property
    def sha(self):
        return self._gitlab_mr.sha

    def raw_pipelines_data(self) -> List[Dict]:
        return self._gitlab_mr.pipelines()

    def pipeline(self, pipeline_id) -> Pipeline:
        project = self.get_raw_project_object()
        return Pipeline(project.pipelines.get(pipeline_id), self._dry_run)

    def rebase(self):
        logger.debug(f"{self}: Rebasing")
        if self._dry_run:
            return
        self._gitlab_mr.rebase()

    def merge(self):
        logger.debug(f"{self}: Merging")
        if self._dry_run:
            return

        squash_commit_message = None
        if self._gitlab_mr.squash:
            squash_commit_message = f"{self._gitlab_mr.title}\n\n{self._gitlab_mr.description}"
        self._gitlab_mr.merge(squash_commit_message=squash_commit_message)

    def create_pipeline(self):
        """Create detached pipeline for MR"""
        if self._dry_run:
            return
        # NOTE: gitlab python library doesn't support this API request.
        url = f"/projects/{self._gitlab_mr.project_id}/merge_requests/{self._gitlab_mr.iid}/pipelines"
        self._gitlab_mr.manager.gitlab.http_post(url)

    def get_raw_project_object(self):
        project_id = self._gitlab_mr.project_id
        return self._gitlab_mr.manager.gitlab.projects.get(project_id, lazy=True)

    def create_discussion(self, body: str, position: dict = None) -> bool:
        logger.debug(f"{self}: Creating discussion")
        if self._dry_run:
            return True

        try:
            self._gitlab_mr.discussions.create({"body": body, "position": position})
        except gitlab.exceptions.GitlabError as e:
            # This is workaround for the case when gitlab refuses to create discussion at the
            # position explicitly stated with "new_line" and "new_path" parameters. TODO: Fix this
            # workaround - find a way to reliably create a discussion, bonded to the file and line
            # number. Stating "old_path" and "old_line" fields in the "position" parameter can
            # help, but there is a problem of detection what "old_line" should be and also there
            # could be problems in the case when the file is removed/renamed.
            if position is not None and "new_line" in position and "new_path" in position:
                logger.info(
                    f"{self}: Cannot create a discussion at line number "
                    f"{position['new_line']} for file {position['new_path']}: {e}.")
            else:
                logger.warning(f"{self}: Cannot create a discussion: {e}.")
            return False
        return True

    @property
    def approved_by(self) -> Set[str]:
        approvals = self._gitlab_mr.approvals.get()
        return {approver["user"]["username"] for approver in approvals.approved_by}

    @property
    def assignees(self) -> Set[str]:
        return {assignee["username"] for assignee in self._gitlab_mr.assignees}

    def set_assignees_by_ids(self, assignee_ids: Set[int]) -> None:
        if self._dry_run:
            return
        self._gitlab_mr.assignee_ids = assignee_ids
        self._gitlab_mr.save()

    @property
    def latest_diff(self):
        lateset_diffs_list = self._gitlab_mr.diffs.list(per_page=1)
        assert len(lateset_diffs_list) > 0, (
            f"No diffs in {self}. "
            "We should not call this method for merge requests without commits")
        return lateset_diffs_list[0]

    def create_note(self, body: str) -> None:
        if not self._dry_run:
            self._gitlab_mr.notes.create({'body': body})

    @property
    def is_merged(self):
        return self._gitlab_mr.state == "merged"

    @property
    def author(self) -> dict:
        return self._gitlab_mr.author

    @property
    def url(self):
        return self._gitlab_mr.web_url

    # Commits in the chronological order: from the earliest to the latest.
    def commits(self):
        return reversed(list(self._gitlab_mr.commits()))

    def issue_keys(self):
        """Extract Jira issue names from the merge request title"""
        title_issues_part, _, _ = self._gitlab_mr.title.partition(":")
        keys_from_title = re.findall(r"\b(\w+-\d+)\b", title_issues_part)
        if keys_from_title:
            return keys_from_title
        return []

    def set_approvers_count(self, approvers_count):
        self._gitlab_mr.approvals.update(new_data={"approvals_required": approvers_count})
