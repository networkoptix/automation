## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import logging
import re
from enum import Enum

from automation_tools.jira import JiraAccessor
from automation_tools.jira_comments import JiraComment, JiraMessageId
from robocat.config import Config
from robocat.merge_request_manager import MergeRequestManager
from robocat.project_manager import ProjectManager
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
from robocat.note import find_last_comment, MessageId
import automation_tools.utils
import robocat.merge_request_actions.follow_up_actions

logger = logging.getLogger(__name__)


class FollowUpRuleExecutionResultClass(RuleExecutionResultClass, Enum):
    def __bool__(self):
        return self == self.rule_execution_successful

    def __str__(self):
        return str(self.value)


class FollowUpRule(BaseRule):
    identifier = "follow_up"

    ExecutionResult = FollowUpRuleExecutionResultClass.create(
        "FollowUpRuleExecutionResult", {
            "rule_execution_successful": "All operations completed successfully",
            "not_eligible": "Merge request is not eligible for cherry-pick",
            "rule_execution_failed": "Some of operations failed",
            "filtered_out": "Rule execution was filtered out due to configuration",
        })

    def __init__(self, config: Config, project_manager: ProjectManager, jira: JiraAccessor):
        super().__init__(config, project_manager, jira)
        self._needs_robocat_approval = self.config.repo.need_code_owner_approval
        self._default_branch_project_mapping = config.jira.project_mapping

    def _execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        logger.debug(f"Executing follow-up rule with {mr_manager}...")

        mr_data = mr_manager.data
        if not mr_data.is_merged:
            logger.info(f"{mr_manager}: Merge request isn't merged. Cannot cherry-pick.")
            return self.ExecutionResult.not_eligible

        if self.config.follow_up_rule is not None:
            rule_config = self.config.follow_up_rule
            if rule_config.excluded_issue_title_patterns:
                logger.debug(
                    f"Checking the Issue title filters against the title {mr_data.title!r}")
                for regexp in rule_config.excluded_issue_title_patterns:
                    if re.match(pattern=regexp, string=mr_data.title):
                        logger.info(
                            f"{mr_manager}: Skipping follow-up because the Issue title matched "
                            f"the pattern {regexp!r}.")
                        return self.ExecutionResult.filtered_out

        if not (jira_issues := self.jira.get_issues(mr_manager.data.issue_keys)):
            # TODO: Add comment to MR informing the user that we can't find any attached issue and
            # that he or she should double-check if it is normal.
            logger.info(
                f"{mr_manager}: Can't detect attached issue for the merge request. "
                "Skipping cherry-pick.")
            return self.ExecutionResult.not_eligible

        # Intercept all the exceptions and leave a comment in Jira issues about failing of merge
        # request follow-up processing. TODO: Add more sophisticated error processing.
        try:
            # A follow-up Merge Request. Do not try to create follow-up for it.
            if mr_manager.is_follow_up():
                logger.debug(f"{mr_manager}: The Merge Request is a follow-up itself.")
                mr_manager.add_comment_with_message_id(MessageId.FollowUpNotNeeded)
                return self.ExecutionResult.rule_execution_successful

            # Primary merge request.
            # Check all Jira issues which are mentioned by the current merge request and create
            # follow-up merge requests for all their branches (defined by "fixVersions" field),
            # except for the target branch of this merge request.
            logger.info(
                f"{mr_manager}: Merge request is a primary merge request. Trying to move to "
                "QA/close single-branch Jira issues and create follow-up merge requests.")
            draft_follow_up_requested_comment = find_last_comment(
                notes=mr_manager.notes(),
                message_id=MessageId.CommandSetDraftFollowUpMode)
            robocat.merge_request_actions.follow_up_actions.create_follow_up_merge_requests(
                jira=self.jira,
                project_manager=self.project_manager,
                mr_manager=mr_manager,
                set_draft_flag=draft_follow_up_requested_comment is not None,
                approve_by_robocat=self._needs_robocat_approval,
                default_branch_project_mapping=self._default_branch_project_mapping)
            return self.ExecutionResult.rule_execution_successful

        except Exception as error:
            stack_trace_repr, exception_info = automation_tools.utils.get_exception_info(error)
            logger.error(
                f"{mr_manager}: Follow-up processing was crashed with exception {exception_info}: "
                f"{stack_trace_repr}")
            for issue in jira_issues:
                issue.add_comment(JiraComment(
                    message_id=JiraMessageId.FollowUpError,
                    params={"error": str(error), "mr_url": mr_data.url, "mr_name": mr_data.title}))
            return self.ExecutionResult.rule_execution_failed
