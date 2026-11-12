## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import jira
import pytest
from automation_tools.jira import JiraAccessor, JiraIssue
from automation_tools.jira_helpers import (
    JIRA_STATUS_CLOSED,
    JIRA_STATUS_OPEN,
    JIRA_STATUS_PROGRESS,
    JIRA_STATUS_REVIEW,
)
from automation_tools.tests.fake_jira_server import (
    JIRA_URL,
    NXLIB_ISSUE,
    NXLIB_START_DEVELOPMENT,
    NXLIB_TRANSITIONS,
    FakeJiraServer,
    Transition,
    jira_client_on,
)

VMS_BUG = {  # VMS-63404, a Bug in "In Review".
    **NXLIB_ISSUE, "id": "63404", "key": "VMS-63404",
    "self": f"{JIRA_URL}/rest/api/2/issue/VMS-63404",
    "fields": {
        **NXLIB_ISSUE["fields"], "status": {"name": "In Review"}, "project": {"key": "VMS"},
        "issuetype": {"name": "Bug"},
    },
}
VMS_REJECT = Transition("201", "Reject", "Closed")  # VMS-63404.
VMS_CLOSE = Transition("71", "Close", "Closed")  # VMS-61079, an Internal Issue.
VMS_CONFIG = {"VMS": {"moves": {(JIRA_STATUS_REVIEW, JIRA_STATUS_CLOSED): "Close"}}}


def vms_bug_with(monkeypatch, *transitions: Transition) -> tuple[JiraIssue, FakeJiraServer]:
    """VMS-63404 read by the real JiraAccessor with VMS_CONFIG; Jira offers these transitions."""
    server = FakeJiraServer([VMS_BUG], {"VMS": {"In Review": list(transitions)}})
    monkeypatch.setattr("jira.JIRA", jira_client_on(server))
    accessor = JiraAccessor(
        url=JIRA_URL, login="robocat", password="token", timeout=10, retries=0,
        project_keys={"VMS"}, custom_project_configs=VMS_CONFIG)
    return accessor.get_issue("VMS-63404"), server


@pytest.fixture
def server() -> FakeJiraServer:
    """The fake Jira server with NXLIB-434."""
    return FakeJiraServer([NXLIB_ISSUE], NXLIB_TRANSITIONS)


@pytest.fixture
def issue(server: FakeJiraServer) -> JiraIssue:
    """NXLIB-434 read with the real jira client from the fake server."""
    client = jira.JIRA(server=JIRA_URL, get_server_info=False)
    client._session.mount(JIRA_URL, server)
    return JiraIssue(jira_handler=client, issue=client.issue("NXLIB-434"), branch_mapping={})


class TestJiraIssueStatus:
    """Status names of other projects match without case (AUT-17)."""

    def test_status_matches_without_case(self, issue):
        """"OPEN" is the standard status "Open"; it is not "In progress"."""
        assert issue.has_status(JIRA_STATUS_OPEN)
        assert not issue.has_status(JIRA_STATUS_PROGRESS)

    def test_move_uses_the_transition_to_the_status(self, issue, server):
        """"In progress" finds the transition to "In Progress" and Jira gets its id."""
        assert issue.move_to(JIRA_STATUS_PROGRESS)

        assert server.transitions_made == [NXLIB_START_DEVELOPMENT]

    def test_move_without_transition(self, issue, server):
        """No transition leads to "In Review": nothing is sent to Jira."""
        assert not issue.move_to(JIRA_STATUS_REVIEW)

        assert server.transitions_made == []


class TestProjectTransitions:
    """A Project config can name the transition of a move between two statuses (AUT-59)."""

    def test_finalize_uses_the_transition_of_the_config(self, monkeypatch):
        """Two transitions lead to "Closed": Robocat uses "Close", which the config names."""
        issue, server = vms_bug_with(monkeypatch, VMS_REJECT, VMS_CLOSE)

        assert issue.try_finalize() is True

        assert server.transitions_made == [VMS_CLOSE]

    def test_move_does_not_use_another_transition(self, monkeypatch):
        """Jira offers only "Reject" to "Closed": Robocat does not move the Issue."""
        issue, server = vms_bug_with(monkeypatch, VMS_REJECT)

        assert not issue.move_to(JIRA_STATUS_CLOSED)

        assert server.transitions_made == []
