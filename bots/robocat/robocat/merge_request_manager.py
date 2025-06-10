## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from functools import lru_cache
from typing import Any, Optional
import dataclasses
import logging
import re
import time

import git
import gitlab

from automation_tools.mr_data_structures import ApprovalRequirements
from robocat.action_reasons import WaitReason, CheckFailureReason
from robocat.award_emoji_manager import AwardEmojiManager
from robocat.gitlab import Gitlab
from robocat.merge_request import MergeRequest
from robocat.note import find_first_comment, find_last_comment, MessageId, Note, NoteDetails
from robocat.pipeline import (
    Pipeline, PipelineLocation, PipelineStatus, RunPipelineReason, JobStatus)
from robocat.project import MergeRequestDiffData
import automation_tools.bot_info
import automation_tools.git
import robocat.comments

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class FollowUpCreationResult:
    branch: str
    successful: bool
    url: str = ""

    @property
    def title(self):
        if self.successful:
            return "Follow-up merge request added"
        return "Failed to add follow-up merge request"

    @property
    def message(self):
        if self.successful:
            return robocat.comments.follow_up_merge_request_message.format(
                branch=self.branch,
                url=self.url)
        return robocat.comments.failed_follow_up_merge_request_message.format(branch=self.branch)

    @property
    def emoji(self):
        if self.successful:
            return AwardEmojiManager.FOLLOWUP_CREATED_EMOJI
        return AwardEmojiManager.FOLOWUP_CREATION_FAILED_EMOJI


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
    author: automation_tools.utils.User
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
    issue_keys: list[set[str]]
    messages: list[str]


# NOTE: Hash and eq methods for this object should return different values for different object
# instances in order to lru_cache is working right.
class MergeRequestManager:
    _FOLLOWUP_DESCRIPTION_RE = re.compile(r"\(cherry picked from commit (?P<sha>[a-f0-9]{40})\)")

    def __init__(self, mr: MergeRequest, current_user: str = None):
        logger.debug(f"Initialize MR manager for {mr.id}: '{mr.title}'")
        self._mr = mr
        self._current_user = current_user
        self._gitlab = Gitlab(self._mr.raw_gitlab_object)
        self.is_just_rebased = False

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

    def get_last_pipeline_status(self) -> Optional[PipelineStatus]:
        if pipeline := self._get_last_pipeline():
            return pipeline.status
        return None

    def get_changes(self) -> MergeRequestDiffData:
        return self._get_project().get_mr_commit_changes(
            self._mr.id, self._mr.target_branch, self._mr.sha)

    def update_unfinished_post_merging_flag(self, value):
        if self.is_post_merging_unfinished():
            if not value:
                self._mr.award_emoji.delete(
                    AwardEmojiManager.UNFINISHED_POST_MERGING_EMOJI, own=False)
        else:
            if value:
                self._mr.award_emoji.create(AwardEmojiManager.UNFINISHED_POST_MERGING_EMOJI)

    def is_post_merging_unfinished(self) -> bool:
        return self._mr.award_emoji.find(AwardEmojiManager.UNFINISHED_POST_MERGING_EMOJI, own=True)

    def satisfies_approval_requirements(self, requirements: ApprovalRequirements) -> bool:
        result = True
        approvals_left = self._approvals_left()
        logger.debug(
            f"{self}: Checking approvals: "
            f"{approvals_left if approvals_left is not None else 'unknown number'} left")
        if requirements.approvals_left is not None:
            # False if approvals_left is None
            result &= approvals_left == requirements.approvals_left
        if requirements.authorized_approvers:
            approved_by = self._mr.approved_by()
            # If the Merge Request author is an authorized approver, consider this Merge Request
            # approved by authorized approver.
            if self._mr.author.username not in requirements.authorized_approvers:
                result &= bool(requirements.authorized_approvers.intersection(approved_by))

        logger.debug(f"{self}: Approval requirements check {'passed' if result else 'failed'}")
        return result

    @lru_cache(maxsize=16)  # Short term cache. New data is obtained for every bot "handle" call.
    def _approvals_left(self) -> Optional[int]:
        """Returns either the number of approvals required or None. The latter means that the data
        returned by the GitLab API is inconsistent - the value of the approvals_left field is equal
        to zero, but the value of the boolean field `approved` is False. This situation sometimes
        occurs just after a new commit is pushed to the repo."""
        mr_approvals_info = self._mr.get_approvals_info()
        if not mr_approvals_info.is_approved and mr_approvals_info.approvals_left == 0:
            return None
        return mr_approvals_info.approvals_left

    def ensure_watching(self) -> bool:
        if self._mr.award_emoji.find(AwardEmojiManager.WATCH_EMOJI, own=True):
            return False

        logger.info(f"{self}: New merge request to take care of")
        base_sha = self._mr.latest_diff().base_commit_sha if self._mr.has_commits else ""
        self._mr.award_emoji.create(AwardEmojiManager.WATCH_EMOJI)
        self.add_comment_with_message_id(
            MessageId.InitialMessage,
            message_params={
                "bot_gitlab_username": self._current_user,
                "bot_revision": automation_tools.bot_info.revision(),
                "command_list": "\n- ".join(
                    cls.description() for cls in robocat.commands.parser.command_classes()),
            },
            message_data={"base_sha": base_sha})

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

    def update_merge_base(self):
        initial_note = find_first_comment(notes=self.notes(), message_id=MessageId.InitialMessage)
        if not initial_note:
            return

        current_base_sha = self._mr.latest_diff().base_commit_sha
        if initial_note.additional_data.get("base_sha") == current_base_sha:
            return

        self.is_just_rebased = True
        comment_data = initial_note.additional_data
        comment_data["base_sha"] = current_base_sha
        self.update_comment_data(note_id=initial_note.note_id, data=comment_data)

    def _add_comment(
            self,
            title: str,
            message: str,
            emoji: str = None,
            message_id: MessageId = None,
            message_data: dict[str, Any] = None):
        logger.debug(f"{self}: Adding comment with title: {title}")
        message_params = {}
        message_params["title"] = title
        message_params["message"] = message
        if message_id:
            message_params["message"] += str(
                NoteDetails(message_id=message_id, sha=self._mr.sha, data=message_data))
        if emoji:
            message_params["emoji"] = emoji
        message_params["revision"] = automation_tools.bot_info.revision()
        self._mr.create_note(body=robocat.comments.template.format(**message_params))

    def run_user_requested_pipeline(self) -> bool:
        last_pipeline = self._get_last_pipeline()
        if last_pipeline and last_pipeline.sha == self._mr.sha:
            logger.info(f"{self._mr}: Refusing to manually run pipeline with the same sha")
            message = robocat.comments.refuse_run_pipeline_message.format(
                pipeline_id=last_pipeline.id, pipeline_url=last_pipeline.web_url, sha=self._mr.sha)
            self._add_comment(
                "Pipeline was not started", message, AwardEmojiManager.NO_PIPELINE_EMOJI)
            return False

        if self.ensure_rebase():
            return False

        # Save the confirmation that the user command was executed.
        user_command_confirmation_comment = find_last_comment(
            notes=self.notes(), message_id=MessageId.CommandRunPipeline, crash_if_not_found=True)
        comment_data = user_command_confirmation_comment.additional_data
        comment_data["CommandExecuted"] = True
        self.update_comment_data(
            note_id=user_command_confirmation_comment.note_id, data=comment_data)

        return self._run_pipeline(RunPipelineReason.requested_by_user)

    def ensure_first_pipeline_run(self) -> bool:
        logger.debug(f"{self}: Ensuring the pipeline is run at least once")
        pipeline = self._get_last_pipeline()
        if pipeline:
            logger.debug(f"{self}: Non-skipped pipelines found; do not start the pipeline")
            return False
        if self.ensure_rebase():
            logger.debug(f"{self}: Rebasing; do not start the pipeline")
            return False
        logger.debug(f"{self}: Starting the pipeline")
        return self._run_pipeline(RunPipelineReason.no_pipelines_before)

    def _get_last_pipeline(self, include_skipped=False) -> Optional[Pipeline]:
        status_set = frozenset(
            s for s in PipelineStatus if include_skipped or s != PipelineStatus.skipped)
        return self._get_last_pipeline_by_status(status_set)

    @lru_cache(maxsize=16)  # Short term cache. New data is obtained for every bot "handle" call.
    def _get_last_pipeline_by_status(self, status_set: set[PipelineStatus]) -> Optional[Pipeline]:
        last_pipeline_location, last_pipeline_time = None, ''
        for p in self._mr.raw_pipelines_list():
            if Pipeline.translate_status(p["status"]) not in status_set:
                continue
            if p["created_at"] <= last_pipeline_time:
                continue
            last_pipeline_location = PipelineLocation(
                pipeline_id=p["id"], project_id=p["project_id"])
            last_pipeline_time = p["created_at"]

        if not last_pipeline_location:
            return None

        return self._gitlab.get_pipeline(last_pipeline_location)

    def ensure_pipeline_rerun(self) -> bool:
        logger.debug(f"{self}: Re-running pipeline")
        pipeline = self._get_last_pipeline()
        if not pipeline:
            logger.debug(f"{self}: No non-skipped pipeline is found")
            return False

        changes = self._difference_to_previous_state(pipeline.sha)
        if changes.not_changed:
            logger.debug(f"{self}: Current state is not different from the previous")
            return False

        if changes.mr_diff_changed:
            logger.debug(f"{self}: MR has relevant changes")
            if self.ensure_rebase():
                logger.debug(f"{self}: Rebasing; do not start the pipeline")
                return False
            logger.debug(f"{self}: Starting the pipeline")
            return self._run_pipeline(RunPipelineReason.mr_updated, changes)

        assert changes.is_rebased, f"Unexpected MR changes status: {changes}."

        # Re-run pipeline after rebase only if last pipeline failed (we assume that rebase by
        # itself can't break the build) and all threads are resolved (since if they are not,
        # probably some changes will be added and we will have to re-run pipeline after that)
        if pipeline.status == PipelineStatus.failed and self._mr.blocking_discussions_resolved:
            logger.debug(f"{self}: Running new pipeline because previous one has failed")
            if self.ensure_rebase():
                logger.debug(f"{self}: Rebasing; do not start the pipeline")
                return False
            logger.debug(f"{self}: Starting the pipeline")
            return self._run_pipeline(RunPipelineReason.mr_rebased, changes)

        logger.debug(f"{self}: No need to start the pipeline")
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

    def ensure_authorized_approvers(self, approvers: list[set[str]]) -> bool:
        current_approvers = (
            self._mr.assignees | self._mr.reviewers | set([self._mr.author.username]))
        approvers_to_assign = set()

        # For every approval rule check if there is at least one approver already assigned to this
        # MR. If yes, then we don't need to assign any other approver for this rule.
        for approver_set in approvers:
            if not approver_set.intersection(current_approvers):
                approvers_to_assign |= approver_set

        if not approvers_to_assign:
            return False

        assignee_ids = []
        project = self._get_project()
        updated_assignees = self._mr.assignees | approvers_to_assign
        for assignee in updated_assignees:
            assignee_ids += project.get_user_ids(assignee)

        self._mr.set_assignees_by_ids(set(assignee_ids))

        # We've added someone to the authorized approvers list, so we should increase needed
        # approval count for the MR.
        self._mr.set_approvers_count(self._mr.get_approvers_count() + 1)

        self._add_comment(
            title="Update assignee list",
            message=robocat.comments.authorized_approvers_assigned.format(
                approvers=", @".join(approvers_to_assign)),
            emoji=AwardEmojiManager.NOTIFICATION_EMOJI)

        return True

    def _get_project(self, project_id: Optional[int] = None, lazy: bool = True):
        if project_id is None:
            return self._gitlab.get_project(self._mr.project_id, lazy)
        return self._gitlab.get_project(project_id, lazy)

    def _run_pipeline(self, reason, details=None) -> bool:
        logger.info(f"{self._mr}: Running pipeline ({reason})")

        running_pipeline = self._get_last_pipeline_by_status(frozenset([PipelineStatus.running]))
        pipeline_to_start = self._get_last_pipeline(include_skipped=True)

        # NOTE: There's no need to create pipelines in other cases because they are created by
        # Gitlab automatically.
        if reason == RunPipelineReason.requested_by_user:
            # Create new pipeline if the last one is not playable by Robocat.
            if not (pipeline_to_start and pipeline_to_start.is_manual):
                pipeline_to_start = self._create_mr_pipeline()

        if not (pipeline_to_start and pipeline_to_start.is_playable()):
            logger.info(
                "No pipeline ready to start is found. Probably, GitLab haven't created the "
                "pipeline for the new MR changes yet. Do nothing until this happen.")
            return False

        # To be on the safe side, first run new pipeline than cancel the old one.
        pipeline_to_start.play()
        if running_pipeline:
            running_pipeline.stop()

        reason_msg = reason.value + ("" if not details else f" ({details})")
        message = robocat.comments.run_pipeline_message.format(
            pipeline_id=pipeline_to_start.id, pipeline_url=pipeline_to_start.web_url,
            reason=reason_msg)
        self._add_comment("Pipeline started", message, AwardEmojiManager.PIPELINE_EMOJI)
        self.ensure_wait_state(None)

        # Must clear last pipeline info from the cache since it's state will probably change as a
        # result of this function run.
        self._get_last_pipeline_by_status.cache_clear()

        return True

    def _create_mr_pipeline(self):
        self._gitlab.create_detached_pipeline(project_id=self._mr.project_id, mr_id=self._mr.id)
        self._get_last_pipeline_by_status.cache_clear()
        return self._get_last_pipeline(include_skipped=True)

    def explain_check_failure(self, reason: CheckFailureReason, *params) -> None:
        logger.info(f"{self}: Add comment explaining check failure: {reason}")

        message_params: dict[str, str] = None
        if reason == CheckFailureReason.failed_pipeline:
            last_pipeline = self._get_last_pipeline()
            message_id = MessageId.FailedCheckForSuccessfulPipeline
            message_params = {
                "last_pipeline_id": str(last_pipeline.id),
                "last_pipeline_web_url": last_pipeline.web_url,
            }
        elif reason == CheckFailureReason.conflicts:
            message_id = MessageId.FailedCheckForConflictsWithTargetBranch
        elif reason == CheckFailureReason.unresolved_threads:
            message_id = MessageId.FailedCheckForUnresolvedThreads

        assert message_id is not None, f"Unknown reason: {reason}"

        existing_comment = find_last_comment(
            notes=self.notes(), message_id=message_id, condition=lambda n: n.sha == self._mr.sha)
        if not existing_comment:
            self.add_comment_with_message_id(message_id=message_id, message_params=message_params)
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
            approvals_left = (
                self._approvals_left()
                if self._approvals_left() is not None
                else 'unknown number')
            message = robocat.comments.approval_wait_message.format(approvals_left=approvals_left)
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

    def merge(self) -> bool:
        if self._mr.is_merged:
            logger.info(f"{self}: Already merged")
            return True

        logger.info(f"{self}: Trying to merge")
        try:
            self._mr.merge()
        except gitlab.exceptions.GitlabMRClosedError as e:
            # This is a workaround for unexpected "mergeable" value in "detailed_merge_status"
            # field instead of "need_rebase". TODO: Remove this as soon as possible.
            logger.info(f"{self}: Cannot merge the MR: {e}. Probably, rebase is required")
            self._mr.rebase()
            return False

        try:
            message = robocat.comments.merged_message.format(branch=self._mr.target_branch)
            self._add_comment("MR merged", message, AwardEmojiManager.MERGED_EMOJI)
        except gitlab.exceptions.GitlabError as e:
            logger.error(f"{self}: Failed to add \"MR merged\" comment: {e}")

        return True

    def create_thread(
            self,
            title: str,
            message: str,
            emoji: str,
            message_id: Optional[MessageId] = None,
            message_data: Optional[dict[str, Any]] = None,
            file: Optional[str] = None,
            line: Optional[int] = None,
            autoresolve: bool = False) -> bool:
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
            title=title,
            message=message,
            emoji=emoji,
            revision=automation_tools.bot_info.revision())
        if message_id:
            body += str(
                NoteDetails(message_id=message_id, sha=self._mr.sha, data=message_data))
        return self._mr.create_discussion(body=body, position=position, autoresolve=autoresolve)

    def is_follow_up(self):
        if self._mr.award_emoji.find(AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI, own=True):
            return True

        if self._mr.description and self._FOLLOWUP_DESCRIPTION_RE.search(self._mr.description):
            return True

        if any(c for c in self._mr.commits() if self._FOLLOWUP_DESCRIPTION_RE.search(c.message)):
            return True

        return False

    def add_follow_up_creation_comment(self, follow_up: FollowUpCreationResult):
        self._add_comment(follow_up.title, follow_up.message, follow_up.emoji)

    def get_merged_commits(self) -> list[str]:
        if not self._mr.is_merged:
            return []

        if self._mr.squash_commit_sha is not None:
            return [self._mr.squash_commit_sha[0:12]]

        return [c.id[0:12] for c in self._mr.commits()]

    def add_workflow_problem_info(self, problem: robocat.comments.Message, is_blocker: bool):
        if is_blocker:
            emoji = AwardEmojiManager.BAD_ISSUE_EMOJI
            message = robocat.comments.workflow_error_message.format(error=problem.text)
        else:
            emoji = AwardEmojiManager.SUSPICIOUS_ISSUE_EMOJI
            message = problem.text

        self.create_thread(
            title=problem.title, message=message, emoji=emoji, message_id=problem.id)

        if is_blocker:
            self._mr.award_emoji.create(AwardEmojiManager.BAD_ISSUE_EMOJI)

    def ensure_no_workflow_errors(self, error_notes: list[Note]):
        self._mr.award_emoji.delete(AwardEmojiManager.SUSPICIOUS_ISSUE_EMOJI, own=True)
        if self._mr.award_emoji.delete(AwardEmojiManager.BAD_ISSUE_EMOJI, own=True):
            self._add_comment(
                title="Workflow errors are fixed",
                message=robocat.comments.workflow_no_errors_message,
                emoji=AwardEmojiManager.AUTOCHECK_OK_EMOJI,
                message_id=MessageId.WorkflowOk)

        for note in error_notes:
            if not note.resolvable:
                continue
            assert note.discussion_id is not None
            self._mr.resolve_discussion(note.discussion_id)

    def squash_locally_if_needed(self, repo: automation_tools.git.Repo):
        if not self._mr.squash or len(list(self._mr.commits())) <= 1:
            return

        approved_by = self._mr.approved_by()
        logger.debug(f"{self}: squashing locally; approved_by {approved_by!r}")
        project = self._get_project(self._mr.source_branch_project_id, lazy=False)
        latest_diff = self._mr.latest_diff()
        commit_message = f"{self._mr.title}\n\n{self._mr.description}"
        mr_author = self._gitlab.get_git_user_info_by_username(self._mr.author.username)
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

        if not self._restore_approvals(approvers=approved_by):
            logger.warning(f"{self}: Cannot re-approve merge request.")
            self._add_comment(
                "Cannot restore approvals",
                robocat.comments.cannot_restore_approvals.format(
                    approvers=f"@{', @'.join(approved_by)}"),
                AwardEmojiManager.LOCAL_SQUASH_PROBLEMS_EMOJI)

    def _restore_approvals(self, approvers: set[str], first_try_delay_s: int = 5) -> bool:
        """This function restores approvals for the Merge Requests. The presupposition is that no
        user from the list passed via the `approvers` parameter has approved this Merge Request
        yet. This presupposition may be false due to the race condition.
        """

        if first_try_delay_s:
            time.sleep(first_try_delay_s)

        is_ok = True
        for user_name in approvers:
            logger.debug(f"{self}: approving on behalf of {user_name!r}")
            user_gitlab = self._gitlab.get_gitlab_object_for_user(user_name)
            user_project = user_gitlab.get_project(self._mr.project_id)
            mr = MergeRequest(user_project.get_raw_mr_by_id(self._mr.id), user_name)
            is_ok &= mr.ensure_approve()

        return is_ok

    def add_robocat_approval(self):
        if not self._mr.ensure_approve():
            self.add_comment_with_message_id(
                MessageId.CannotApproveAsUser,
                message_params={"username": self._current_user})

    def remove_robocat_approval(self):
        self._mr.ensure_unapprove()

    def notes(self, bot_only: bool = True) -> list[Note]:
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
        if pipeline := self._get_last_pipeline(include_skipped=True):
            if job := pipeline.get_job_by_name(job_name):
                return job.status
        return None

    def last_pipeline_enforce_job_run(self, job_name: str) -> bool:
        if pipeline := self._get_last_pipeline(include_skipped=True):
            job = pipeline.get_job_by_name(job_name)
            if job and job.status != JobStatus.running:
                pipeline.play_job(job)
                return True
        return False

    @property
    def is_mr_assigned_to_current_user(self) -> bool:
        return self._current_user in self._mr.assignees

    def add_comment_with_message_id(
            self,
            message_id: MessageId,
            message_params: dict[str, Any] = None,
            message_data: dict[str, Any] = None):
        title = robocat.comments.bot_readable_comment_title[message_id]
        emoji = AwardEmojiManager.EMOJI_BY_MESSAGE_ID.get(message_id)
        if message_params:
            message = robocat.comments.bot_readable_comment[message_id].format(**message_params)
        else:
            message = robocat.comments.bot_readable_comment[message_id]

        self._add_comment(title, message, emoji, message_id=message_id, message_data=message_data)

    def update_comment_data(self, note_id: int, data: dict[str, Any]) -> bool:
        if not (note_data := self._mr.note_data(note_id)):
            return False

        note = Note(note_data)
        note.update_details(NoteDetails(message_id=note.message_id, sha=note.sha, data=data))
        self._mr.update_note(note_id=note_id, body=note.body)
        return True

    def prepare_to_merge(self, repo: automation_tools.git.Repo) -> bool:
        if self._mr.is_merged:
            return True

        self.squash_locally_if_needed(repo)

        if self._mr.is_rebase_needed:
            self._mr.rebase()
            return False

        if self._mr.is_pipeline_run_needed:
            self._run_pipeline(RunPipelineReason.needed_by_project_settings)
            return False

        return self._mr.is_mergeable
