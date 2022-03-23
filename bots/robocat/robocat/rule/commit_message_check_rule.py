import logging
import re
from typing import Dict, List, Set, Tuple
from dataclasses import asdict
from enum import Enum

from robocat.merge_request_manager import MergeRequestManager, ApprovalRequirements
from robocat.note import MessageId
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
import robocat.rule.helpers.approve_rule_helpers as approve_rule_helpers
import robocat.rule.helpers.commit_message_checker as commit_message_checker
import robocat.rule.helpers.open_source_file_checker as open_source_file_checker
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

        has_changed_open_source_files = any(
            open_source_file_checker.affected_open_source_files(mr_manager))
        if self._is_diff_complete(mr_manager) and not has_changed_open_source_files:
            return self.ExecutionResult.not_applicable

        error_check_result = self._do_error_check(
            mr_manager=mr_manager, check_results_class=CommitMessageStoredCheckResults)

        keepers = approve_rule_helpers.get_all_open_source_keepers(self._approve_rules)
        logger.debug(f"{mr_manager}: Authorized approvers are {keepers!r}")
        approval_requirements = ApprovalRequirements(authorized_approvers=keepers)

        if error_check_result.has_errors:
            self._ensure_problem_comments(mr_manager, error_check_result)
            if mr_manager.satisfies_approval_requirements(approval_requirements):
                return self.ExecutionResult.merge_authorized
            preferred_approvers = self._get_keepers_by_changed_files(mr_manager)
            if mr_manager.ensure_authorized_approvers(preferred_approvers):
                logger.debug(f"{mr_manager}: Preferred approvers assigned to MR.")
            return self.ExecutionResult.commit_message_not_ok

        self._ensure_problems_not_found_comment(mr_manager, error_check_result)
        return self.ExecutionResult.commit_message_is_ok

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

        keepers = self._get_keepers_by_changed_files(mr_manager)
        is_author_authorized_approver = (mr_manager.data.author_name in keepers)
        if is_author_authorized_approver:
            message = robocat.comments.bad_commit_message_from_authorized_approver.format(
                error_message=error.raw_text)
            message_id = MessageId.BadCommitMessageByKeeper
        else:
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

    def _get_keepers_by_changed_files(self, mr_manager: MergeRequestManager) -> Set[str]:
        changed_files = list(open_source_file_checker.affected_open_source_files(mr_manager))
        return approve_rule_helpers.get_open_source_keepers_for_files(
            files=changed_files, approve_rules=self._approve_rules)
