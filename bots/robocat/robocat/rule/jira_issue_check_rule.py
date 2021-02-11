import logging
from enum import Enum

from robocat.rule.base_rule import BaseRule, RuleExecutionResult
from robocat.merge_request_manager import MergeRequestManager
from automation_tools.jira import JiraAccessor

logger = logging.getLogger(__name__)


class JiraIssueCheckRuleExecutionResult(RuleExecutionResult, Enum):
    merged = "MR is already merged"
    rule_execution_successfull = "Jira Issues are ok"
    rule_execution_failed = "Jira Issues have problems"
    no_commits = "No commits"
    work_in_progress = "Work in progress"
    not_applicable = "Not attached to any Jira Issue"

    def __bool__(self):
        return self in [self.not_applicable, self.rule_execution_successfull, self.merged]


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

        jira_issue_keys = mr_manager.data.issue_keys
        if not jira_issue_keys:
            logger.debug(f"{mr_manager}: Can't detect attached Jira Issue for the merge request.")
            return JiraIssueCheckRuleExecutionResult.not_applicable

        jira_issue_errors = []
        self._jira.get_issue.cache_clear()
        for issue_key in jira_issue_keys:
            issue = self._jira.get_issue(issue_key)
            if issue.should_be_ignored_by_police():
                continue

            version_error_string = issue.version_set_error_string()
            if version_error_string:
                jira_issue_errors.append(f"{issue_key}: {version_error_string}")

        if jira_issue_errors:
            mr_manager.ensure_jira_issue_errors_info(errors=jira_issue_errors)
            return JiraIssueCheckRuleExecutionResult.rule_execution_failed

        mr_manager.ensure_jira_issue_errors_info(errors=[])
        return JiraIssueCheckRuleExecutionResult.rule_execution_successfull
