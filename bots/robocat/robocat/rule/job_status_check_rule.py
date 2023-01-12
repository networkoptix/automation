from enum import Enum
import logging
from typing import Dict, List, Set

from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId
from robocat.pipeline import JobStatus
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
import robocat.rule.helpers.approve_rule_helpers as approve_rule_helpers
from robocat.rule.helpers.stateful_checker_helpers import (
    CheckError,
    CheckChangesMixin,
    ErrorCheckResult,
    StoredCheckResults)
logger = logging.getLogger(__name__)


class JobStatusCheckRuleExecutionResultClass(RuleExecutionResultClass, Enum):
    def __bool__(self):
        return self in [
            self.merge_authorized,
            self.merged,
            self.checks_passed,
        ]


class JobStatusStoredCheckResults(StoredCheckResults):
    MESSAGE_IDS = {
        MessageId.JobStatusChecksPassed,
        MessageId.JobStatusCheckNeedsApproval,
    }
    OR_MESSAGE_IDS = {MessageId.JobStatusChecksPassed}


class JobStatusCheckRule(CheckChangesMixin, BaseRule):
    ExecutionResult = JobStatusCheckRuleExecutionResultClass.create(
        "JobStatusCheckRuleExecutionResult", {
            "merge_authorized": "MR is approved by the authorized approvers",
            "manual_check_mandatory": "Manual check is mandatory",
            "checks_passed": (
                "Job status check rule didn't find any problems; no manual check is required"),
            "in_progress": "Check is not finished yet",
        })
    CHECK_NOT_FINISHED = "check_not_finished"
    HAS_NEW_OPEN_SOURCE_FILES_ISSUE = "open_source_has_new_files"
    HAS_OPEN_SOURCE_ISSUES_ISSUE = "open_source_issues"
    HAS_APIDOC_CHANGES_ISSUE = "apidoc_related_changes"

    JOB_NAME_BY_ISSUE_TYPE = {
        HAS_OPEN_SOURCE_ISSUES_ISSUE: "open-source:check",
        HAS_NEW_OPEN_SOURCE_FILES_ISSUE: "new-open-source-files:check",
        HAS_APIDOC_CHANGES_ISSUE: "apidoc:check",
    }
    ISSUES_REQUIRING_MANUAL_CHECK = {HAS_NEW_OPEN_SOURCE_FILES_ISSUE, HAS_APIDOC_CHANGES_ISSUE}

    def __init__(
            self,
            project_manager,
            open_source_approve_ruleset: approve_rule_helpers.ApproveRuleset,
            apidoc_changes_approve_ruleset: approve_rule_helpers.ApproveRuleset):
        open_source_relevance_checker = getattr(
            approve_rule_helpers, open_source_approve_ruleset["relevance_checker"])
        apidoc_changes_relevance_checker = getattr(
            approve_rule_helpers, apidoc_changes_approve_ruleset["relevance_checker"])
        self._approve_rules = {
            self.HAS_NEW_OPEN_SOURCE_FILES_ISSUE:
                [
                    approve_rule_helpers.ApproveRule(
                        approvers=rule["approvers"],
                        patterns=rule["patterns"],
                        relevance_checker=open_source_relevance_checker)
                    for rule in open_source_approve_ruleset["rules"]
                ],
            self.HAS_APIDOC_CHANGES_ISSUE:
                [
                    approve_rule_helpers.ApproveRule(
                        approvers=rule["approvers"],
                        patterns=rule["patterns"],
                        relevance_checker=apidoc_changes_relevance_checker)
                    for rule in apidoc_changes_approve_ruleset["rules"]
                ],
        }

        logger.info("Job status check rule created.")
        self._project_manager = project_manager
        super().__init__()

    def execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        logger.debug(f"Executing job status check rule on {mr_manager}...")

        mr_data = mr_manager.data
        preliminary_check_result = self.preliminary_check_result(mr_data)
        if preliminary_check_result != self.ExecutionResult.preliminary_check_passed:
            return preliminary_check_result

        found_errors = self._do_error_check(
            mr_manager=mr_manager, check_results_class=JobStatusStoredCheckResults)

        if found_errors.has_error_of_type(self.CHECK_NOT_FINISHED):
            return self.ExecutionResult.in_progress

        if self._satisfies_approval_requirements(mr_manager, found_errors):
            return self.ExecutionResult.merge_authorized

        self._add_comments_if_needed(mr_manager, found_errors)

        if self._is_manual_check_required(mr_manager, found_errors):
            self._enforce_manual_check(mr_manager, found_errors)
            return self.ExecutionResult.manual_check_mandatory

        # If we ever have an error that prevents merging and does not result in a failed
        # pipeline, here is the place to return the false result if such error is found.

        return self.ExecutionResult.checks_passed

    def _is_manual_check_required(
            self, mr_manager: MergeRequestManager, errors: ErrorCheckResult) -> bool:
        if mr_manager.is_follow_up():
            return False

        for issue_type in self.ISSUES_REQUIRING_MANUAL_CHECK:
            if errors.has_error_of_type(issue_type):
                is_mr_author_keeper = approve_rule_helpers.is_mr_author_keeper(
                    self._approve_rules[issue_type], mr_manager)
                if not is_mr_author_keeper:
                    return True

        return False

    def _find_errors(self, mr_manager: MergeRequestManager) -> Set[CheckError]:
        job_status = {
            issue_type: mr_manager.last_pipeline_check_job_status(job_name)
            for issue_type, job_name in self.JOB_NAME_BY_ISSUE_TYPE.items()}

        # If some of the check jobs neither succeeded nor failed, then the check is not completed.
        # Enforce running these jobs and return an issue that prohibits merging.
        check_is_completed = True
        for issue_type, status in job_status.items():
            if status not in {JobStatus.succeeded, JobStatus.failed}:
                if status is None:  # No such job - skipping check.
                    continue
                job_name = self.JOB_NAME_BY_ISSUE_TYPE[issue_type]
                logger.debug(f'{mr_manager}: Trying to start "{job_name}" job.')
                mr_manager.last_pipeline_enforce_job_run(job_name)
                check_is_completed = False
        if not check_is_completed:
            return {CheckError(type=self.CHECK_NOT_FINISHED)}

        # We do not need any actions if the HAS_OPEN_SOURCE_ISSUES_ISSUE job has failed - the
        # pipeline has failed, so the Merge Request will not be merged, and the user can check the
        # error messages directly in the job result.
        return {
            CheckError(type=issue_type)
            for issue_type in self.ISSUES_REQUIRING_MANUAL_CHECK
            if job_status[issue_type] == JobStatus.failed
        }

    def _enforce_manual_check(self, mr_manager: MergeRequestManager, errors: ErrorCheckResult):
        preferred_approvers = set()
        for issue_type in self.ISSUES_REQUIRING_MANUAL_CHECK:
            if errors.has_error_of_type(issue_type):
                preferred_approvers.update(approve_rule_helpers.get_keepers(
                    approve_rules=self._approve_rules[issue_type],
                    mr_manager=mr_manager,
                    for_changed_files=True))

        if mr_manager.ensure_authorized_approvers(preferred_approvers):
            logger.debug(f"{mr_manager}: Preferred approvers assigned to MR.")

    def _satisfies_approval_requirements(self, mr_manager, errors: ErrorCheckResult) -> bool:
        result = True
        for issue_type in self.ISSUES_REQUIRING_MANUAL_CHECK:
            if not errors.has_error_of_type(issue_type):
                continue
            approval_requirements = approve_rule_helpers.get_approval_requirements(
                approve_rules=self._approve_rules[issue_type], mr_manager=mr_manager)
            result &= mr_manager.satisfies_approval_requirements(approval_requirements)

        return result

    def _add_comments_if_needed(self, mr_manager: MergeRequestManager, errors: ErrorCheckResult):
        if not errors.has_changed_since_last_check:
            return

        if not errors.current_errors:
            mr_manager.add_comment_with_message_id(message_id=MessageId.JobStatusChecksPassed)
            return

        for error in errors.new_errors:
            # Now we leave comments only for issues requiring manual check, but this can change.
            if error.type in self.ISSUES_REQUIRING_MANUAL_CHECK:
                if not self._is_manual_check_required(mr_manager, errors):
                    continue
                keepers = approve_rule_helpers.get_keepers(
                    approve_rules=self._approve_rules[error.type],
                    mr_manager=mr_manager,
                    for_changed_files=True)
                mr_manager.add_comment_with_message_id(
                    message_id=MessageId.JobStatusCheckNeedsApproval,
                    message_params={
                        "approvers": ", @".join(keepers),
                        "job_name": self.JOB_NAME_BY_ISSUE_TYPE[error.type]},
                    message_data={"type": error.type})
