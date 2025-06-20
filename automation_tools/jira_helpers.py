## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from typing import TypedDict

import jira.exceptions

import automation_tools.utils


class JiraError(automation_tools.utils.AutomationError):
    def __init__(self, message: str, jira_error: jira.exceptions.JIRAError = None):
        super().__init__(message + (': ' + str(jira_error) if jira_error else ""))


class JiraStatusChangeError(JiraError):
    pass


JIRA_STATUS_REVIEW = "review"
JIRA_STATUS_PROGRESS = "progress"
JIRA_STATUS_CLOSED = "closed"
JIRA_STATUS_QA = "qa"
JIRA_STATUS_READY_TO_MERGE = "ready_to_merge"
JIRA_STATUS_OPEN = "open"
JIRA_STATUS_INQA = "inqa"
JIRA_STATUS_VERIFICATION = "pending_verification"


JIRA_TRANSITION_WORKFLOW_FAILURE = "workflow_failure"


JiraStatuses = TypedDict("JiraStatuses", {
    JIRA_STATUS_REVIEW: str,
    JIRA_STATUS_PROGRESS: str,
    JIRA_STATUS_CLOSED: str,
    JIRA_STATUS_QA: str,
    JIRA_STATUS_READY_TO_MERGE: str,
    JIRA_STATUS_OPEN: str,
    JIRA_STATUS_INQA: str,
    JIRA_STATUS_VERIFICATION: str,
})


JiraTransitions = TypedDict("JiraTransitions", {JIRA_TRANSITION_WORKFLOW_FAILURE: str})


class JiraProjectConfig(TypedDict):
    statuses: JiraStatuses
    transitions: JiraTransitions
