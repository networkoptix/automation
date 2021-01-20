import logging
from enum import Enum
from typing import List

from robocat.merge_request_manager import MergeRequestManager, FollowupCreationResult
from robocat.project_manager import ProjectManager
from robocat.rule.base_rule import BaseRule, RuleExecutionResult
from automation_tools.jira import JiraAccessor, JiraError

logger = logging.getLogger(__name__)


class FollowupRuleExecutionResult(RuleExecutionResult, Enum):
    rule_execution_successfull = "All operations completed successfylly"
    not_eligible = "Merge request is not eligible for cherry-pick"
    rule_execution_failed = "Some of operations failed"

    def __bool__(self):
        return self == self.rule_execution_successfull

    def __str__(self):
        return str(self.value)


class FollowupRule(BaseRule):
    def __init__(self, project_manager: ProjectManager, jira: JiraAccessor):
        self._project_manager = project_manager
        self._jira = jira
        super().__init__()

    def execute(self, mr_manager: MergeRequestManager) -> FollowupRuleExecutionResult:
        logger.debug(f"Executing follow-up rule with {mr_manager}...")

        self._jira.get_issue.cache_clear()

        mr_data = mr_manager.data
        if not mr_data.is_merged:
            logger.info(f"{mr_manager}: Merge request isn't merged. Cannot cherry-pick.")
            return FollowupRuleExecutionResult.not_eligible

        jira_issue_keys = mr_manager.data.issue_keys
        if not jira_issue_keys:
            # TODO: Add comment to MR informing the user that we can't find any attached issue and
            # that he or she should double-check if it is normal.
            logger.info(
                f"{mr_manager}: Can't detect attached issue for the merge request. "
                "Skipping cherry-pick.")
            return FollowupRuleExecutionResult.not_eligible

        # Intercept all the exceptions and leave a comment in Jira issues about failing of merge
        # request follow-up processing. TODO: Add more sofisticated error processing.
        try:
            # Follow-up merge request. Close Jira issues which are mentioned by the current merge
            # request, if all their branches (defined by "fixVersions" field) have merged merge
            # requests.
            if mr_manager.is_followup():
                logger.info(
                    "Merge request is a follow-up merge request. Trying to move to QA/close Jira "
                    "issues.")
                self._try_close_jira_issues(
                    target_branch=mr_data.target_branch, issue_keys=jira_issue_keys)
                return FollowupRuleExecutionResult.rule_execution_successfull

            # Primary merge request.
            # 1. Check all Jira issues which are mentioned by the current merge request and create
            # follow-up merge requests for all their branches (defined by "fixVersions" field),
            # except for the target branch of this merge request.
            # 2. Close Jira issues which have only one branch, if this branch is the target branch
            # of the current merge request.
            logger.info(
                "Merge request is a primary merge request. Trying to move to QA/close "
                "single-branch Jira issues and create follow-up merge requests.")
            self._create_followup_merge_requests(original_mr_manager=mr_manager)
            self._try_close_single_branch_jira_issues(
                target_branch=mr_data.target_branch, issue_keys=jira_issue_keys)
            return FollowupRuleExecutionResult.rule_execution_successfull

        except Exception as error:
            logger.error(f"Follow-up processing was crashed for {mr_manager}: {error}")
            for issue in self._jira.get_issues(jira_issue_keys):
                issue.add_followup_error_comment(error=error, mr_url=mr_data.url)
            return FollowupRuleExecutionResult.rule_execution_failed

    def _try_close_jira_issues(self, target_branch: str, issue_keys: List[str]):
        for issue in self._jira.get_issues(issue_keys):
            logger.debug(f"Trying to move to QA/close issue {issue}.")
            issue_branches = issue.branches
            mr_ids = issue.get_related_merge_request_ids()
            merged_branches = {target_branch}.union(
                self._project_manager.get_merged_branches_by_mr_ids(mr_ids))

            if not issue_branches.issubset(merged_branches):
                logger.info(
                    f"Cannot move to QA/close issue {issue} because the changes are not "
                    'merged to some of the branches determined by "fixVersions" field. Issue '
                    f'branches (from "fixVersions"): {issue_branches!r}, merged branches: '
                    f"{merged_branches!r}.")
                continue

            issue.try_finalize()

    def _try_close_single_branch_jira_issues(
            self, target_branch: str, issue_keys: List[str]):
        for issue in self._jira.get_issues(issue_keys):
            if issue.branches == {target_branch}:
                issue.try_finalize()

    def _create_followup_merge_requests(self, original_mr_manager: MergeRequestManager):
        original_target_branch = original_mr_manager.data.target_branch
        issue_branches_with_merged_mr = {original_target_branch}
        for issue in self._jira.get_issues(original_mr_manager.data.issue_keys):
            issue_branches = issue.branches
            if issue_branches == {original_target_branch}:
                continue

            for target_branch in issue_branches:
                if target_branch in issue_branches_with_merged_mr:
                    continue

                logger.debug(f"Trying to create follow-up merge requests for issue {issue}.")
                self._create_followup_merge_request(
                    original_mr_manager=original_mr_manager,
                    target_branch=target_branch)
                issue_branches_with_merged_mr.add(target_branch)

            issue.add_followups_created_comment(
                issue_branches - {original_target_branch})

    def _create_followup_merge_request(
            self, original_mr_manager: MergeRequestManager, target_branch: str):
        new_mr = self._project_manager.create_followup_merge_request(
            target_branch=target_branch, original_mr_manager=original_mr_manager)
        if new_mr is None:  # Dry run case
            return

        new_mr_manager = MergeRequestManager(new_mr)
        original_mr_manager.add_followup_creation_comment(FollowupCreationResult(
            branch=target_branch,
            url=new_mr_manager.data.url,
            successfull=True))
