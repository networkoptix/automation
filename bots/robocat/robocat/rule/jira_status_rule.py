## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import logging
from enum import Enum

import automation_tools.checkers.config as automation_config
from automation_tools.jira import JiraAccessor, JiraError
from automation_tools.jira_helpers import (
    JIRA_STATUS_OPEN,
    JIRA_STATUS_PROGRESS,
    JIRA_STATUS_REVIEW,
)
from jira.exceptions import JIRAError
from requests.exceptions import RequestException

from robocat.config import Config
from robocat.merge_request_manager import MergeRequestManager
from robocat.project_manager import ProjectManager
from robocat.rule.base_rule import (
    ActionRuleExecutionResultClass,
    BaseRule,
    RuleExecutionResultClass,
)

logger = logging.getLogger(__name__)


class JiraStatusRuleExecutionResultClass(ActionRuleExecutionResultClass, Enum):
    """The results of the Jira status rule; it never blocks the merge."""

    def __bool__(self):
        """Always true: moving a Jira Issue is help, not a check."""
        return True


class MergeRequestState(Enum):
    """The state of an open MR that decides where its Jira Issues go; the value is for the log."""

    Draft = "a draft"
    Open = "ready"


class JiraStatusRule(BaseRule):
    """Moves the Jira Issues of an MR when the MR becomes a draft or ready."""

    identifier = "jira_status"

    ExecutionResult = JiraStatusRuleExecutionResultClass.create(
        "JiraStatusRuleExecutionResult", {
            "rule_execution_successful": "Jira Issue statuses follow the draft state of the MR",
            "not_eligible": "Merged, without commits, or a follow-up MR: no Jira Issue is moved",
        })

    EPIC_TYPE = "Epic"  # Epics stay as they are: their status follows their Issues.
    MOVES = {  # (MR state, Issue status) -> the status Robocat moves the Issue to.
        (MergeRequestState.Draft, JIRA_STATUS_OPEN): JIRA_STATUS_PROGRESS,
        (MergeRequestState.Open, JIRA_STATUS_OPEN): JIRA_STATUS_PROGRESS,  # Then on to In Review.
        (MergeRequestState.Open, JIRA_STATUS_PROGRESS): JIRA_STATUS_REVIEW,
        (MergeRequestState.Draft, JIRA_STATUS_REVIEW): JIRA_STATUS_PROGRESS,  # Draft again.
    }

    def __init__(self, config: Config, project_manager: ProjectManager, jira: JiraAccessor):
        """Keep the Jira projects that Robocat knows, like the workflow rule."""
        super().__init__(config, project_manager, jira)
        self._project_keys: list[str] = (
            list(self.config.jira.project_mapping.keys())
            if self.config.jira.project_mapping
            else (self.config.jira.project_keys or []))

    def _execute(self, mr_manager: MergeRequestManager) -> RuleExecutionResultClass:
        """Move each Jira Issue of the MR that is behind the draft state of the MR."""
        mr_data = mr_manager.data
        if mr_data.is_merged or not mr_data.has_commits or mr_manager.is_follow_up():
            return self.ExecutionResult.not_eligible

        state = MergeRequestState.Draft if mr_data.work_in_progress else MergeRequestState.Open
        for issue_key in mr_data.issue_keys:
            if issue_key.partition("-")[0] not in self._project_keys:
                continue
            try:
                for _ in self.MOVES:  # A step reads the new status; the limit stops any loop.
                    if not self._move_issue(mr_manager, issue_key, state):
                        break
            except (JiraError, JIRAError, RequestException) as error:  # Must not stop the MR.
                logger.warning(f"{mr_manager}: Cannot move the Jira Issue {issue_key}: {error}")

        return self.ExecutionResult.rule_execution_successful

    def _move_issue(
            self, mr_manager: MergeRequestManager, issue_key: str,
            state: MergeRequestState) -> bool:
        """Move one Jira Issue one step if the table of moves has its status; True if it moved."""
        issue = self.jira.get_issue(issue_key)
        if issue.type_name == self.EPIC_TYPE or issue.has_label(automation_config.IGNORE_LABEL):
            return False
        for (moves_state, status), target in self.MOVES.items():
            if moves_state != state or not issue.has_status(status):
                continue
            before = issue.raw_status
            after = issue.status_name(target) or target  # The Jira name, as in the Jira UI.
            if moved := issue.move_to(target):
                logger.info(f"{mr_manager}: Moved the Jira Issue {issue_key} from {before!r} "
                            f"to {after!r}: the MR is {state.value}.")
            else:
                logger.info(f"{mr_manager}: No transition moves the Jira Issue {issue_key} from "
                            f"{before!r} to {after!r}.")
            return moved
        return False
