from enum import Enum
import logging
from typing import Dict, List, Set, Tuple

from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId
from robocat.pipeline import JobStatus
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
import robocat.rule.helpers.approve_rule_helpers as approve_rule_helpers
from robocat.rule.helpers.statefull_checker_helpers import (
    CheckError,
    CheckChangesMixin,
    ErrorCheckResult,
    StoredCheckResults)
from robocat.award_emoji_manager import AwardEmojiManager
import robocat.comments

logger = logging.getLogger(__name__)


class OpenSourceCheckRuleExecutionResultClass(RuleExecutionResultClass, Enum):
    def __bool__(self):
        return self in [
            self.not_applicable,
            self.merge_authorized,
            self.merged,
            self.checks_passed,
        ]


class OpenSourceStoredCheckResults(StoredCheckResults):
    OK_MESSAGE_IDS = {MessageId.OpenSourceNeedApproval}
    NEEDS_MANUAL_CHECK_MESSAGE_IDS = {MessageId.OpenSourceNeedApproval}


class OpenSourceCheckRule(CheckChangesMixin, BaseRule):
    ExecutionResult = OpenSourceCheckRuleExecutionResultClass.create(
        "OpenSourceCheckRuleExecutionResult", {
            "merge_authorized": "MR is approved by the authorized approver",
            "not_applicable": "No changes in open source files",
            "manual_check_mandatory": "Manual check is mandatory",
            "checks_passed": (
                "Open source rule check didn't find any problems; no manual check is required"),
            "in_progress": "Check is not finished yet",
        })
    CHECK_STATUS_NO_CHECK_NEEDED = "no_open_source_changes"
    CHECK_STATUS_NOT_FINISHED = "check_not_finished"
    CHECK_STATUS_HAS_NEW_FILES = "open_source_has_new_files"

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

        error_check_result = self._do_error_check(
            mr_manager=mr_manager, check_results_class=OpenSourceStoredCheckResults)

        if self._has_error(self.CHECK_STATUS_NO_CHECK_NEEDED, error_check_result):
            return self.ExecutionResult.not_applicable

        if self._has_error(self.CHECK_STATUS_NOT_FINISHED, error_check_result):
            return self.ExecutionResult.in_progress

        if self._satisfies_approval_requirements(mr_manager):
            return self.ExecutionResult.merge_authorized

        if self._is_manual_check_required(mr_manager):
            self._ensure_need_manual_approvement_comment(mr_manager, error_check_result)
            self._enforce_manual_check(mr_manager)
            return self.ExecutionResult.manual_check_mandatory

        if error_check_result.has_errors:
            # We never should end up here - the only error we can get now also triggers the
            # "manual check required" flag.
            # TODO: Refactor accordingly, remove this part of the code, all related parts, and
            # possibly rename the rule (to something like new_open_source_files_check_rule).
            logger.error(
                f"{mr_manager}: INTERNAL ERROR in the open source check rule.")
            return self.ExecutionResult.problems_found
        return self.ExecutionResult.checks_passed

    @staticmethod
    def _has_error(error_type: str, check_result: ErrorCheckResult) -> bool:
        return any(e for e in check_result.new_errors if e.type == error_type)

    def _is_manual_check_required(self, mr_manager: MergeRequestManager) -> bool:
        if mr_manager.is_followup():
            return False
        if approve_rule_helpers.is_mr_author_keeper(self._approve_rules, mr_manager):
            return False
        new_files_check_result = mr_manager.last_pipeline_check_job_status(
            "new-open-source-files:check")
        return new_files_check_result == JobStatus.failed

    def _find_errors(
            self,
            old_errors_info: OpenSourceStoredCheckResults,
            mr_manager: MergeRequestManager) -> Tuple[bool, Set[CheckError]]:
        errors_check_result = mr_manager.last_pipeline_check_job_status("open-source:check")
        if errors_check_result is None:
            return False, {CheckError(type=self.CHECK_STATUS_NO_CHECK_NEEDED)}

        # We need this result only to understand if all checks are completed. If not, we do not
        # leave any comment and do not allow the merge.
        new_files_check_result = mr_manager.last_pipeline_check_job_status(
            "new-open-source-files:check")

        # If some of the check jobs neither succeeded nor failed than the check is not completed.
        # Enforce running these jobs and exit prohibiting merge.

        check_is_completed = True

        if errors_check_result not in {JobStatus.succeeded, JobStatus.failed}:
            logger.debug(f'{mr_manager}: Trying to start "open-source:checK" job.')
            mr_manager.last_pipeline_enforce_job_run("open-source:check")
            check_is_completed = False

        if new_files_check_result not in {JobStatus.succeeded, JobStatus.failed}:
            logger.debug(f'{mr_manager}: Trying to start "new-open-source:checK" job.')
            mr_manager.last_pipeline_enforce_job_run("new-open-source-files:check")
            check_is_completed = False

        if not check_is_completed:
            return True, {CheckError(type=self.CHECK_STATUS_NOT_FINISHED)}

        return False, set()

    def _enforce_manual_check(self, mr_manager: MergeRequestManager):
        preferred_approvers = approve_rule_helpers.get_keepers(
            approve_rules=self._approve_rules, mr_manager=mr_manager, for_changed_files=True)
        if mr_manager.ensure_authorized_approvers(preferred_approvers):
            logger.debug(f"{mr_manager}: Preferred approvers assigned to MR.")

    def _satisfies_approval_requirements(self, mr_manager) -> bool:
        approval_requirements = approve_rule_helpers.get_approval_requirements(
            approve_rules=self._approve_rules, mr_manager=mr_manager)
        return mr_manager.satisfies_approval_requirements(approval_requirements)

    def _ensure_need_manual_approvement_comment(
            self, mr_manager: MergeRequestManager, error_check_result: ErrorCheckResult):
        if not error_check_result.must_add_comment:
            return

        if approve_rule_helpers.is_mr_author_keeper(self._approve_rules, mr_manager):
            return

        keepers = approve_rule_helpers.get_keepers(
            approve_rules=self._approve_rules,
            mr_manager=mr_manager,
            for_changed_files=True)
        mr_manager.add_comment_with_message_id(
            message_id=MessageId.OpenSourceNeedApproval,
            message_params={"approvers": ", @".join(keepers)},
            message_data={"type": self.CHECK_STATUS_HAS_NEW_FILES})
