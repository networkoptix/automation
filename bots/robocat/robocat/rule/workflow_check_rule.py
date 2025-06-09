## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from enum import Enum
from typing import Optional
import logging
import re

from automation_tools.checkers.checkers import (
    IssueIgnoreLabelChecker, WorkflowPolicyChecker, WrongVersionChecker)
from automation_tools.jira import JiraAccessor, JiraIssue, GitlabBranchDescriptor
from automation_tools.jira_helpers import JIRA_STATUS_PROGRESS, JIRA_STATUS_REVIEW
from robocat.action_reasons import CheckFailureReason
from robocat.comments import Message
from robocat.config import Config
from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId
from robocat.project_manager import ProjectManager
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
from robocat.rule.helpers.stateful_checker_helpers import StoredCheckResults

logger = logging.getLogger(__name__)

ProjectIssueBranchInfo = dict[str, dict[str, GitlabBranchDescriptor]]


class WorkflowStoredCheckResults(StoredCheckResults):
    MESSAGE_IDS = {
        MessageId.WorkflowOk,
        MessageId.WorkflowBadFixVersions,
        MessageId.WorkflowBadTargetBranch,
        MessageId.WorkflowDifferentCommitMessage,
        MessageId.WorkflowDifferentJiraIssueSets,
        MessageId.WorkflowInconsistentFixVersions,
        MessageId.WorkflowNoJiraIssueInCommitMessage,
        MessageId.WorkflowNoJiraIssueInMr,
        MessageId.WorkflowParenthesesNotAllowed,
        MessageId.InconsistentAssigneesInJiraAndGitlab,
        MessageId.SuspiciousJiraIssueStatus,
        MessageId.FailedCheckForNoSupportedProject,
    }
    OK_MESSAGE_IDS = {MessageId.WorkflowOk}


class WorkflowCheckRuleExecutionResultClass(RuleExecutionResultClass, Enum):
    def __bool__(self):
        return self in [
            self.rule_execution_successful,
            self.heuristic_warnings,
            self.merged,
            self.not_applicable,
            self.filtered_out,
        ]


class WorkflowCheckRule(BaseRule):
    identifier = "workflow"

    ExecutionResult = WorkflowCheckRuleExecutionResultClass.create(
        "WorkflowCheckRuleExecutionResult", {
            "bad_project_list": "Merge Request does not belong to any supported Jira Project",
            "rule_execution_successful": "Workflow requirements are ok",
            "jira_issue_problems": "Problems with the attached Jira Issues",
            "heuristic_warnings": "Possible workflow problems",
            "inconsistent_descriptions": "MR description is inconsistent with the commit messages",
            "not_applicable": "Only Issues concerning other Projects are mentioned in the MR",
        })

    def __init__(self, config: Config, project_manager: ProjectManager, jira: JiraAccessor):
        super().__init__(config, project_manager, jira)
        self._jira_issue_cache: dict[str, JiraIssue] = {}
        self._project_keys: list[str] = (
            list(self.config.jira.project_mapping.keys())
            if self.config.jira.project_mapping
            else (self.config.jira.project_keys or []))

    def _execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        logger.debug(f"Executing Jira Issue check rule with {mr_manager}...")

        self._jira_issue_cache = {}

        mr_data = mr_manager.data
        preliminary_check_result = self.preliminary_check_result(mr_data)
        if preliminary_check_result != self.ExecutionResult.preliminary_check_passed:
            return preliminary_check_result

        belongs_to_supported_projects = any([
            True for k in mr_manager.data.issue_keys
            if WorkflowPolicyChecker(project_keys=self._project_keys).is_applicable(k)])
        if not belongs_to_supported_projects:
            related_project_problems = [
                Message(
                    id=MessageId.FailedCheckForNoSupportedProject,
                    params={"jira_projects_list": '"{}"'.format('", "'.join(self._project_keys))}),
            ]
            self._update_workflow_problems_info(
                mr_manager=mr_manager, problems=related_project_problems, is_blocker=True)
            return self.ExecutionResult.bad_project_list

        if mr_manager.data.issue_keys and self._foreign_issues_only(mr_manager):
            return self.ExecutionResult.not_applicable

        previous_check_state = WorkflowStoredCheckResults(mr_manager)

        if jira_issue_errors := self._get_jira_issue_errors(mr_manager):
            self._update_workflow_problems_info(
                mr_manager=mr_manager, problems=jira_issue_errors, is_blocker=True)
            return self.ExecutionResult.jira_issue_problems

        if error := self._get_mr_description_error(mr_manager):
            self._update_workflow_problems_info(
                mr_manager=mr_manager, problems=[error], is_blocker=True)
            return self.ExecutionResult.inconsistent_descriptions

        if heuristic_warnings := self._get_heuristic_warnings(mr_manager):
            self._update_workflow_problems_info(
                mr_manager=mr_manager, problems=heuristic_warnings, is_blocker=False)
            return self.ExecutionResult.heuristic_warnings

        if previous_check_state.was_never_checked() or previous_check_state.has_errors():
            # This is the first check or we detected errors during the previous checks but not now.
            # Leave "good to go" comment.
            error_notes = WorkflowStoredCheckResults(mr_manager).get_error_notes(
                unresolved_only=True)
            mr_manager.ensure_no_workflow_errors(error_notes)

        return self.ExecutionResult.rule_execution_successful

    def _foreign_issues_only(self, mr_manager: MergeRequestManager) -> bool:
        jira_projects = {
            self._get_jira_issue_using_cache(k).project
            for k in self._exclude_ignored_issues(mr_manager.data.issue_keys)}

        return all(
            False
            for project in jira_projects
            if self.config.jira.project_mapping.get(project) == self.project_manager.data.path)

    def _update_workflow_problems_info(
            self, mr_manager: MergeRequestManager, problems: list[Message], is_blocker: bool):
        current_errors_info = WorkflowStoredCheckResults(mr_manager)
        reported_errors_by_id = current_errors_info.get_errors(unresolved_only=True)
        for problem in problems:
            if problem.id not in reported_errors_by_id:
                mr_manager.add_workflow_problem_info(problem=problem, is_blocker=is_blocker)

    def _get_jira_issue_errors(self, mr_manager: MergeRequestManager) -> list[Message]:
        jira_issue_errors = []

        if not mr_manager.data.issue_keys:
            logger.warning(
                f"{mr_manager}: Can't detect attached Jira Issue for the Merge Request.")
            jira_issue_errors = [Message(id=MessageId.WorkflowNoJiraIssueInMr)]

        # Iterate over all the Issues mentioned in the MR, except for the ones marked by
        # "hide_from_police" label. Note that Issues can belong to different Projects.
        jira_issue_branches_by_projects = {}
        for issue_key in self._exclude_ignored_issues(mr_manager.data.issue_keys):
            issue = self._get_jira_issue_using_cache(str(issue_key))
            jira_issue_errors += self._check_jira_issue_for_errors(
                issue=issue,
                mr_manager=mr_manager,
                jira_issue_branches_by_projects=jira_issue_branches_by_projects)

        return jira_issue_errors

    def _check_jira_issue_for_errors(
            self,
            issue: JiraIssue,
            mr_manager: MergeRequestManager,
            jira_issue_branches_by_projects: ProjectIssueBranchInfo) -> list[Message]:
        result = []

        result += self._check_jira_issue_for_bad_version_set(issue)
        result += self._check_jira_issue_for_inconsistent_branches(
            issue=issue, jira_issue_branches_by_projects=jira_issue_branches_by_projects)
        result += self._check_jira_issue_for_bad_target_branch(
            issue=issue,
            mr_manager=mr_manager,
            jira_issue_branches_by_projects=jira_issue_branches_by_projects)

        return result

    def _check_jira_issue_for_bad_version_set(self, issue: JiraIssue) -> list[Message]:
        result = []
        checker = WrongVersionChecker(
            project_keys=self.jira.project_keys, gitlab_project=self.project_manager.data.path)
        if version_error_string := checker.run(issue):
            parameters = {"issue_key": str(issue), "version_error_string": version_error_string}
            result.append(
                Message(id=MessageId.WorkflowBadFixVersions, params=parameters))

        return result

    def _check_jira_issue_for_inconsistent_branches(
            self, issue: JiraIssue,
            jira_issue_branches_by_projects: ProjectIssueBranchInfo) -> list[Message]:
        result = []

        current_project_path = self.project_manager.data.path
        branches = {
            GitlabBranchDescriptor(branch_name=b.branch_name, project_path=current_project_path)
            for b in issue.branches()
            if b.project_path in (None, current_project_path)}

        first_found_issue_data = jira_issue_branches_by_projects.setdefault(
            issue.project,
            {"key": str(issue), "branches": branches, "fixVersions": issue.fixVersions})

        # Check that all the Issues belonging to one project have the same "fixVersions".
        if first_found_issue_data["branches"] != branches:
            parameters = {
                "current_issue_key": str(issue),
                "first_found_issue_key": first_found_issue_data['key'],
                "current_issue_versions": issue.fixVersions,
                "first_found_issue_versions": first_found_issue_data['fixVersions'],
            }
            result.append(
                Message(id=MessageId.WorkflowInconsistentFixVersions, params=parameters))

        return result

    def _check_jira_issue_for_bad_target_branch(
            self,
            issue: JiraIssue,
            mr_manager: MergeRequestManager,
            jira_issue_branches_by_projects: ProjectIssueBranchInfo) -> list[Message]:
        result = []

        first_found_issue_data = jira_issue_branches_by_projects.get(issue.project, {})

        # Check that the target branch corresponds to one of the versions from "fixVersions" field
        # once for every Project. If no "fixVersions" are set, the check is skipped.
        target_branch_description = GitlabBranchDescriptor(
            branch_name=mr_manager.data.target_branch, project_path=self.project_manager.data.path)
        if (bool(issue.fixVersions)
                and first_found_issue_data["key"] == str(issue)
                and target_branch_description not in first_found_issue_data["branches"]):
            logger.debug(
                f"Target branch is {mr_manager.data.target_branch!r}, branches extracted from "
                f"fixVerions are {first_found_issue_data['branches']!r}, fixVersions are "
                f"{first_found_issue_data['fixVersions']!r}")
            parameters = {"issue_key": str(issue), "target_branch": mr_manager.data.target_branch}
            result.append(
                Message(id=MessageId.WorkflowBadTargetBranch, params=parameters))

        return result

    def _get_jira_issue_using_cache(self, key: str) -> JiraIssue:
        if key not in self._jira_issue_cache:
            self._jira_issue_cache[key] = self.jira.get_issue(key)
        return self._jira_issue_cache[key]

    def _get_mr_description_error(self, mr_manager: MergeRequestManager) -> Optional[Message]:
        mr_data = mr_manager.data
        commits_data = mr_manager.get_commits_data()

        if not mr_data.squash:
            actual_commit_issue_keys = self._exclude_ignored_issues(
                list({k for keys in commits_data.issue_keys for k in keys}))
            actual_issue_keys = self._exclude_ignored_issues(mr_data.issue_keys)
            if not set(actual_issue_keys).issubset(set(actual_commit_issue_keys)):
                parameters = {
                    "actual_issue_keys": actual_issue_keys,
                    "actual_commit_issue_keys": actual_commit_issue_keys,
                }
                return Message(id=MessageId.WorkflowDifferentJiraIssueSets, params=parameters)

        if not (mr_manager.is_follow_up() or mr_data.squash or len(commits_data.messages) > 1):
            expected_commit_message = f"{mr_data.title}\n\n{mr_data.description}".strip()
            if commits_data.messages[0].strip() != expected_commit_message:
                parameters = {
                    "expected_commit_message": expected_commit_message,
                    "first_commit_message": commits_data.messages[0].strip(),
                }
                return Message(id=MessageId.WorkflowDifferentCommitMessage, params=parameters)

        if mr_manager.is_follow_up() and mr_data.squash:
            if re.match(r'^(?:.+?\:)?\s*\(.+\)', mr_data.title):
                return Message(id=MessageId.WorkflowParenthesesNotAllowed)

        if not mr_data.squash:
            if any([True for keys in commits_data.issue_keys if not keys]):
                return Message(id=MessageId.WorkflowNoJiraIssueInCommitMessage)

        return None

    def _exclude_ignored_issues(self, issue_keys: list[str]) -> list[str]:
        result = []
        for key in issue_keys:
            issue = self._get_jira_issue_using_cache(key)
            checker = IssueIgnoreLabelChecker(project_keys=self.jira.project_keys)
            if checker.run(issue):
                continue
            result.append(key)

        return result

    def _get_heuristic_warnings(self, mr_manager: MergeRequestManager) -> list[Message]:
        result = []

        mr_data = mr_manager.data
        # Here we check all the MR Issues, including the ones labeld as ignored.
        for issue_key in mr_data.issue_keys:
            issue = self._get_jira_issue_using_cache(issue_key)
            if issue.assignee.name != mr_data.author.name:
                parameters = {
                    "issue_key": issue_key,
                    "jira_assignee": issue.assignee.name,
                    "mr_assignee": mr_data.author.name,
                }
                result.append(Message(
                    id=MessageId.InconsistentAssigneesInJiraAndGitlab, params=parameters))

            if issue.status not in [JIRA_STATUS_PROGRESS, JIRA_STATUS_REVIEW]:
                parameters = {"issue_key": issue_key, "issue_status": issue.raw_status}
                result.append(Message(
                    id=MessageId.SuspiciousJiraIssueStatus, params=parameters))

        return result
