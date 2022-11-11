import logging
from enum import Enum
from typing import List

from robocat.merge_request_manager import MergeRequestManager, FollowupCreationResult
import robocat.merge_request_actions.followup_actions
from robocat.project_manager import ProjectManager
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
from automation_tools.jira import JiraAccessor

logger = logging.getLogger(__name__)


class FollowupRuleExecutionResultClass(RuleExecutionResultClass, Enum):
    def __bool__(self):
        return self == self.rule_execution_successful

    def __str__(self):
        return str(self.value)


class FollowupRule(BaseRule):
    ExecutionResult = FollowupRuleExecutionResultClass.create(
        "FollowupRuleExecutionResult", {
            "rule_execution_successful": "All operations completed successfully",
            "not_eligible": "Merge request is not eligible for cherry-pick",
            "rule_execution_failed": "Some of operations failed",
        })

    def __init__(self, project_manager: ProjectManager, jira: JiraAccessor):
        self._project_manager = project_manager
        self._jira = jira
        super().__init__()

    def execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        logger.debug(f"Executing follow-up rule with {mr_manager}...")

        self._jira.get_issue.cache_clear()

        mr_data = mr_manager.data
        if not mr_data.is_merged:
            logger.info(f"{mr_manager}: Merge request isn't merged. Cannot cherry-pick.")
            return self.ExecutionResult.not_eligible

        jira_issue_keys = mr_manager.data.issue_keys
        if not jira_issue_keys:
            # TODO: Add comment to MR informing the user that we can't find any attached issue and
            # that he or she should double-check if it is normal.
            logger.info(
                f"{mr_manager}: Can't detect attached issue for the merge request. "
                "Skipping cherry-pick.")
            return self.ExecutionResult.not_eligible

        # Intercept all the exceptions and leave a comment in Jira issues about failing of merge
        # request follow-up processing. TODO: Add more sophisticated error processing.
        try:
            # A follow-up Merge Request. Close Jira Issues mentioned by the current Merge Request,
            # if all their branches (defined by the "fixVersions" field) have the respective Merge
            # Requests merged.
            if mr_manager.is_followup():
                logger.info(
                    f"{mr_manager}: The Merge Request is a follow-up. Trying to move to "
                    "QA/close Jira issues.")
                self._try_close_jira_issues(
                    mr_manager=mr_manager,
                    target_branch=mr_data.target_branch,
                    issue_keys=jira_issue_keys)
                return self.ExecutionResult.rule_execution_successful

            # Primary merge request.
            # 1. Check all Jira issues which are mentioned by the current merge request and create
            # follow-up merge requests for all their branches (defined by "fixVersions" field),
            # except for the target branch of this merge request.
            # 2. Close Jira issues which have only one branch, if this branch is the target branch
            # of the current merge request.
            logger.info(
                f"{mr_manager}: Merge request is a primary merge request. Trying to move to "
                "QA/close single-branch Jira issues and create follow-up merge requests.")
            robocat.merge_request_actions.followup_actions.create_followup_merge_requests(
                jira=self._jira,
                project_manager=self._project_manager,
                mr_manager=mr_manager)
            self._try_close_single_branch_jira_issues(
                target_branch=mr_data.target_branch,
                issue_keys=jira_issue_keys,
                mr_manager=mr_manager)
            return self.ExecutionResult.rule_execution_successful

        except Exception as error:
            logger.error(
                f"{mr_manager}: Follow-up processing was crashed for {mr_manager}: {error}")
            for issue in self._jira.get_issues(jira_issue_keys):
                issue.add_followup_error_comment(error=error, mr_url=mr_data.url)
            return self.ExecutionResult.rule_execution_failed

    def _try_close_jira_issues(self, mr_manager, target_branch: str, issue_keys: List[str]):
        for issue in self._jira.get_issues(issue_keys):
            logger.debug(f"{mr_manager} Trying to move to QA/close issue {issue}.")
            issue_branches = issue.branches(exclude_already_merged=True)
            mr_ids = issue.get_related_merge_request_ids()
            merged_branches = {target_branch}.union(
                self._project_manager.get_merged_branches_by_mr_ids(mr_ids))

            if not issue_branches.issubset(merged_branches):
                logger.info(
                    f"{mr_manager}: Cannot move to QA/close issue {issue} because the changes are "
                    'not merged to some of the branches determined by "fixVersions" field. Issue '
                    f'branches (from "fixVersions"): {issue_branches!r}, merged branches: '
                    f"{merged_branches!r}.")
                continue

            issue.try_finalize() or mr_manager.add_issue_not_finalized_notification(str(issue))

    def _try_close_single_branch_jira_issues(
            self, target_branch: str, issue_keys: List[str], mr_manager: MergeRequestManager):
        for issue in self._jira.get_issues(issue_keys):
            if issue.branches(exclude_already_merged=True) == {target_branch}:
                issue.try_finalize() or mr_manager.add_issue_not_finalized_notification(str(issue))
