## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import jira
import pytest
from automation_tools.jira import JiraIssue
from automation_tools.jira_helpers import (
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
)


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
