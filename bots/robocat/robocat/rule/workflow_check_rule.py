import logging
from enum import Enum
from typing import List

from automation_tools.checkers.checkers import (
    WrongVersionChecker, IssueIgnoreLabelChecker, IssueIgnoreProjectChecker)
from robocat.rule.base_rule import BaseRule, RuleExecutionResult
from robocat.merge_request_manager import MergeRequestManager, MergeRequestData
from automation_tools.jira import JiraAccessor, JiraIssue

logger = logging.getLogger(__name__)


class WorkflowCheckRuleExecutionResult(RuleExecutionResult, Enum):
    merged = "MR is already merged"
    rule_execution_successfull = "Workflow requirements are ok"
    jira_issue_problems = "Problems with attached Jira Issues"
    commit_messages_problems = "Inconsistent commit messages"
    mr_title_problem = "Merge Request title is incorrect"
    no_commits = "No commits"
    work_in_progress = "Work in progress"

    def __bool__(self):
        return self in [self.rule_execution_successfull, self.merged]


class WorkflowCheckRule(BaseRule):
    def __init__(self, jira: JiraAccessor):
        self._jira = jira
        super().__init__()

    def execute(self, mr_manager: MergeRequestManager) -> WorkflowCheckRuleExecutionResult:
        logger.debug(f"Executing Jira Issue check rule with {mr_manager}...")

        mr_data = mr_manager.data
        if mr_data.is_merged:
            return WorkflowCheckRuleExecutionResult.merged

        if not mr_data.has_commits:
            return WorkflowCheckRuleExecutionResult.no_commits

        if mr_data.work_in_progress:
            return WorkflowCheckRuleExecutionResult.work_in_progress

        self._jira.get_issue.cache_clear()

        jira_issue_errors = self._get_jira_issue_errors(mr_manager)
        if jira_issue_errors:
            mr_manager.ensure_workflow_errors_info(
                errors=jira_issue_errors, title="Jira workflow check failed")
            return WorkflowCheckRuleExecutionResult.jira_issue_problems

        actual_commit_issue_keys = self._exclude_ignored_issues(mr_data.commit_issue_keys)
        actual_issue_keys = self._exclude_ignored_issues(mr_data.issue_keys)
        if set(actual_commit_issue_keys) != set(actual_issue_keys):
            mr_manager.ensure_workflow_errors_info(
                errors=[
                    "Different Jira Issue sets in Merge Request title and commit messages. "
                    f"{actual_issue_keys} are mentioned in the Merge Request title while "
                    f"{actual_commit_issue_keys} are mentioned in the commit messages."],
                title="Commit message check failed")
            return WorkflowCheckRuleExecutionResult.commit_messages_problems

        expected_commit_message = f"{mr_data.title}\n\n{mr_data.description}".strip()
        if not mr_data.squash and mr_data.merged_commit_message.strip() != expected_commit_message:
            mr_manager.ensure_workflow_errors_info(
                errors=[
                    "For non-squashed Merge Requests with one commit the Merge Request title must "
                    "be the same that commit message which is not true "
                    f"({expected_commit_message!r} != {mr_data.merged_commit_message.strip()!r})"],
                title="Bad commit title")
            return WorkflowCheckRuleExecutionResult.mr_title_problem

        mr_manager.ensure_workflow_errors_info(errors=[])
        return WorkflowCheckRuleExecutionResult.rule_execution_successfull

    def _get_jira_issue_errors(self, mr_manager: MergeRequestManager) -> List[str]:
        jira_issue_errors = []

        if not mr_manager.data.issue_keys:
            logger.warning(
                f"{mr_manager}: Can't detect attached Jira Issue for the Merge Request.")
            jira_issue_errors = ["Merge Request must be related to at least one Jira Issue"]

        jira_issue_branches = {}
        first_found_issue_data = None
        actual_issue_keys = self._exclude_ignored_issues(mr_manager.data.issue_keys)
        for issue_key in actual_issue_keys:
            issue = self._jira.get_issue(issue_key)
            version_error_string = WrongVersionChecker().run(issue)
            if version_error_string:
                jira_issue_errors.append(
                    f"Bad `fixVersions` field in the related Jira Issue {issue_key}: "
                    f"{version_error_string}")

            first_found_issue_data = jira_issue_branches.setdefault(
                issue.project,
                {"key": issue_key, "branches": issue.branches(), "fixVersions": issue.fixVersions})

        if first_found_issue_data and first_found_issue_data["branches"] != issue.branches():
            jira_issue_errors.append(
                f"{issue_key}: `fixVersions` is inconsistent with `fixVersions` of "
                f"{first_found_issue_data['key']}: {issue.fixVersions!r} != "
                f"{first_found_issue_data['fixVersions']!r}.")

        return jira_issue_errors

    def _exclude_ignored_issues(self, issue_keys: List[str]) -> List[str]:
        result = []
        for key in issue_keys:
            issue = self._jira.get_issue(key)
            if IssueIgnoreLabelChecker().run(issue) or IssueIgnoreProjectChecker().run(issue):
                continue
            result.append(key)

        return result
