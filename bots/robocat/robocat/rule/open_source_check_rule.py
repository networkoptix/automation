import logging
import re
from typing import Dict, List, Set, Tuple
from dataclasses import asdict
from enum import Enum

from robocat.merge_request_manager import MergeRequestManager, ApprovalRequirements
from robocat.note import MessageId
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
import robocat.rule.helpers.approve_rule_helpers as approve_rule_helpers
import robocat.rule.helpers.open_source_file_checker as open_source_file_checker
from robocat.rule.helpers.statefull_checker_helpers import (
    CheckChangesMixin,
    ErrorCheckResult,
    StoredCheckResults)
from robocat.award_emoji_manager import AwardEmojiManager
import robocat.comments

logger = logging.getLogger(__name__)


class OpenSourceCheckRuleExecutionResultClass(RuleExecutionResultClass, Enum):
    def __bool__(self):
        return self in [
            self.not_applicable, self.merge_authorized, self.merged, self.no_manual_check_required]


class OpenSourceStoredCheckResults(StoredCheckResults):
    CheckErrorClass = open_source_file_checker.FileError

    ERROR_MESSAGE_IDS = {
        MessageId.OpenSourceHasBadChangesFromKeeper,
        MessageId.OpenSourceHasBadChangesCallKeeperMandatory,
        MessageId.OpenSourceHasBadChangesCallKeeperOptional,
    }
    OK_MESSAGE_IDS = {
        MessageId.OpenSourceNoProblemNeedApproval,
        MessageId.OpenSourceNoProblemAutoApproved,
    }
    UNCHECKABLE_MESSAGE_IDS = {
        MessageId.OpenSourceHugeDiffNeedsManualCheck,
        MessageId.OpenSourceHugeDiffCallKeeper,
    }
    NEEDS_MANUAL_CHECK_MESSAGE_IDS = {
        MessageId.OpenSourceHugeDiffNeedsManualCheck,
        MessageId.OpenSourceHugeDiffCallKeeper,
        MessageId.OpenSourceHasBadChangesCallKeeperMandatory,
        MessageId.OpenSourceNoProblemNeedApproval,
    }


class OpenSourceCheckRule(CheckChangesMixin, BaseRule):
    ExecutionResult = OpenSourceCheckRuleExecutionResultClass.create(
        "OpenSourceCheckRuleExecutionResult", {
            "merge_authorized": "MR is approved by the authorized approver",
            "not_applicable": "No changes in open source files",
            "files_not_ok": (
                "Open source files do not comply with the requirements, or the change list is too "
                "large"),
            "manual_check_required": (
                "Open source rule check didn't find any problems; manual check is required"),
            "no_manual_check_required": (
                "Open source rule check didn't find any problems; no manual check is required"),
        })

    def __init__(self, project_manager, approve_rules: List[Dict[str, List[str]]]):
        self._approve_rules = []
        for rule_dict in approve_rules:
            self._approve_rules.append(approve_rule_helpers.ApproveRule(
                approvers=rule_dict["approvers"], patterns=rule_dict["patterns"]))
        logger.info(f"Open source rule created. Approvers list is {self._approve_rules!r}")
        self._project_manager = project_manager
        super().__init__()

    def execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        logger.debug(f"Executing check open sources rule on {mr_manager}...")

        mr_data = mr_manager.data
        preliminary_check_result = self.preliminary_check_result(mr_data)
        if preliminary_check_result != self.ExecutionResult.preliminary_check_passed:
            return preliminary_check_result

        has_changed_open_source_files = any(
            open_source_file_checker.changed_open_source_files(mr_manager))
        if self._is_diff_complete(mr_manager) and not has_changed_open_source_files:
            return self.ExecutionResult.not_applicable

        error_check_result = self._do_error_check(
            mr_manager=mr_manager, check_results_class=OpenSourceStoredCheckResults)

        keepers = approve_rule_helpers.get_all_open_source_keepers(self._approve_rules)
        logger.debug(f"{mr_manager}: Authorized approvers are {keepers!r}")
        approval_requirements = ApprovalRequirements(authorized_approvers=keepers)

        if self._is_manual_check_required(mr_manager):
            # MR can be approved by anybody from the authorized_approvers set, but we assign to the
            # MR only those who are the best choice for approving this particular MR.
            preferred_approvers = self._get_keepers_by_changed_files(mr_manager)
            if mr_manager.ensure_authorized_approvers(preferred_approvers):
                logger.debug(f"{mr_manager}: Preferred approvers assigned to MR.")

        if self._are_problems_found(mr_manager, error_check_result):
            self._ensure_problem_comments(mr_manager, error_check_result)
            if mr_manager.satisfies_approval_requirements(approval_requirements):
                return self.ExecutionResult.merge_authorized
            return self.ExecutionResult.files_not_ok

        self._ensure_problems_not_found_comment(mr_manager, error_check_result)
        if self._is_manual_check_required(mr_manager):
            if mr_manager.satisfies_approval_requirements(approval_requirements):
                return self.ExecutionResult.merge_authorized
            return self.ExecutionResult.manual_check_required

        return self.ExecutionResult.no_manual_check_required

    def _find_errors(
            self,
            old_errors_info: OpenSourceStoredCheckResults,
            mr_manager: MergeRequestManager) -> Tuple[bool, open_source_file_checker.FileErrors]:
        has_errors = False
        new_errors = set()

        for file_name in open_source_file_checker.changed_open_source_files(mr_manager):
            file_content = self._project_manager.file_get_content(
                sha=mr_manager.data.sha, file=file_name)
            file_errors = open_source_file_checker.file_errors(
                file_name=file_name, file_content=file_content)
            for error in file_errors:
                has_errors = True
                if not old_errors_info.have_error(error=error):
                    new_errors.add(error)

        return (has_errors, new_errors)

    @staticmethod
    def _has_new_open_source_files(mr_manager) -> bool:
        changes = mr_manager.get_changes()
        new_paths = [c["new_path"] for c in changes.changes if c["new_file"] or c["renamed_file"]]
        return any(p for p in new_paths if open_source_file_checker.is_check_needed(p))

    def _is_manual_check_required(self, mr_manager: MergeRequestManager) -> bool:
        if not self._is_diff_complete(mr_manager):
            return True

        if self._has_new_open_source_files(mr_manager) and not mr_manager.is_followup():
            return True

        return False

    def _are_problems_found(
            self, mr_manager: MergeRequestManager, error_check_result: ErrorCheckResult) -> bool:
        if not self._is_diff_complete(mr_manager):
            return True
        return error_check_result.has_errors

    def _ensure_problem_comments(
            self, mr_manager: MergeRequestManager, error_check_result: ErrorCheckResult):
        if not error_check_result.must_add_comment:
            return

        keepers = self._get_keepers_by_changed_files(mr_manager)
        is_author_authorized_approver = (mr_manager.data.author_name in keepers)
        if not self._is_diff_complete(mr_manager):
            if is_author_authorized_approver:
                message = robocat.comments.check_changes_manually
                message_id = MessageId.OpenSourceHugeDiffNeedsManualCheck
            else:
                message = robocat.comments.may_have_changes_in_open_source.format(
                    approvers=", @".join(keepers))
                message_id = MessageId.OpenSourceHugeDiffCallKeeper
            mr_manager.create_thread(
                title="Can't auto-check open source changes",
                message=message,
                message_id=message_id,
                emoji=AwardEmojiManager.AUTOCHECK_IMPOSSIBLE_EMOJI)
            return

        for error in error_check_result.new_errors:
            self._create_open_source_discussion(mr_manager, error)

    def _create_open_source_discussion(
            self, mr_manager: MergeRequestManager, error: open_source_file_checker.FileError):
        title = "Autocheck for open source changes failed"
        message_template = f"bad_open_source_{error.type}"

        keepers = self._get_keepers_by_changed_files(mr_manager)
        is_author_authorized_approver = (mr_manager.data.author_name in keepers)
        if is_author_authorized_approver:
            message = robocat.comments.has_bad_changes_from_authorized_approver.format(
                error_message=robocat.comments.__dict__[message_template].format(**error.params))
            message_id = MessageId.OpenSourceHasBadChangesFromKeeper
        elif self._has_new_open_source_files(mr_manager):
            message = robocat.comments.has_bad_changes_in_open_source.format(
                error_message=robocat.comments.__dict__[message_template].format(**error.params),
                approvers=", @".join(keepers))
            message_id = MessageId.OpenSourceHasBadChangesCallKeeperMandatory
        else:
            message = robocat.comments.has_bad_changes_in_open_source_optional_approval.format(
                error_message=robocat.comments.__dict__[message_template].format(**error.params),
                approvers=", @".join(keepers))
            message_id = MessageId.OpenSourceHasBadChangesCallKeeperOptional

        discussion_created = mr_manager.create_thread(
            title=title,
            message=message,
            message_id=message_id,
            message_data=asdict(error),
            emoji=AwardEmojiManager.AUTOCHECK_FAILED_EMOJI,
            file=error.file, line=error.line)

        # If the API call failed to create discussion bonded to the file and line number, we are
        # creating the discussion that is not bonded to the concrete position. TODO: Fix this
        # behavior. We must find the way to reliably create discussion, bonded to the file and line
        # number. See also comment in merge_request.py, function create_discussion().
        if not discussion_created:
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

        keepers = self._get_keepers_by_changed_files(mr_manager)
        is_author_authorized_approver = (mr_manager.data.author_name in keepers)
        if self._is_manual_check_required(mr_manager) and not is_author_authorized_approver:
            message = robocat.comments.has_good_changes_in_open_source.format(
                approvers=", @".join(keepers))
            autoresolve = False
            message_id = MessageId.OpenSourceNoProblemNeedApproval
        else:
            message = robocat.comments.has_unimportant_changes_in_open_source
            autoresolve = True
            message_id = MessageId.OpenSourceNoProblemAutoApproved

        mr_manager.create_thread(
            title="Auto-check for open-source changes passed",
            message=message,
            message_id=message_id,
            emoji=AwardEmojiManager.AUTOCHECK_OK_EMOJI,
            autoresolve=autoresolve)

    def _get_keepers_by_changed_files(self, mr_manager: MergeRequestManager) -> Set[str]:
        changed_files = list(open_source_file_checker.changed_open_source_files(mr_manager))
        return approve_rule_helpers.get_open_source_keepers_for_files(
            files=changed_files, approve_rules=self._approve_rules)
