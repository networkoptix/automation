import logging
import re

from enum import Enum
from typing import List, Optional, Set

from automation_tools.checkers.checkers import (
    WrongVersionChecker, IssueIgnoreLabelChecker, IssueIgnoreProjectChecker)
from automation_tools.checkers.config import DEFAULT_PROJECT_KEYS_TO_CHECK
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
from robocat.merge_request_manager import MergeRequestManager
from automation_tools.jira import JiraAccessor

logger = logging.getLogger(__name__)


class WorkflowCheckRuleExecutionResultClass(RuleExecutionResultClass, Enum):
    def __bool__(self):
        return self in [self.rule_execution_successfull, self.merged]


class WorkflowCheckRule(BaseRule):
    ExecutionResult = WorkflowCheckRuleExecutionResultClass.create(
        "WorkflowCheckRuleExecutionResult", {
            "rule_execution_successfull": "Workflow requirements are ok",
            "jira_issue_problems": "Problems with the attached Jira Issues",
            "inconsistent_descriptions": "MR description is inconsistent with the commit messages",
        })

    def __init__(self, jira: JiraAccessor, project_keys: Set[str] = None):
        self._jira = jira
        self._project_keys = project_keys if project_keys else DEFAULT_PROJECT_KEYS_TO_CHECK
        super().__init__()

    def execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        logger.debug(f"Executing Jira Issue check rule with {mr_manager}...")

        mr_data = mr_manager.data
        preliminary_check_result = self.preliminary_check_result(mr_data)
        if preliminary_check_result != self.ExecutionResult.preliminary_check_passed:
            return preliminary_check_result

        self._jira.get_issue.cache_clear()

        jira_issue_errors = self._get_jira_issue_errors(mr_manager)
        if jira_issue_errors:
            mr_manager.ensure_workflow_errors_info(
                errors=jira_issue_errors, title="Jira workflow check failed")
            return self.ExecutionResult.jira_issue_problems

        if error := self._get_mr_description_error(mr_manager):
            mr_manager.ensure_workflow_errors_info(
                errors=[error],
                title="Merge request title/description is not compliant with the rules")
            return self.ExecutionResult.inconsistent_descriptions

        mr_manager.ensure_workflow_errors_info(errors=[])
        return self.ExecutionResult.rule_execution_successfull

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

    def _get_mr_description_error(self, mr_manager: MergeRequestManager) -> Optional[str]:
        mr_data = mr_manager.data
        commits_data = mr_manager.get_commits_data()

        if not mr_data.squash:
            actual_commit_issue_keys = self._exclude_ignored_issues(
                list({k for keys in commits_data.issue_keys for k in keys}))
            actual_issue_keys = self._exclude_ignored_issues(mr_data.issue_keys)
            if not set(actual_issue_keys).issubset(set(actual_commit_issue_keys)):
                return (
                    "Different Jira Issue sets in Merge Request title/description and commit "
                    "messages are not allowed for non-squashed Merge Requests. "
                    f"{actual_issue_keys} are mentioned in the Merge Request title/description "
                    f"while {actual_commit_issue_keys} are mentioned in the commit messages.")

        if not (mr_manager.is_followup() or mr_data.squash or len(commits_data.messages) > 1):
            expected_commit_message = f"{mr_data.title}\n\n{mr_data.description}".strip()
            if commits_data.messages[0].strip() != expected_commit_message:
                return (
                    "For non-squashed Merge Requests with one commit title/description of the "
                    "Merge Request must be the same that the commit message. Merge Request "
                    f"title/description is {expected_commit_message!r}, commit message is "
                    f"{commits_data.messages[0].strip()!r}")

        if mr_manager.is_followup() and mr_data.squash:
            if re.match(r'^(?:.+?\:)?\s*\(.+\)', mr_data.title):
                return (
                    "Parentheses right after the Jira Issue ref (or at the beginning, if no Jira "
                    "Issue is mentioned) in the title of the squashed follow-up Merge Request "
                    "are not allowed.")

        if not mr_data.squash:
            if any([True for keys in commits_data.issue_keys if not keys]):
                return (
                    "In non-squashed Merge Request all commit messages must contain a reference "
                    "to at least one Jira Issue.")

        return None

    def _exclude_ignored_issues(self, issue_keys: List[str]) -> List[str]:
        result = []
        for key in issue_keys:
            issue = self._jira.get_issue(key)
            checkers = [IssueIgnoreLabelChecker(), IssueIgnoreProjectChecker(self._project_keys)]
            if any(c.run(issue) for c in checkers):
                continue
            result.append(key)

        return result
