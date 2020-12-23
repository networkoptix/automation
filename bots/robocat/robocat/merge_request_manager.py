import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Set, List, Dict
import re
import gitlab

import robocat.comments
from robocat.award_emoji_manager import AwardEmojiManager
from robocat.pipeline import Pipeline, PipelineStatus, PlayPipelineError, RunPipelineReason
from robocat.action_reasons import WaitReason, ReturnToDevelopmentReason
from robocat.merge_request import MergeRequest
from robocat.project import Project

logger = logging.getLogger(__name__)


@dataclass
class FollowupCreationResult:
    branch: str
    successfull: bool
    url: str = ""

    @property
    def title(self):
        if self.successfull:
            return "Follow-up merge request added"
        return "Failed to add follow-up merge request"

    @property
    def message(self):
        if self.successfull:
            return robocat.comments.followup_merge_request_message.format(
                branch=self.branch,
                url=self.url)
        return robocat.comments.failed_followup_merge_request_message.format(branch=self.branch)

    @property
    def emoji(self):
        if self.successfull:
            return AwardEmojiManager.FOLLOWUP_CREATED_EMOJI
        return AwardEmojiManager.FOLOWUP_CREATION_FAILED_EMOJI


@dataclass
class ApprovalRequirements:
    approvals_left: int = None
    mandatory_approvers: Set[str] = field(default_factory=set)


@dataclass
class MergeRequestChanges:
    not_changed: bool = False
    commits_changed: bool = False
    is_rebased: bool = False
    message: str = ""

    def __str__(self):
        return self.message


@dataclass
class MergeRequestChangesSameSha(MergeRequestChanges):
    message: str = "nothing changed"
    not_changed: bool = True


@dataclass
class MergeRequestChangesRebased(MergeRequestChanges):
    message: str = "last commit sha changed"
    is_rebased: bool = True


@dataclass
class MergeRequestChangesDiffHashChanged(MergeRequestChanges):
    message: str = "last commit diff changed"
    commits_changed: bool = True


@dataclass
class MergeRequestChangesCommitMessageChanged(MergeRequestChanges):
    message: str = "last commit name changed"
    commits_changed: bool = True


@dataclass
class FollowupData:
    issue_keys: list
    original_target_branch: str
    original_source_branch: str
    commit_sha_list: list = field(default_factory=list)
    title: str = None
    description: str = None
    author_username: str = None
    original_mr_url: str = None
    is_followup: bool = False


# NOTE: Hash and eq methods for this object should return different values for different object
# instances on order to lru_cache is working right.
class MergeRequestManager:
    _FOLLOWUP_DESCRIPTION_RE = re.compile(r"\(cherry picked from commit (?P<sha>[a-f0-9]{40})\)")

    def __init__(self, mr: MergeRequest):
        logger.debug(f"Initialize MR manager for {mr.id}: '{mr.title}'")
        self._mr = mr

    def __str__(self):
        return f"MR Manager!{self._mr.id}"

    @property
    def mr_id(self) -> int:
        return self._mr.id

    @property
    def mr_last_commit_sha(self) -> str:
        return self._mr.sha

    @property
    def mr_work_in_progress(self) -> bool:
        return self._mr.work_in_progress

    @property
    def mr_has_commits(self) -> bool:
        return bool(self._mr.sha)

    @property
    def mr_has_conflicts(self) -> bool:
        return self._mr.has_conflicts

    @property
    def mr_has_unresolved_threads(self) -> bool:
        return not self._mr.blocking_discussions_resolved

    @property
    def mr_last_pipeline_status(self) -> PipelineStatus:
        pipeline = self._get_last_pipeline()
        return pipeline.status

    @property
    def mr_url(self):
        return self._mr.url

    @property
    def is_merged(self) -> bool:
        return self._mr.is_merged

    def update_unfinished_processing_flag(self, value):
        if self._mr.award_emoji.find(AwardEmojiManager.UNFINISHED_PROCESSING_EMOJI, own=True):
            if not value:
                self._mr.award_emoji.delete(
                    AwardEmojiManager.UNFINISHED_PROCESSING_EMOJI, own=False)
        else:
            if value:
                self._mr.award_emoji.create(AwardEmojiManager.UNFINISHED_PROCESSING_EMOJI)

    def satisfies_approval_requirements(self, requirements: ApprovalRequirements) -> bool:
        result = True
        if requirements.approvals_left is not None:
            result &= self._cached_approvals_left() == requirements.approvals_left
        if requirements.mandatory_approvers:
            approved_by = self._mr.approved_by
            result &= requirements.mandatory_approvers.issubset(approved_by)
        return result

    @lru_cache(maxsize=16)  # Short term cache. New data is obtained for every bot "handle" call.
    def _cached_approvals_left(self):
        return self._mr.approvals_left

    def ensure_watching(self) -> bool:
        if self._mr.award_emoji.find(AwardEmojiManager.WATCH_EMOJI, own=True):
            return False

        logger.info(f"{self}: New merge request to take care of")
        self._mr.award_emoji.create(AwardEmojiManager.WATCH_EMOJI)
        message = robocat.comments.initial_message.format(
            approvals_left=self._cached_approvals_left())
        self._add_comment(
            "Looking after this MR", message, AwardEmojiManager.INITIAL_EMOJI)
        return True

    def _add_comment(self, title, message, emoji=""):
        logger.debug(f"{self}: Adding comment with title: {title}")
        self._mr.create_note(body=robocat.comments.template.format(**locals()))

    def ensure_user_requeseted_pipeline_run(self) -> bool:
        if not self._mr.award_emoji.find(AwardEmojiManager.PIPELINE_EMOJI, own=False):
            return False
        self._run_pipeline(RunPipelineReason.requested_by_user)
        return True

    def ensure_first_pipeline_run(self) -> bool:
        pipeline = self._get_last_pipeline()
        if pipeline:
            return False
        self._run_pipeline(RunPipelineReason.no_pipelines_before)
        return True

    @lru_cache(maxsize=16)  # Short term cache. New data is obtained for every bot "handle" call.
    def _get_last_pipeline(self, include_skipped=False) -> Pipeline:
        pipeline_ids = [
            p['id'] for p in self._mr.raw_pipelines_data()
            if include_skipped or Pipeline.translate_status(p["status"]) != PipelineStatus.skipped]
        return self._mr.pipeline(max(pipeline_ids)) if pipeline_ids else None

    def ensure_pipeline_rerun(self) -> bool:
        pipeline = self._get_last_pipeline()
        if not pipeline:
            return False

        changes = self._difference_to_previous_state(pipeline.sha)
        if changes.not_changed:
            return False

        if changes.commits_changed:
            self._run_pipeline(RunPipelineReason.mr_updated, changes)
            return True

        assert changes.is_rebased, f"Unexpected MR changes status: {changes}."

        # Re-run pipeline after rebase only if last pipeline failed (we assume that rebase by
        # itself can't break the build) and all threads are resolved (since if they are not,
        # probably some changes will be added and we will have to re-run pipeline after that)
        if pipeline.status == PipelineStatus.failed and not self.mr_has_unresolved_threads:
            self._run_pipeline(RunPipelineReason.mr_rebased, changes)
            return True

        return False

    def _difference_to_previous_state(self, sha: str) -> MergeRequestChanges:
        if sha == self._mr.sha:
            return MergeRequestChangesSameSha()

        commit_message_for_sha = self._get_commit_message(sha)
        last_commit_message = self._get_commit_message(self._mr.sha)
        if commit_message_for_sha != last_commit_message:
            return MergeRequestChangesCommitMessageChanged()

        diff_for_sha = self._get_commit_diff_hash(sha)
        diff_for_current_sha = self._get_commit_diff_hash(self._mr.sha)
        if diff_for_sha != diff_for_current_sha:
            return MergeRequestChangesDiffHashChanged()

        return MergeRequestChangesRebased()

    def _get_commit_message(self, sha: str):
        return self._get_project().get_commit_message(sha)

    def _get_commit_diff_hash(self, sha: str):
        return self._get_project().get_commit_diff_hash(sha)

    def ensure_assignee(self, assignee_username) -> bool:
        assignees = self._mr.assignees
        if assignee_username in assignees:
            return False

        updated_assignees = assignees | set([assignee_username])
        logger.debug(f"{self}: Updating assignees list: {updated_assignees}")

        project = self._get_project()
        assignee_ids = list()
        for assignee in updated_assignees:
            assignee_ids += project.get_user_ids(assignee)

        self._mr.set_assignees_by_ids(assignee_ids)
        return True

    def _get_project(self):
        return Project(self._mr.get_raw_project_object())

    def _run_pipeline(self, reason, details=None):
        logger.info(f"{self._mr}: Running pipeline ({reason})")

        pipeline = self._get_last_pipeline(include_skipped=True)

        # NOTE: There's no need to create pipelines in other cases because they are created by
        # Gitlab automatically.
        if reason == RunPipelineReason.requested_by_user:
            self._mr.award_emoji.delete(AwardEmojiManager.PIPELINE_EMOJI, own=False)
            # Don't create new pipeline if the last one is ready to start.
            if not pipeline or not pipeline.is_manual:
                pipeline = self._create_mr_pipeline()

        if not pipeline:  # We expect that by this time gitlab has already created a pipeline.
            raise PlayPipelineError("No autocreated pipelines found.")
        pipeline.play()

        reason_msg = reason.value + ("" if not details else f" ({details})")
        message = robocat.comments.run_pipeline_message.format(
            pipeline_id=pipeline.id, reason=reason_msg)
        self._add_comment("Pipeline started", message, AwardEmojiManager.PIPELINE_EMOJI)
        self.ensure_wait_state(None)

        # Must clear last pipeline info from the cache since it's state will probably change as a
        # result of this function run.
        self._get_last_pipeline.cache_clear()

    def _create_mr_pipeline(self):
        self._mr.create_pipeline()
        self._get_last_pipeline.cache_clear()
        return self._get_last_pipeline(include_skipped=True)

    def return_to_development(self, reason) -> None:
        logger.info(f"{self}: Moving to WIP: {reason}")

        if reason == ReturnToDevelopmentReason.failed_pipeline:
            last_pipeline = self._get_last_pipeline()
            title = f"Pipeline [{last_pipeline.id}]({last_pipeline.web_url}) failed"
            message = robocat.comments.failed_pipeline_message
        elif reason == ReturnToDevelopmentReason.conflicts:
            title = "Conflicts with target branch"
            message = robocat.comments.conflicts_message
        elif reason == ReturnToDevelopmentReason.unresolved_threads:
            title = "Unresolved threads"
            message = robocat.comments.unresolved_threads_message
        elif reason == ReturnToDevelopmentReason.autocreated:
            title = message = None
        else:
            assert False, f"Unknown reason: {reason}"

        self._mr.create_note(body="/wip")
        if message is not None:
            self._add_comment(title, message, AwardEmojiManager.RETURN_TO_DEVELOPMENT_EMOJI)
        self.unset_wait_state()

    def ensure_wait_state(self, reason) -> None:
        if self._mr.award_emoji.find(AwardEmojiManager.WAIT_EMOJI, own=True):
            logger.debug(
                f"{self}: Setting wait reason {reason} ignored because "
                f"{AwardEmojiManager.WAIT_EMOJI} emoji is set.")
            return

        if reason == WaitReason.no_commits:
            title = "Waiting for commits"
            message = robocat.comments.commits_wait_message
        elif reason == WaitReason.not_approved:
            title = "Waiting for approvals"
            message = robocat.comments.approval_wait_message.format(
                approvals_left=self._cached_approvals_left())
        elif reason == WaitReason.pipeline_running:
            last_pipeline = self._get_last_pipeline()
            title = "Waiting for pipeline"
            message = robocat.comments.pipeline_wait_message.format(
                pipeline_id=last_pipeline.id, pipeline_url=last_pipeline.web_url)

        self._mr.award_emoji.create(AwardEmojiManager.WAIT_EMOJI)
        if reason:
            self._add_comment(title, message, AwardEmojiManager.WAIT_EMOJI)

    def unset_wait_state(self) -> None:
        self._mr.award_emoji.delete(AwardEmojiManager.WAIT_EMOJI, own=True)

    def merge_or_rebase(self):
        if self.is_merged:
            logger.info(f"{self}: Already merged")
            return

        try:
            logger.info(f"{self}: Trying to merge")
            self._mr.merge()
            message = robocat.comments.merged_message.format(branch=self._mr.target_branch)
            self._add_comment("MR merged", message, AwardEmojiManager.MERGED_EMOJI)
        except gitlab.exceptions.GitlabMRClosedError as e:
            # NOTE: gitlab API sucks and there is no other way to know if rebase required.
            logger.info(
                f"{self._mr}: Got error during merge, most probably just rebase required: {e}")
            self._mr.rebase()

    def create_thread_to_resolve(
            self, title, message, emoji, file: str = None, line: int = None) -> bool:
        if file is not None and line is not None:
            latest_diff = self._mr.latest_diff
            position = {
                "base_sha": latest_diff.base_commit_sha,
                "start_sha": latest_diff.start_commit_sha,
                "head_sha": latest_diff.head_commit_sha,
                "position_type": "text",
                "new_line": line,
                "new_path": file,
            }
        else:
            position = None

        body = robocat.comments.template.format(title=title, message=message, emoji=emoji)
        return self._mr.create_discussion(body=body, position=position)

    @property
    def last_mr_changes(self) -> List[Dict]:
        return self._get_project().get_mr_commit_changes(self._mr.id, self._mr.sha)

    def get_followup_mr_data(self) -> FollowupData:
        assert self._mr.is_merged, f"Merge request {self} isn't merged."

        issue_keys = self._mr.issue_keys()
        if not issue_keys:
            # TODO: Add comment to MR informing the user that we can't find any attached issue and
            # that he or she should double-check if it is normal.
            logger.info(
                "{self}: Can't detect attached issue for the merge request. Skipping cherry-pick.")
            return None

        if self._is_followup_mr():
            return FollowupData(
                is_followup=True,
                issue_keys=issue_keys,
                original_target_branch=self._mr.target_branch,
                original_source_branch=self._mr.source_branch,
                title=self._mr.title,
                description=self._mr.description,
                author_username=self._mr.author["username"],
                original_mr_url=self._mr.url)

        if self._mr.squash_sha is not None:
            commit_sha_list = [self._mr.squash_sha[0:12]]
        else:
            commit_sha_list = [c.id[0:12] for c in self._mr.commits()]

        return FollowupData(
            commit_sha_list=commit_sha_list,
            issue_keys=issue_keys,
            original_target_branch=self._mr.target_branch,
            original_source_branch=self._mr.source_branch,
            title=self._mr.title,
            description=self._mr.description,
            author_username=self._mr.author["username"],
            original_mr_url=self._mr.url)

    def _is_followup_mr(self):
        if self._mr.award_emoji.find(AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI, own=True):
            return True

        if self._FOLLOWUP_DESCRIPTION_RE.search(self._mr.description):
            return True

        if any(c for c in self._mr.commits() if self._FOLLOWUP_DESCRIPTION_RE.search(c.message)):
            return True

        return False

    def add_followup_creation_comment(self, followup: FollowupCreationResult):
        self._add_comment(followup.title, followup.message, followup.emoji)
