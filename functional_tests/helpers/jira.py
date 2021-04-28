import enum
from typing import List, NamedTuple

import jira


class IssueType(enum.Enum):
    Bug = "Bug"
    Crash = "Crash"
    Task = "Task"
    Internal = "Internal"

    @property
    def has_affects_versions(self):
        return self in [IssueType.Bug, IssueType.Crash]


class IssueStatus(enum.Enum):
    Open = "Open"
    InProgress = "In progress"
    Closed = "Closed"
    Done = "Done"
    InReview = "In Review"
    WaitingForQa = "Waiting for QA"
    InQa = "In QA"


class IssueDescription(NamedTuple):
    title: str
    issuetype: IssueType
    versions: List[str]
    status: IssueStatus = IssueStatus.Open


def get_transition_name(
        handler: jira.client.JIRA, issue: jira.resources.Issue, target_status: IssueStatus) -> str:
    transitions = [t for t in handler.transitions(issue) if t["to"]["name"] == target_status.value]
    if not transitions:
        raise RuntimeError(
            f"Cannot find appropriate transition from {issue.fields.status.name!r} to "
            f"{target_status.value!r}")

    return transitions[0]["name"]


def update_issue_data(
        handler: jira.client.JIRA, issue: jira.resources.Issue) -> jira.resources.Issue:
    return handler.issue(issue.key)
