## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Set
from automation_tools.jira import JiraAccessor

from robocat.config import ApproveRulesetEntryConfig, Config
from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId
from robocat.pipeline import JobStatus
from robocat.project_manager import ProjectManager
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
import robocat.rule.helpers.approve_rule_helpers as approve_rule_helpers
from robocat.rule.helpers.stateful_checker_helpers import (
    CheckError,
    CheckChangesMixin,
    ErrorCheckResult,
    StoredCheckResults)
from source_file_compliance import RepoCheckConfig

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
    OK_MESSAGE_IDS = {MessageId.JobStatusChecksPassed}


@dataclass
class IssueDescriptor:
    job_name: str
    ruleset: list[approve_rule_helpers.ApproveRule] = field(default_factory=list)
    requires_manual_check: bool = True
    deleted_files_affect_result: bool = False


class JobStatusCheckRule(CheckChangesMixin, BaseRule):
    identifier = "job_status"

    ExecutionResult = JobStatusCheckRuleExecutionResultClass.create(
        "JobStatusCheckRuleExecutionResult", {
            "merge_authorized": "MR is approved by the authorized approvers",
            "manual_check_mandatory": "Manual check is mandatory",
            "checks_passed": (
                "Job status check rule didn't find any problems; no manual check is required"),
            "in_progress": "Check is not finished yet",
        })
    CHECK_NOT_FINISHED = "check_not_finished"

    def __init__(self, config: Config, project_manager: ProjectManager, jira: JiraAccessor):
        super().__init__(config, project_manager, jira)

        # Always have "open_source_issue". TODO: Check, if it is needed at all, looks like now
        # all the work for this type of problems is done by the pipline job.
        self._possible_issues = {
            "open_source_issues": IssueDescriptor(
                job_name="open-source:check", requires_manual_check=False),
        }

        self._update_possible_issues(
            config=config.job_status_check_rule.open_source,
            issue_name="open_source_has_new_files",
            job_name="new-open-source-files:check")

        self._update_possible_issues(
            config=config.job_status_check_rule.apidoc,
            issue_name="apidoc_related_changes",
            job_name="apidoc:check")

        self._update_possible_issues(
            config=config.job_status_check_rule.code_owner_approval,
            issue_name="no_code_owner_approval",
            job_name="code-owner-approval:check",
            deleted_files_affect_result=True,
            separate_issues_for_rules=True)

        logger.info("Job status check rule created.")

    def _update_possible_issues(
            self,
            config: ApproveRulesetEntryConfig,
            issue_name: str,
            job_name: str,
            deleted_files_affect_result: bool = False,
            separate_issues_for_rules: bool = False):
        if not config:
            return

        issue_names = []
        rulesets = []
        relevance_checker = getattr(approve_rule_helpers, config.approve_ruleset.relevance_checker)
        if separate_issues_for_rules:
            for rule_index, rule in enumerate(config.approve_ruleset.rules):
                issue_names.append(f"{issue_name}_{rule_index}")
                rulesets.append([
                    approve_rule_helpers.ApproveRule(
                        approvers=rule.approvers,
                        patterns=rule.patterns,
                        relevance_checker=relevance_checker)])
        else:
            issue_names.append(issue_name)
            rulesets.append([
                approve_rule_helpers.ApproveRule(
                    approvers=rule.approvers,
                    patterns=rule.patterns,
                    relevance_checker=relevance_checker)
                for rule in config.approve_ruleset.rules])

        for i_name, ruleset in zip(issue_names, rulesets):
            self._possible_issues[i_name] = IssueDescriptor(
                job_name=job_name,
                deleted_files_affect_result=deleted_files_affect_result,
                ruleset=ruleset)

    def _execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
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

        if self._does_mr_require_manual_check(mr_manager, found_errors):
            self._enforce_manual_check(mr_manager, found_errors)
            return self.ExecutionResult.manual_check_mandatory

        # If we ever have an error that prevents merging and does not result in a failed
        # pipeline, here is the place to return the false result if such error is found.

        return self.ExecutionResult.checks_passed

    def _does_mr_require_manual_check(
            self, mr_manager: MergeRequestManager, errors: ErrorCheckResult) -> bool:
        if mr_manager.is_follow_up():
            return False

        for issue_type, issue_descriptor in self._issues_requiring_manual_check():
            if errors.has_error_of_type(issue_type):
                is_mr_author_keeper = approve_rule_helpers.is_mr_author_keeper(
                    approve_rules=issue_descriptor.ruleset, mr_manager=mr_manager)
                if not is_mr_author_keeper:
                    return True

        return False

    def _issues_requiring_manual_check(self) -> list[tuple[str, IssueDescriptor]]:
        return [
            (issue_name, issue_descriptor)
            for issue_name, issue_descriptor in self._possible_issues.items()
            if issue_descriptor.requires_manual_check]

    def _find_errors(self, mr_manager: MergeRequestManager) -> Set[CheckError]:
        job_status = {
            issue_type: mr_manager.last_pipeline_check_job_status(issue_descriptor.job_name)
            for issue_type, issue_descriptor in self._possible_issues.items()}

        # If some of the check jobs neither succeeded nor failed, then the check is not completed.
        # Enforce running these jobs and return an issue that prohibits merging.
        check_is_completed = True
        for issue_type, status in job_status.items():
            if status not in {JobStatus.succeeded, JobStatus.failed}:
                if status is None:  # No such job - skipping check.
                    continue
                job_name = self._possible_issues[issue_type].job_name
                logger.debug(f'{mr_manager}: Trying to start "{job_name}" job.')
                mr_manager.last_pipeline_enforce_job_run(job_name)
                check_is_completed = False
        if not check_is_completed:
            return {CheckError(type=self.CHECK_NOT_FINISHED)}

        return {
            CheckError(type=issue_type)
            for issue_type, issue_descriptor in self._issues_requiring_manual_check()
            if (
                job_status[issue_type] == JobStatus.failed
                # Do not report the issue if there are no changes in the part of the repo relevant
                # to this specific rule. Useful for the jobs that check multiple rules at once
                # (e.g. the check for code-owner approval).
                and approve_rule_helpers.get_all_relevant_files(
                    mr_manager=mr_manager, approve_rules=issue_descriptor.ruleset))
        }

    def _enforce_manual_check(self, mr_manager: MergeRequestManager, errors: ErrorCheckResult):
        authorized_approvers = []
        for issue_type, issue_descriptor in self._issues_requiring_manual_check():
            if not errors.has_error_of_type(issue_type):
                continue
            preferred_approvers = approve_rule_helpers.get_keepers(
                approve_rules=issue_descriptor.ruleset,
                mr_manager=mr_manager,
                for_changed_files=True,
                for_affected_files=issue_descriptor.deleted_files_affect_result)

            authorized_approvers.append(preferred_approvers)

        if mr_manager.ensure_authorized_approvers(authorized_approvers):
            logger.debug(f"{mr_manager}: Keepers assigned to MR (reason: {issue_type}).")

    def _satisfies_approval_requirements(self, mr_manager, errors: ErrorCheckResult) -> bool:
        for issue_type, issue_descriptor in self._issues_requiring_manual_check():
            if not errors.has_error_of_type(issue_type):
                continue
            approval_requirements = approve_rule_helpers.get_approval_requirements(
                approve_rules=issue_descriptor.ruleset, mr_manager=mr_manager)
            if not mr_manager.satisfies_approval_requirements(approval_requirements):
                return False

        return True

    def _add_comments_if_needed(self, mr_manager: MergeRequestManager, errors: ErrorCheckResult):
        if not errors.has_changed_since_last_check:
            return

        if not errors.current_errors:
            mr_manager.add_comment_with_message_id(message_id=MessageId.JobStatusChecksPassed)
            return

        for error in errors.new_errors:
            # Now we leave comments only for issues requiring manual check, but this can change.
            if error.type in [issue for (issue, _) in self._issues_requiring_manual_check()]:
                if not self._does_mr_require_manual_check(mr_manager, errors):
                    continue
                issue_descriptor = self._possible_issues[error.type]
                keepers = approve_rule_helpers.get_keepers(
                    approve_rules=issue_descriptor.ruleset,
                    mr_manager=mr_manager,
                    for_changed_files=True,
                    for_affected_files=issue_descriptor.deleted_files_affect_result)
                mr_manager.add_comment_with_message_id(
                    message_id=MessageId.JobStatusCheckNeedsApproval,
                    message_params={
                        "approvers": ", @".join(keepers),
                        "job_name": issue_descriptor.job_name,
                    },
                    message_data={"type": error.type})
