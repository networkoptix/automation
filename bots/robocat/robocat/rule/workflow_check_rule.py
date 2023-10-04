import logging
import re

from enum import Enum
from typing import List, Optional

from automation_tools.checkers.checkers import (WrongVersionChecker, IssueIgnoreLabelChecker)
from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId, Comment
from robocat.project_manager import ProjectManager
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
from robocat.rule.helpers.stateful_checker_helpers import StoredCheckResults
from automation_tools.jira import JiraAccessor

logger = logging.getLogger(__name__)


class WorkflowStoredCheckResults(StoredCheckResults):
    MESSAGE_IDS = {
        MessageId.WorkflowOk,
        MessageId.WorkflowBadFixVersions,
        MessageId.WorkflowDifferentCommitMessage,
        MessageId.WorkflowDifferentJiraIssueSets,
        MessageId.WorkflowInconsistentFixVersions,
        MessageId.WorkflowNoJiraIssueInCommitMessage,
        MessageId.WorkflowNoJiraIssueInMr,
        MessageId.WorkflowParenthesesNotAllowed,
    }
    OK_MESSAGE_IDS = {MessageId.WorkflowOk}


class WorkflowCheckRuleExecutionResultClass(RuleExecutionResultClass, Enum):
    def __bool__(self):
        return self in [self.rule_execution_successful, self.merged]


class WorkflowCheckRule(BaseRule):
    identifier = "workflow"

    ExecutionResult = WorkflowCheckRuleExecutionResultClass.create(
        "WorkflowCheckRuleExecutionResult", {
            "rule_execution_successful": "Workflow requirements are ok",
            "jira_issue_problems": "Problems with the attached Jira Issues",
            "inconsistent_descriptions": "MR description is inconsistent with the commit messages",
        })

    def __init__(self, config: dict, project_manager: ProjectManager, jira: JiraAccessor):
        super().__init__(config, project_manager, jira)

    def execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        logger.debug(f"Executing Jira Issue check rule with {mr_manager}...")

        mr_data = mr_manager.data
        preliminary_check_result = self.preliminary_check_result(mr_data)
        if preliminary_check_result != self.ExecutionResult.preliminary_check_passed:
            return preliminary_check_result

        self.jira.get_issue.cache_clear()

        jira_issue_errors = self._get_jira_issue_errors(mr_manager)
        if jira_issue_errors:
            self._update_workflow_errors_info(
                mr_manager=mr_manager,
                errors=jira_issue_errors,
                title="Jira workflow check failed")
            return self.ExecutionResult.jira_issue_problems

        if error := self._get_mr_description_error(mr_manager):
            self._update_workflow_errors_info(
                mr_manager=mr_manager,
                errors=[error],
                title="Merge request title/description does not comply with the rules")
            return self.ExecutionResult.inconsistent_descriptions

        mr_manager.ensure_no_workflow_errors()
        return self.ExecutionResult.rule_execution_successful

    def _update_workflow_errors_info(
            self, mr_manager: MergeRequestManager, errors: List[Comment], title: str):
        current_errors_info = WorkflowStoredCheckResults(mr_manager)
        reported_errors_by_id = current_errors_info.get_errors()
        for error in errors:
            if error.id not in reported_errors_by_id:
                mr_manager.add_workflow_error_info(error=error, title=title)

    def _get_jira_issue_errors(self, mr_manager: MergeRequestManager) -> List[Comment]:
        jira_issue_errors = []

        if not mr_manager.data.issue_keys:
            logger.warning(
                f"{mr_manager}: Can't detect attached Jira Issue for the Merge Request.")
            jira_issue_errors = [Comment(
                id=MessageId.WorkflowNoJiraIssueInMr,
                text="Merge Request must be related to at least one Jira Issue")]

        jira_issue_branches = {}
        first_found_issue_data = None
        actual_issue_keys = self._exclude_ignored_issues(mr_manager.data.issue_keys)
        for issue_key in actual_issue_keys:
            issue = self.jira.get_issue(issue_key)
            checker = WrongVersionChecker(project_keys=self.jira.project_keys)
            if version_error_string := checker.run(issue):
                comment_text = (
                    f"Bad `fixVersions` field in the related Jira Issue {issue_key}: "
                    f"{version_error_string}")
                jira_issue_errors.append(
                    Comment(id=MessageId.WorkflowBadFixVersions, text=comment_text))

            first_found_issue_data = jira_issue_branches.setdefault(
                issue.project,
                {"key": issue_key, "branches": issue.branches(), "fixVersions": issue.fixVersions})

        if first_found_issue_data and first_found_issue_data["branches"] != issue.branches():
            comment_text = (
                f"{issue_key}: `fixVersions` is inconsistent with `fixVersions` of "
                f"{first_found_issue_data['key']}: {issue.fixVersions!r} != "
                f"{first_found_issue_data['fixVersions']!r}.")
            jira_issue_errors.append(
                Comment(id=MessageId.WorkflowInconsistentFixVersions, text=comment_text))

        return jira_issue_errors

    def _get_mr_description_error(self, mr_manager: MergeRequestManager) -> Optional[Comment]:
        mr_data = mr_manager.data
        commits_data = mr_manager.get_commits_data()

        if not mr_data.squash:
            actual_commit_issue_keys = self._exclude_ignored_issues(
                list({k for keys in commits_data.issue_keys for k in keys}))
            actual_issue_keys = self._exclude_ignored_issues(mr_data.issue_keys)
            if not set(actual_issue_keys).issubset(set(actual_commit_issue_keys)):
                comment_text = (
                    "Different Jira Issue sets in Merge Request title/description and commit "
                    "messages are not allowed for non-squashed Merge Requests. "
                    f"{actual_issue_keys} are mentioned in the Merge Request title/description "
                    f"while {actual_commit_issue_keys} are mentioned in the commit messages.")
                return Comment(id=MessageId.WorkflowDifferentJiraIssueSets, text=comment_text)

        if not (mr_manager.is_follow_up() or mr_data.squash or len(commits_data.messages) > 1):
            expected_commit_message = f"{mr_data.title}\n\n{mr_data.description}".strip()
            if commits_data.messages[0].strip() != expected_commit_message:
                comment_text = (
                    "For non-squashed Merge Requests with one commit title/description of the "
                    "Merge Request must be the same that the commit message. Merge Request "
                    f"title/description is {expected_commit_message!r}, commit message is "
                    f"{commits_data.messages[0].strip()!r}")
                return Comment(id=MessageId.WorkflowDifferentCommitMessage, text=comment_text)

        if mr_manager.is_follow_up() and mr_data.squash:
            if re.match(r'^(?:.+?\:)?\s*\(.+\)', mr_data.title):
                comment_text = (
                    "Parentheses right after the Jira Issue ref (or at the beginning, if no Jira "
                    "Issue is mentioned) in the title of the squashed follow-up Merge Request "
                    "are not allowed.")
                return Comment(id=MessageId.WorkflowParenthesesNotAllowed, text=comment_text)

        if not mr_data.squash:
            if any([True for keys in commits_data.issue_keys if not keys]):
                comment_text = (
                    "In a non-squashed Merge Request, each commit message must contain a "
                    "reference to at least one Jira Issue")
                return Comment(id=MessageId.WorkflowNoJiraIssueInCommitMessage, text=comment_text)

        return None

    def _exclude_ignored_issues(self, issue_keys: List[str]) -> List[str]:
        result = []
        for key in issue_keys:
            issue = self.jira.get_issue(key)
            checker = IssueIgnoreLabelChecker(project_keys=self.jira.project_keys)
            if checker.run(issue):
                continue
            result.append(key)

        return result
