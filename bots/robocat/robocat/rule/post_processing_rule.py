## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from enum import Enum
import logging

from automation_tools.jira import (
    GitlabBranchDescriptor, JiraAccessor, JiraIssue, JiraStatusChangeError)
from automation_tools.jira_comments import JiraComment, JiraMessageId
from robocat.config import Config
from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId
from robocat.project_manager import ProjectManager
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass

logger = logging.getLogger(__name__)


class PostProcessingRuleExecutionResultClass(RuleExecutionResultClass, Enum):
    def __bool__(self):
        return self in [self.rule_execution_successful, self.filtered_out]

    def __str__(self):
        return str(self.value)


class PostProcessingRule(BaseRule):
    identifier = "post_processing"

    ExecutionResult = PostProcessingRuleExecutionResultClass.create(
        "PostProcessingRuleExecutionResult", {
            "rule_execution_successful": "All operations completed successfully",
            "not_eligible": "Merge request is not eligible for post-processing",
            "rule_execution_failed": "Some of operations failed",
        })

    def __init__(self, config: Config, project_manager: ProjectManager, jira: JiraAccessor):
        super().__init__(config, project_manager, jira)
        self._default_branch_project_mapping = config.jira.project_mapping

    def _execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        logger.debug(f"Executing post-processing rule with {mr_manager}...")

        mr_data = mr_manager.data
        if not mr_data.is_merged:
            logger.info(f"{mr_manager}: Merge request isn't merged. Cannot post-process.")
            return self.ExecutionResult.not_eligible

        if not (jira_issues := self.jira.get_issues(mr_manager.data.issue_keys)):
            logger.info(
                f"{mr_manager}: Can't detect attached issue for the merge request. "
                "Skipping post-processing.")
            return self.ExecutionResult.not_eligible

        return (
            self.ExecutionResult.rule_execution_successful
            if self._try_close_jira_issues(mr_manager=mr_manager, issues=jira_issues)
            else self.ExecutionResult.rule_execution_failed)

    def _try_close_jira_issues(self, mr_manager, issues: list[JiraIssue]) -> bool:
        return bool(all(
            self._try_close_jira_issue(mr_manager=mr_manager, issue=issue) for issue in issues))

    def _try_close_jira_issue(self, mr_manager: MergeRequestManager, issue: JiraIssue) -> bool:
        logger.debug(f"{mr_manager} Trying to move to QA/close Issue {issue}.")

        declared_merged_branches = issue.declared_merged_branches()
        declared_merged_branch_names = {str(b) for b in declared_merged_branches}
        logger.debug(f"Declared merged branches for {issue}: {declared_merged_branch_names!r}")

        for branch in issue.branches():
            if not self._check_if_branch_is_merged(
                    branch=branch,
                    mr_manager=mr_manager,
                    issue=issue,
                    declared_merged_branches=declared_merged_branches):
                fix_version_branch_names = set(str(b) for b in issue.branches())
                logger.info(
                    f"{mr_manager}: Cannot move to QA/close issue {issue} because the changes are "
                    f'not merged to some of the branches determined by "fixVersions" field. Issue '
                    f'branches (from "fixVersions"): {fix_version_branch_names!r}, merged '
                    f"branches:  {declared_merged_branch_names!r}.")
                return False

        try:
            if issue.try_finalize():
                return True
        except JiraStatusChangeError as error:
            mr_manager.add_issue_not_finalized_notification(str(issue))
            issue.add_comment(JiraComment(
                message_id=JiraMessageId.FollowUpError,
                params={
                    "error": str(error),
                    "mr_url": mr_manager.data.url,
                    "mr_name": mr_manager.data.title,
                }))
        return False

    def _check_if_branch_is_merged(
            self,
            branch: GitlabBranchDescriptor,
            mr_manager: MergeRequestManager,
            issue: JiraIssue,
            declared_merged_branches: list[GitlabBranchDescriptor]) -> bool:
        project_path = (branch.project_path
                        or self._default_branch_project_mapping.get(issue.project, None))
        if project_path is None:
            logger.warning(
                f"{mr_manager}: The branch {branch} belongs to the unknown project - can't check "
                f"if it is merged. Skipping the Issue {issue} post-processing.")
            mr_manager.add_comment_with_message_id(
                MessageId.UnknownProjectWhenClosingIssue,
                message_params={
                    "project": issue.project, "branch": str(branch), "issue": str(issue)})
            return False

        is_branch_declared_merged = any(
            True
            for b in declared_merged_branches
            if b.project_path == project_path and b.branch_name == branch.branch_name)
        if not is_branch_declared_merged:
            return False

        logger.debug(f"{mr_manager}: The branch {branch} is merged.")
        return True
