import logging
import dataclasses
from functools import lru_cache
from typing import Any, Dict, Set, List, Optional
import re
import time

import git
import gitlab

import robocat.comments
from robocat.award_emoji_manager import AwardEmojiManager
from robocat.pipeline import (
    Pipeline,
    PipelineStatus,
    PlayPipelineError,
    RunPipelineReason,
    JobStatus)
from robocat.action_reasons import WaitReason, ReturnToDevelopmentReason
from robocat.merge_request import MergeRequest
from robocat.note import Comment, MessageId, Note
from robocat.project import MergeRequestDiffData
from robocat.gitlab import Gitlab
import automation_tools.bot_info
import automation_tools.git

logger = logging.getLogger(__name__)


@dataclasses.dataclass
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


@dataclasses.dataclass
class ApprovalRequirements:
    approvals_left: int = None
    authorized_approvers: Set[str] = dataclasses.field(default_factory=set)


@dataclasses.dataclass
class MergeRequestChanges:
    not_changed: bool = False
    mr_diff_changed: bool = False
    is_rebased: bool = False
    is_message_changed: bool = False
    text: str = ""

    def __str__(self):
        return self.text


@dataclasses.dataclass
class MergeRequestChangesSameSha(MergeRequestChanges):
    text: str = "nothing changed"
    not_changed: bool = True


@dataclasses.dataclass
class MergeRequestChangesRebased(MergeRequestChanges):
    is_message_changed: bool
    text: str = "last commit sha changed"
    is_rebased: bool = True


@dataclasses.dataclass
class MergeRequestChangesDiffHashChanged(MergeRequestChanges):
    is_message_changed: bool
    text: str = "last commit diff changed"
    mr_diff_changed: bool = True


@dataclasses.dataclass
class MergeRequestData:
    id: int
    title: str
    description: str
    author_name: str
    sha: str
    url: str
    is_merged: bool
    has_commits: bool
    has_conflicts: bool
    work_in_progress: bool
    blocking_discussions_resolved: bool
    source_branch: bool
    target_branch: bool
    source_branch_project_id: int
    target_branch_project_id: int
    issue_keys: list
    squash: bool


@dataclasses.dataclass
class MergeRequestCommitsData:
    issue_keys: List[Set[str]]
    messages: List[str]


# NOTE: Hash and eq methods for this object should return different values for different object
# instances in order to lru_cache is working right.
class MergeRequestManager:
    _FOLLOWUP_DESCRIPTION_RE = re.compile(r"\(cherry picked from commit (?P<sha>[a-f0-9]{40})\)")

    def __init__(self, mr: MergeRequest, current_user: str = None):
        logger.debug(f"Initialize MR manager for {mr.id}: '{mr.title}'")
        self._mr = mr
        self._current_user = current_user
        self._gitlab = Gitlab(self._mr.raw_gitlab_object)

    def __str__(self):
        return f"MR Manager!{self._mr.id}"

    @property
    def data(self) -> MergeRequestData:
        return MergeRequestData(
            **{f.name: getattr(self._mr, f.name) for f in dataclasses.fields(MergeRequestData)})

    def get_commits_data(self) -> MergeRequestCommitsData:
        messages = [c.message for c in self._mr.commits()]

        issue_keys = []
        for message in messages:
            (title, _, body) = message.partition("\n\n")
            issue_keys.append(self._mr.extract_issue_keys(title, body))

        return MergeRequestCommitsData(
            messages=messages,
            issue_keys=issue_keys
        )

    def get_last_pipeline_status(self) -> PipelineStatus:
        pipeline = self._get_last_pipeline()
        return pipeline.status

    def get_changes(self) -> MergeRequestDiffData:
        return self._get_project().get_mr_commit_changes(
            self._mr.id, self._mr.target_branch, self._mr.sha)

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
        if requirements.authorized_approvers:
            approved_by = self._mr.approved_by()
            # If the Merge Request author is an authorized approver, consider this Merge Request
            # approved by authorized approver.
            if self._mr.author_name not in requirements.authorized_approvers:
                result &= bool(requirements.authorized_approvers.intersection(approved_by))

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
            "Looking after this MR",
            message,
            emoji=AwardEmojiManager.INITIAL_EMOJI,
            message_id=MessageId.Initial)

        # Gitlab automatically appends `Closes-<issue_key>.` to Merge Request descriptions. We
        # don't need this, and, moreover, it conflicts with our sanity checks. So, if the bot
        # suspects that this phrase is auto-added (this is the last words in the Merge Request
        # description and the Issue Key mentioned is the same that in the Merge Request title), it
        # strips this phrase out.
        issue_key, *_ = self._mr.title.partition(":")
        description = self._mr.description.strip()
        search_string = f"Closes {issue_key}"
        if description.endswith(search_string):
            self._mr.description = description[:len(description) - len(search_string)].strip()

        return True

    def _add_comment(
            self, title, message: str, emoji: str = None,
            message_id: MessageId = None, message_data: Dict[str, Any] = None):
        logger.debug(f"{self}: Adding comment with title: {title}")
        message_params = {}
        message_params["title"] = title
        message_params["message"] = message
        if message_id:
            message_params["message"] += Note.format_details_string(
                message_id=message_id, sha=self._mr.sha, data=message_data)
        if emoji:
            message_params["emoji"] = emoji
        message_params["revision"] = automation_tools.bot_info.revision()
        self._mr.create_note(body=robocat.comments.template.format(**message_params))

    def ensure_user_requested_pipeline_run(self) -> bool:
        if not self._mr.award_emoji.find(AwardEmojiManager.PIPELINE_EMOJI, own=False):
            return False
        last_pipeline = self._get_last_pipeline()
        if last_pipeline and last_pipeline.sha == self._mr.sha:
            logger.info(f"{self._mr}: Refusing to manually run pipeline with the same sha")
            message = robocat.comments.refuse_run_pipeline_message.format(
                pipeline_id=last_pipeline.id, pipeline_url=last_pipeline.web_url, sha=self._mr.sha)
            self._add_comment(
                "Pipeline was not started", message, AwardEmojiManager.NOTIFICATION_EMOJI)
            self._mr.award_emoji.delete(AwardEmojiManager.PIPELINE_EMOJI, own=False)
            return False

        if self.ensure_rebase():
            return False

        self._run_pipeline(RunPipelineReason.requested_by_user)
        return True

    def ensure_first_pipeline_run(self) -> bool:
        pipeline = self._get_last_pipeline()
        if pipeline:
            return False
        if self.ensure_rebase():
            return False
        self._run_pipeline(RunPipelineReason.no_pipelines_before)
        return True

    def _get_last_pipeline(self, include_skipped=False) -> Optional[Pipeline]:
        status_set = frozenset(
            s for s in PipelineStatus if include_skipped or s != PipelineStatus.skipped)
        return self._get_last_pipeline_by_status(status_set)

    @lru_cache(maxsize=16)  # Short term cache. New data is obtained for every bot "handle" call.
    def _get_last_pipeline_by_status(self, status_set: Set[PipelineStatus]) -> Optional[Pipeline]:
        pipeline_ids = [
            p['id'] for p in self._mr.raw_pipelines_list()
            if Pipeline.translate_status(p["status"]) in status_set]
        if not pipeline_ids:
            return None

        pipeline_id = max(pipeline_ids)
        return self._gitlab.get_pipeline(project_id=self._mr.project_id, pipeline_id=pipeline_id)

    def ensure_pipeline_rerun(self) -> bool:
        pipeline = self._get_last_pipeline()
        if not pipeline:
            return False

        changes = self._difference_to_previous_state(pipeline.sha)
        if changes.not_changed:
            return False

        if changes.mr_diff_changed:
            if self.ensure_rebase():
                return False
            self._run_pipeline(RunPipelineReason.mr_updated, changes)
            return True

        assert changes.is_rebased, f"Unexpected MR changes status: {changes}."

        # Re-run pipeline after rebase only if last pipeline failed (we assume that rebase by
        # itself can't break the build) and all threads are resolved (since if they are not,
        # probably some changes will be added and we will have to re-run pipeline after that)
        if pipeline.status == PipelineStatus.failed and self._mr.blocking_discussions_resolved:
            if self.ensure_rebase():
                return False
            self._run_pipeline(RunPipelineReason.mr_rebased, changes)
            return True

        return False

    def _difference_to_previous_state(self, sha: str) -> MergeRequestChanges:
        if sha == self._mr.sha:
            return MergeRequestChangesSameSha()

        commit_message_for_sha = self._get_commit_message(sha)
        is_message_changed = commit_message_for_sha != self.last_commit_message()

        diff_for_sha = self._get_commit_diff_hash(sha)
        diff_for_current_sha = self._get_commit_diff_hash(self._mr.sha)
        if diff_for_sha != diff_for_current_sha:
            return MergeRequestChangesDiffHashChanged(is_message_changed=is_message_changed)

        return MergeRequestChangesRebased(is_message_changed=is_message_changed)

    def last_commit_message(self):
        return self._get_commit_message(self._mr.sha)

    def _get_commit_message(self, sha: str):
        return self._get_project().get_commit_message(sha)

    def _get_commit_diff_hash(self, sha: str):
        return self._get_project().get_commit_diff_hash(sha, include_line_numbers=False)

    def ensure_rebase(self) -> bool:
        full_mr_data = self._get_project().get_raw_mr_by_id(
            self._mr.id, include_diverged_commits_count=True)

        if full_mr_data.diverged_commits_count:
            self._mr.rebase()
            return True

        return False

    @property
    def rebase_in_progress(self):
        return self._mr.rebase_in_progress

    def ensure_authorized_approvers(self, approvers: Set[str]) -> bool:
        current_approvers = self._mr.assignees | self._mr.reviewers | set([self._mr.author_name])
        if current_approvers.intersection(approvers):
            return False

        assignee_ids = []
        project = self._get_project()
        updated_assignees = self._mr.assignees | approvers
        for assignee in updated_assignees:
            assignee_ids += project.get_user_ids(assignee)

        self._mr.set_assignees_by_ids(set(assignee_ids))

        # We've added someone to the authorized approvers list, so we should increase needed
        # approval count for the MR.
        self._mr.set_approvers_count(self._mr.get_approvers_count() + 1)

        self._add_comment(
            title="Update assignee list",
            message=robocat.comments.authorized_approvers_assigned.format(
                approvers=", @".join(approvers)),
            emoji=AwardEmojiManager.NOTIFICATION_EMOJI)

        return True

    def _get_project(self, project_id: Optional[int] = None, lazy: bool = True):
        if project_id is None:
            return self._gitlab.get_project(self._mr.project_id, lazy)
        return self._gitlab.get_project(project_id, lazy)

    def _run_pipeline(self, reason, details=None):
        logger.info(f"{self._mr}: Running pipeline ({reason})")

        running_pipeline = self._get_last_pipeline_by_status(frozenset([PipelineStatus.running]))
        if running_pipeline:
            running_pipeline.stop()

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
        self._get_last_pipeline_by_status.cache_clear()

    def _create_mr_pipeline(self):
        self._gitlab.create_detached_pipeline(project_id=self._mr.project_id, mr_id=self._mr.id)
        self._get_last_pipeline_by_status.cache_clear()
        return self._get_last_pipeline(include_skipped=True)

    def return_to_development(self, reason, *params) -> None:
        logger.info(f"{self}: Marking as Draft: {reason}")

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
        elif reason == ReturnToDevelopmentReason.bad_project_list:
            title = "No supported project found"
            message = robocat.comments.no_supported_jira_projects % params
        else:
            assert False, f"Unknown reason: {reason}"

        self._mr.set_draft_flag()
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
        if self._mr.is_merged:
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

    def create_thread(
            self, title, message, emoji,
            message_id: MessageId = None, message_data: Dict[str, Any] = None,
            file: str = None, line: int = None, autoresolve: bool = False) -> bool:
        if file is not None and line is not None:
            latest_diff = self._mr.latest_diff()
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

        body = robocat.comments.template.format(
            title=title, message=message, emoji=emoji,
            revision=automation_tools.bot_info.revision())
        if message_id:
            body += Note.format_details_string(
                message_id=message_id, sha=self._mr.sha, data=message_data)
        return self._mr.create_discussion(body=body, position=position, autoresolve=autoresolve)

    def is_followup(self):
        if self._mr.award_emoji.find(AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI, own=True):
            return True

        if self._mr.description and self._FOLLOWUP_DESCRIPTION_RE.search(self._mr.description):
            return True

        if any(c for c in self._mr.commits() if self._FOLLOWUP_DESCRIPTION_RE.search(c.message)):
            return True

        return False

    def add_followup_creation_comment(self, followup: FollowupCreationResult):
        self._add_comment(followup.title, followup.message, followup.emoji)

    def get_merged_commits(self) -> List[str]:
        if not self._mr.is_merged:
            return []

        if self._mr.squash_commit_sha is not None:
            return [self._mr.squash_commit_sha[0:12]]

        return [c.id[0:12] for c in self._mr.commits()]

    def add_workflow_error_info(self, error: Comment = None, title: str = ""):
        self._add_comment(
            title=title,
            message=robocat.comments.workflow_error_message.format(error=error.text),
            emoji=AwardEmojiManager.BAD_ISSUE_EMOJI,
            message_id=error.id)
        self._mr.award_emoji.create(AwardEmojiManager.BAD_ISSUE_EMOJI)

    def ensure_no_workflow_errors(self):
        if self._mr.award_emoji.delete(AwardEmojiManager.BAD_ISSUE_EMOJI, own=True):
            self._add_comment(
                title="Workflow errors are fixed",
                message=robocat.comments.workflow_no_errors_message,
                emoji=AwardEmojiManager.AUTOCHECK_OK_EMOJI,
                message_id=MessageId.WorkflowOk)

    def squash_locally_if_needed(self, repo: automation_tools.git.Repo):
        if not self._mr.squash or len(list(self._mr.commits())) <= 1:
            return

        approved_by = self._mr.approved_by()
        logger.debug(f"{self}: squashing locally; approved_by {approved_by!r}")
        project = self._get_project(self._mr.source_branch_project_id, lazy=False)
        latest_diff = self._mr.latest_diff()
        commit_message = f"{self._mr.title}\n\n{self._mr.description}"
        mr_author = self._gitlab.get_git_user_info_by_username(self._mr.author_name)
        try:
            repo.squash(
                remote=project.namespace, url=project.ssh_url, branch=self._mr.source_branch,
                message=commit_message, base_sha=latest_diff.base_commit_sha, author=mr_author)
        except git.BadName as exc:
            remote_url = f"{project.ssh_url}:{project.namespace}"
            logger.warning(
                f"{self}: Cannot squash commits locally: {exc}. Most likely there is no "
                f"{self._mr.source_branch!r} branch in {remote_url!r}")
            self._add_comment(
                "Cannot squash locally", robocat.comments.cannot_squash_locally,
                AwardEmojiManager.LOCAL_SQUASH_PROBLEMS_EMOJI)
            return

        if not self._restore_approvements(approvers=approved_by):
            logger.warning(f"{self}: Cannot re-approve merge request.")
            self._add_comment(
                "Cannot restore approvals",
                robocat.comments.cannot_restore_approvals.format(
                    approvers=f"@{', @'.join(approved_by)}"),
                AwardEmojiManager.LOCAL_SQUASH_PROBLEMS_EMOJI)

    def _restore_approvements(self, approvers: Set[str], first_try_delay_s: int = 5) -> bool:
        """This function restores approvements for the Merge Requests. The presupposition is that

        no user from the list passed via the `approvers` parameter has approved this Merge Request
        yet. This presupposition may be false due to the race condition. To address this issue, if
        the function fails to restore approvement, it tries to do this again after timeout. Also
        the function has an overall timeout to prevent the situation of endless retries. If the
        function fails to restore some of the approvements, it checks if the Merge Request already
        has all the approvements by the users listed in `approvers` parameter and returns the
        result of the check. Otherwise (if all API calls return "OK" status) it returns true.
        """

        start_time_s = time.time()
        if first_try_delay_s:
            time.sleep(first_try_delay_s)

        is_ok = True
        for user_name in approvers:
            logger.debug(f"{self}: approving on behalf of {user_name!r}")
            user_gitlab = self._gitlab.get_gitlab_object_for_user(user_name)
            user_project = user_gitlab.get_project(self._mr.project_id)
            mr = MergeRequest(user_project.get_raw_mr_by_id(self._mr.id), user_name)
            is_ok &= self._try_set_approve(mr, start_time_s)

        return is_ok or approvers <= self._mr.approved_by()

    @staticmethod
    def _try_set_approve(mr: MergeRequest, start_time_s: float) -> bool:
        max_approve_restore_timeout_s = 30
        retry_timeout_s = 5

        while True:
            try:
                mr.approve()
                break
            except gitlab.exceptions.GitlabAuthenticationError:
                # Gitlab bug: if the Merge Request is already approved by some user, the API
                # returns error 401 in response for the "approve" call from the same user.
                pass

            if time.time() - start_time_s > max_approve_restore_timeout_s:
                return False
            time.sleep(retry_timeout_s)

        return True

    def notes(self, bot_only: bool = True) -> List[Note]:
        all_notes = [Note(note_data) for note_data in self._mr.notes_data()]
        if bot_only and self._current_user:
            return [n for n in all_notes if n.author == self._current_user]
        return all_notes

    def add_issue_not_finalized_notification(self, issue_key: str):
        message = robocat.comments.issue_is_not_finalized.format(issue_key=issue_key)
        self._add_comment(
          "Issue was not moved to QA/Closed",
          message,
          emoji=AwardEmojiManager.ISSUE_NOT_MOVED_TO_QA_EMOJI,
          message_id=MessageId.FollowUpIssueNotMovedToQA)

    def last_pipeline_check_job_status(self, job_name: str) -> Optional[JobStatus]:
        pipeline = self._get_last_pipeline(include_skipped=True)
        for j in pipeline.jobs():
            if j.name != job_name:
                continue
            return JobStatus(j.status)
        return None
