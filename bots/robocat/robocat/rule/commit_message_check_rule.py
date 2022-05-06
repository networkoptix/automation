import logging
import re
from typing import Dict, List, Set, Tuple
from dataclasses import asdict
from enum import Enum

from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
import robocat.rule.helpers.approve_rule_helpers as approve_rule_helpers
import robocat.rule.helpers.commit_message_checker as commit_message_checker
from robocat.rule.helpers.statefull_checker_helpers import (
    CheckChangesMixin,
    ErrorCheckResult,
    StoredCheckResults)
from robocat.award_emoji_manager import AwardEmojiManager
import robocat.comments

logger = logging.getLogger(__name__)


class CommitMessageCheckRuleExecutionResultClass(RuleExecutionResultClass, Enum):
    def __bool__(self):
        return self in [
            self.not_applicable, self.merge_authorized, self.merged, self.commit_message_is_ok]


class CommitMessageStoredCheckResults(StoredCheckResults):
    CheckErrorClass = commit_message_checker.CommitMessageError

    ERROR_MESSAGE_IDS = {
        MessageId.BadCommitMessageByKeeper,
        MessageId.BadCommitMessage,
    }
    OK_MESSAGE_IDS = {
        MessageId.CommitMessageIsOk,
    }
    UNCHECKABLE_MESSAGE_IDS = set()
    NEEDS_MANUAL_CHECK_MESSAGE_IDS = set()


class CommitMessageCheckRule(CheckChangesMixin, BaseRule):
    ExecutionResult = CommitMessageCheckRuleExecutionResultClass.create(
        "CommitMessageCheckRuleExecutionResult", {
            "merge_authorized": "MR is approved by the authorized approver",
            "not_applicable": "No changes in open source files",
            "commit_message_not_ok": "Commit message contains bad words",
            "commit_message_is_ok": "Commit message check didn't find any problems",
        })

    def __init__(self, approve_rules: List[Dict[str, List[str]]]):
        self._approve_rules = []
        for rule_dict in approve_rules:
            self._approve_rules.append(approve_rule_helpers.ApproveRule(
                approvers=rule_dict["approvers"], patterns=rule_dict["patterns"]))
        logger.info(
            f"Commit message check rule created. Approvers list is {self._approve_rules!r}")
        super().__init__()

    def execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        logger.debug(f"Executing check commit message rule on {mr_manager}...")

        mr_data = mr_manager.data
        preliminary_check_result = self.preliminary_check_result(mr_data)
        if preliminary_check_result != self.ExecutionResult.preliminary_check_passed:
            return preliminary_check_result

        if not self._has_changes_in_open_source(mr_manager):
            return self.ExecutionResult.not_applicable

        error_check_result = self._do_error_check(
            mr_manager=mr_manager, check_results_class=CommitMessageStoredCheckResults)

        if error_check_result.has_errors:
            self._ensure_problem_comments(mr_manager, error_check_result)
            approval_requirements = approve_rule_helpers.get_approval_requirements(
                approve_rules=self._approve_rules, mr_manager=mr_manager)
            if mr_manager.satisfies_approval_requirements(approval_requirements):
                return self.ExecutionResult.merge_authorized
            preferred_approvers = approve_rule_helpers.get_keepers(
                approve_rules=self._approve_rules, mr_manager=mr_manager, for_affected_files=True)
            if mr_manager.ensure_authorized_approvers(preferred_approvers):
                logger.debug(f"{mr_manager}: Preferred approvers assigned to MR.")
            return self.ExecutionResult.commit_message_not_ok

        self._ensure_problems_not_found_comment(mr_manager, error_check_result)
        return self.ExecutionResult.commit_message_is_ok

    def _has_changes_in_open_source(self, mr_manager: MergeRequestManager) -> bool:
        # We rely on the pipeline check here: if the job for open-source check is not created
        # we assume that there are no changes in the open-source part of the project.
        open_source_check_result = mr_manager.last_pipeline_check_job_status("open-source:check")
        return open_source_check_result is not None

    def _find_errors(
            self,
            old_errors_info: StoredCheckResults,
            mr_manager: MergeRequestManager) -> commit_message_checker.FindErrorsResult:
        has_errors = False
        new_errors = set()

        commit_message_errors = commit_message_checker.commit_message_errors(
            mr_manager.last_commit_message())

        for error in commit_message_errors:
            has_errors = True
            if not old_errors_info.have_error(error=error):
                new_errors.add(error)

        return (has_errors, new_errors)

    def _ensure_problem_comments(
            self, mr_manager: MergeRequestManager, error_check_result: ErrorCheckResult):
        if not error_check_result.must_add_comment:
            return
        for error in error_check_result.new_errors:
            self._create_commit_message_discussion(mr_manager, error)

    def _create_commit_message_discussion(
            self,
            mr_manager: MergeRequestManager,
            error: commit_message_checker.CommitMessageError):
        title = "Commit message auto-check failed"

        if approve_rule_helpers.is_mr_author_keeper(self._approve_rules, mr_manager):
            message = robocat.comments.bad_commit_message_from_authorized_approver.format(
                error_message=error.raw_text)
            message_id = MessageId.BadCommitMessageByKeeper
        else:
            keepers = approve_rule_helpers.get_keepers(
                approve_rules=self._approve_rules, mr_manager=mr_manager, for_affected_files=True)
            message = robocat.comments.bad_commit_message.format(
                error_message=error.raw_text,
                approvers=", @".join(keepers))
            message_id = MessageId.BadCommitMessage

        mr_manager.create_thread(
            title=title,
            message=message,
            message_id=message_id,
            message_data=asdict(error),
            emoji=AwardEmojiManager.AUTOCHECK_FAILED_EMOJI)

    def _ensure_problems_not_found_comment(
            self, mr_manager: MergeRequestManager, error_check_result: ErrorCheckResult):
        if not error_check_result.must_add_comment:
            return

        mr_manager.create_thread(
            title="Commit auto-check passed",
            message=robocat.comments.commit_message_is_ok,
            message_id=MessageId.CommitMessageIsOk,
            emoji=AwardEmojiManager.AUTOCHECK_OK_EMOJI,
            autoresolve=True)
