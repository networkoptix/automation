import logging
from enum import Enum

from robocat.merge_request_manager import MergeRequestManager, FollowupCreationResult, FollowupData
from robocat.project_manager import ProjectManager
from robocat.rule.base_rule import BaseRule, RuleExecutionResult
from robocat.action_reasons import ReturnToDevelopmentReason
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

        if not mr_manager.is_merged:
            logger.info("{mr_manager}: Merge request isn't merged. Cannot cherry-pick.")
            return FollowupRuleExecutionResult.not_eligible

        followup_mr_data = mr_manager.get_followup_mr_data()
        if followup_mr_data is None:
            return FollowupRuleExecutionResult.not_eligible

        # Intercept all the exceptions and leave a comment in Jira issues about failing of merge
        # request follow-up processing. TODO: Add more sofisticated error processing.
        try:
            # Follow-up merge request. Close Jira issues which are mentioned by the current merge
            # request, if all their branches (defined by "fixVersions" field) have merged merge
            # requests.
            if followup_mr_data.is_followup:
                logger.info(
                    "Merge request is a follow-up merge request. Trying to move to QA/close Jira "
                    "issues.")
                self._try_close_jira_issues(followup_mr_data=followup_mr_data)
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
            self._create_followup_merge_requests(
                current_mr_manager=mr_manager, followup_mr_data=followup_mr_data)
            self._try_close_single_branch_jira_issues(followup_mr_data=followup_mr_data)
            return FollowupRuleExecutionResult.rule_execution_successfull

        except Exception as error:
            logger.error(f"Follow-up processing was crashed for {mr_manager}: {error}")
            for issue in self._jira.get_issues(followup_mr_data.issue_keys):
                issue.add_followup_error_comment(
                    error=error, mr_url=followup_mr_data.original_mr_url)
            return FollowupRuleExecutionResult.rule_execution_failed

    def _try_close_jira_issues(self, followup_mr_data: FollowupData):
        for issue in self._jira.get_issues(followup_mr_data.issue_keys):
            logger.debug(f"Trying to move to QA/close issue {issue}.")
            issue_branches = issue.branches
            mr_ids = issue.get_related_merge_request_ids()
            merged_branches = {followup_mr_data.original_target_branch}.union(
                self._project_manager.get_merged_branches_by_mr_ids(mr_ids))

            if not issue_branches.issubset(merged_branches):
                logger.info(
                    f"Cannot move to QA/close issue {issue} because the changes are not "
                    'merged to some of the branches determined by "fixVersions" field. Issue '
                    f'branches (from "fixVersions"): {issue_branches!r}, merged branches: '
                    f"{merged_branches!r}.")
                continue

            issue.try_finalize()

    def _try_close_single_branch_jira_issues(self, followup_mr_data: FollowupData):
        for issue in self._jira.get_issues(followup_mr_data.issue_keys):
            if issue.branches == {followup_mr_data.original_target_branch}:
                issue.try_finalize()

    def _create_followup_merge_requests(
            self, current_mr_manager: MergeRequestManager, followup_mr_data: FollowupData):

        issue_branches_with_merged_mr = {followup_mr_data.original_target_branch}
        for issue in self._jira.get_issues(followup_mr_data.issue_keys):
            issue_branches = issue.branches
            if issue_branches == {followup_mr_data.original_target_branch}:
                continue

            for target_branch in issue_branches:
                if target_branch in issue_branches_with_merged_mr:
                    continue

                logger.debug(f"Trying to create follow-up merge requests for issue {issue}.")
                self._create_followup_merge_request(
                    current_mr_manager=current_mr_manager,
                    followup_mr_data=followup_mr_data,
                    target_branch=target_branch)
                issue_branches_with_merged_mr.add(target_branch)

            issue.add_followups_created_comment(
                issue_branches - {followup_mr_data.original_target_branch})

    def _create_followup_merge_request(
            self, current_mr_manager: MergeRequestManager,
            followup_mr_data: FollowupData, target_branch: str):

        new_mr = self._project_manager.create_followup_merge_request(
            target_branch=target_branch, followup_mr_data=followup_mr_data)
        if new_mr is None:  # Dry run case
            return

        new_mr_manager = MergeRequestManager(new_mr)
        new_mr_manager.return_to_development(ReturnToDevelopmentReason.autocreated)

        current_mr_manager.add_followup_creation_comment(FollowupCreationResult(
            branch=target_branch,
            url=new_mr_manager.mr_url,
            successfull=True))
