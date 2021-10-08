import logging
from enum import Enum

from automation_tools.checkers.checkers import (
    WrongVersionChecker, IssueIgnoreLabelChecker, IssueIgnoreProjectChecker)
from robocat.rule.base_rule import BaseRule, RuleExecutionResult
from robocat.merge_request_manager import MergeRequestManager
from automation_tools.jira import JiraAccessor

logger = logging.getLogger(__name__)


class JiraIssueCheckRuleExecutionResult(RuleExecutionResult, Enum):
    merged = "MR is already merged"
    rule_execution_successfull = "Jira Issues are ok"
    rule_execution_failed = "Problems with attached Jira Issues"
    no_commits = "No commits"
    work_in_progress = "Work in progress"

    def __bool__(self):
        return self in [self.rule_execution_successfull, self.merged]


class JiraIssueCheckRule(BaseRule):
    def __init__(self, jira: JiraAccessor):
        self._jira = jira
        super().__init__()

    def execute(self, mr_manager: MergeRequestManager) -> JiraIssueCheckRuleExecutionResult:
        logger.debug(f"Executing Jira Issue check rule with {mr_manager}...")

        mr_data = mr_manager.data
        if mr_data.is_merged:
            return JiraIssueCheckRuleExecutionResult.merged

        if not mr_data.has_commits:
            return JiraIssueCheckRuleExecutionResult.no_commits

        if mr_data.work_in_progress:
            return JiraIssueCheckRuleExecutionResult.work_in_progress

        jira_issue_errors = []

        jira_issue_keys = mr_manager.data.issue_keys
        if not jira_issue_keys:
            logger.warning(
                f"{mr_manager}: Can't detect attached Jira Issue for the merge request.")
            jira_issue_errors = ["Merge Request must be related to at least one Jira Issue"]

        jira_issue_branches = {}
        self._jira.get_issue.cache_clear()
        for issue_key in jira_issue_keys:
            issue = self._jira.get_issue(issue_key)
            if IssueIgnoreLabelChecker().run(issue) or IssueIgnoreProjectChecker().run(issue):
                continue

            version_error_string = WrongVersionChecker().run(issue)
            if version_error_string:
                jira_issue_errors.append(
                    f"Bad `fixVersions` field in the related Jira Issue {issue_key}: "
                    f"{version_error_string}")

            first_found_issue_data = jira_issue_branches.setdefault(
                issue.project,
                {"key": issue_key, "branches": issue.branches(), "fixVersions": issue.fixVersions})
            if first_found_issue_data["branches"] != issue.branches():
                jira_issue_errors.append(
                    f"{issue_key}: `fixVersions` is inconsistent with `fixVersions` of "
                    f"{first_found_issue_data['key']}: {issue.fixVersions!r} != "
                    f"{first_found_issue_data['fixVersions']!r}.")

        if jira_issue_errors:
            mr_manager.ensure_jira_issue_errors_info(errors=jira_issue_errors)
            return JiraIssueCheckRuleExecutionResult.rule_execution_failed

        mr_manager.ensure_jira_issue_errors_info(errors=[])
        return JiraIssueCheckRuleExecutionResult.rule_execution_successfull
