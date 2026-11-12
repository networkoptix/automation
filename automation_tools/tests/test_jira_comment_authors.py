## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from typing import Any

import pytest
from automation_tools.jira import GitlabBranchDescriptor, JiraIssue, get_current_jira_user
from automation_tools.jira_comments import JiraComment, JiraCommentDataKey, JiraMessageId
from automation_tools.tests.fake_jira_server import (
    JIRA_URL,
    ROBOCAT,
    FakeJiraServer,
    jira_client_on,
)

ISSUE_KEY = "VMS-63055"
JIRA_AUTOMATION = {  # An app account: Jira Cloud sends no email address (VMS-63055).
    "accountId": "557058:f58131cb-b67d-43c7-b30d-6b58d40bd077",
    "displayName": "Automation for Jira",
    "active": True,
    "timeZone": "GMT",
    "accountType": "app",
}
ROBOCAT_APP = {  # Robocat as an app account: Jira sends no email address for it.
    "accountId": "65660dbf14ddd6374cf258fe",
    "displayName": "CI Service Account",
    "active": True,
    "accountType": "app",
}
HIDDEN_EMAIL_USER = {  # A person who hides the email address: Jira sends none.
    "accountId": "712020:00000000-0000-0000-0000-000000000058",
    "displayName": "Hidden Email User",
    "active": True,
    "timeZone": "GMT",
    "accountType": "atlassian",
}
MERGED_BRANCH = "dev/nx:master"
MERGED_COMMENT = str(JiraComment(  # The comment Robocat adds after the merge (bot.py).
    message_id=JiraMessageId.MrMergedToBranch,
    params={"mr_name": "VMS-63055: Fix", "mr_url": "https://gitlab/mr/41179",
            "mr_branch": MERGED_BRANCH},
    data={JiraCommentDataKey.MrId.name: 41179, JiraCommentDataKey.OriginalMrId.name: 41179,
          JiraCommentDataKey.MrBranch.name: MERGED_BRANCH}))


def comment(number: int, author: dict[str, Any] | None, body: str) -> dict[str, Any]:
    """One comment of the issue, as Jira sends it; an anonymous comment has no author."""
    sent = {"id": str(number), "body": body, "created": "2026-10-28T12:00:00"}
    return sent if author is None else {**sent, "author": author}


def jira_with(assignee: dict[str, Any] | None, comments: list[dict[str, Any]],
              myself: dict[str, Any] = ROBOCAT) -> FakeJiraServer:
    """The fake Jira with one VMS Bug in review: this assignee and these comments."""
    issue = {"id": "1063055", "key": ISSUE_KEY, "fields": {
        "status": {"name": "In Review"}, "project": {"key": "VMS"},
        "issuetype": {"name": "Bug"}, "labels": [], "fixVersions": [], "assignee": assignee}}
    return FakeJiraServer([issue], {}, existing_comments={ISSUE_KEY: comments}, myself=myself)


def read_issue(server: FakeJiraServer) -> JiraIssue:
    """The issue, read with the real jira client from the fake server."""
    client = jira_client_on(server)(server=JIRA_URL)
    return JiraIssue(jira_handler=client, issue=client.issue(ISSUE_KEY), branch_mapping={})


@pytest.fixture(autouse=True)
def fresh_current_user():
    """Each test reads Robocat's account from its own fake server."""
    get_current_jira_user.cache_clear()


class TestJiraAuthorsWithoutEmail:
    """Jira Cloud sends no email for app accounts and hidden emails (AUT-58)."""

    def test_robocat_finds_its_comments_next_to_an_app_comment(self):
        """An app comment does not crash Robocat; only Robocat's own comments count."""
        issue = read_issue(jira_with(assignee=ROBOCAT, comments=[
            comment(1, JIRA_AUTOMATION, "This ticket was moved to Blocked."),
            comment(2, ROBOCAT, MERGED_COMMENT),
            comment(3, HIDDEN_EMAIL_USER, MERGED_COMMENT),  # A copy by a person: not Robocat's.
        ]))

        assert [c.message_id for c in issue.bot_comments()] == [JiraMessageId.MrMergedToBranch]
        assert issue.has_bot_comment(JiraMessageId.MrMergedToBranch)
        assert issue.declared_merged_branches() == {
            GitlabBranchDescriptor.from_string(MERGED_BRANCH): {41179}}

    def test_robocat_finds_its_comments_next_to_an_anonymous_comment(self):
        """A comment without an author (Jira's schema allows it: anonymous) does not crash."""
        issue = read_issue(jira_with(assignee=ROBOCAT, comments=[
            comment(1, None, "An anonymous comment."),
            comment(2, ROBOCAT, MERGED_COMMENT),
        ]))

        assert [c.message_id for c in issue.bot_comments()] == [JiraMessageId.MrMergedToBranch]

    def test_robocat_as_app_account_without_email(self):
        """Robocat's own account may have no email (an app account): it finds its comments."""
        issue = read_issue(jira_with(assignee=ROBOCAT, myself=ROBOCAT_APP, comments=[
            comment(1, ROBOCAT_APP, MERGED_COMMENT),
        ]))

        assert [c.message_id for c in issue.bot_comments()] == [JiraMessageId.MrMergedToBranch]

    def test_assignee_without_email(self):
        """An assignee who hides the email address is read with an empty email."""
        issue = read_issue(jira_with(assignee=HIDDEN_EMAIL_USER, comments=[]))

        assignee = issue.assignee
        assert assignee is not None
        assert (assignee.name, assignee.email, assignee.username) == (
            "Hidden Email User", "", HIDDEN_EMAIL_USER["accountId"])
