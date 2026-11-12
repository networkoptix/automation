## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from collections.abc import Mapping
from typing import Final, Literal, TypedDict

import jira.exceptions

import automation_tools.utils


class JiraError(automation_tools.utils.AutomationError):
    def __init__(self, message: str, jira_error: jira.exceptions.JIRAError = None):
        super().__init__(message + (': ' + str(jira_error) if jira_error else ""))


class JiraStatusChangeError(JiraError):
    pass


JiraStatus = Literal[
    "review", "progress", "closed", "qa", "ready_to_merge", "open", "inqa",
    "pending_verification"]

JIRA_STATUS_REVIEW: Final = "review"  # Final, so pyright infers Literal["review"] rather than str
JIRA_STATUS_PROGRESS: Final = "progress"
JIRA_STATUS_CLOSED: Final = "closed"
JIRA_STATUS_QA: Final = "qa"
JIRA_STATUS_READY_TO_MERGE: Final = "ready_to_merge"
JIRA_STATUS_OPEN: Final = "open"
JIRA_STATUS_INQA: Final = "inqa"
JIRA_STATUS_VERIFICATION: Final = "pending_verification"


JIRA_TRANSITION_WORKFLOW_FAILURE: Final = "workflow_failure"


StatusMove = tuple[JiraStatus, JiraStatus]


class JiraTransitions(TypedDict):
    """The Jira names of the transitions that Robocat uses by name."""
    workflow_failure: str


class JiraProjectConfig(TypedDict):
    """The Jira names of the statuses, transitions and status moves of a Jira Project."""
    statuses: Mapping[JiraStatus, str]
    transitions: JiraTransitions
    moves: Mapping[StatusMove, str]


class JiraProjectConfigOverride(TypedDict, total=False):
    """The names of a Jira Project that differ from the standard JiraProjectConfig."""
    statuses: Mapping[JiraStatus, str]
    transitions: JiraTransitions
    moves: Mapping[StatusMove, str]
