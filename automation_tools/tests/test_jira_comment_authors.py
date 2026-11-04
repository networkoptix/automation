## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import http
import json
import urllib.parse
from typing import Any

import jira
import pytest
import requests
from automation_tools.jira import GitlabBranchDescriptor, JiraIssue, get_current_jira_user
from automation_tools.jira_comments import JiraComment, JiraCommentDataKey, JiraMessageId
from requests.adapters import BaseAdapter

JIRA_URL = "https://jira.example.com"
ISSUE_KEY = "VMS-63055"
ROBOCAT = {  # Robocat's Jira account, as Jira sends it: with its email address.
    "accountId": "61df182a68926d0068c6b714",
    "displayName": "CI Service Account",
    "emailAddress": "robocat@example.com",
    "active": True,
    "accountType": "atlassian",
}
JIRA_AUTOMATION = {  # An app account: Jira Cloud sends no email address (VMS-63055).
    "accountId": "557058:f58131cb-b67d-43c7-b30d-6b58d40bd077",
    "displayName": "Automation for Jira",
    "active": True,
    "timeZone": "GMT",
    "accountType": "app",
}
ROBOCAT_APP = {  # Robocat as an app account: Jira sends no email address for it.
    "accountId": "61df182a68926d0068c6b714",
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


def jira_answer(request: requests.PreparedRequest, status: int, body: Any) -> requests.Response:
    """A Jira HTTP answer: the status and a JSON body."""
    response = requests.Response()
    response.status_code = status
    response.reason = http.HTTPStatus(status).phrase
    response._content = json.dumps(body).encode()
    response.headers["Content-Type"] = "application/json"
    response.url = str(request.url)
    response.request = request
    return response


def comment(number: int, author: dict[str, Any] | None, body: str) -> dict[str, Any]:
    """One comment of the issue, as Jira sends it; an anonymous comment has no author."""
    sent = {"id": str(number), "body": body, "created": "2026-10-28T12:00:00"}
    return sent if author is None else {**sent, "author": author}


class FakeJiraServer(BaseAdapter):
    """A fake Jira server under a real requests session: the jira library stays real."""

    def __init__(self, assignee: dict[str, Any] | None, comments: list[dict[str, Any]],
                 myself: dict[str, Any] = ROBOCAT):
        """The issue with this assignee and these comments; myself: Robocat's own account."""
        super().__init__()
        self.myself = myself
        self.issue = {
            "id": "1063055",
            "key": ISSUE_KEY,
            "fields": {
                "status": {"name": "In Review"},
                "project": {"key": "VMS"},
                "issuetype": {"name": "Bug"},
                "labels": [],
                "fixVersions": [],
                "assignee": assignee,
            },
        }
        self.comments = comments

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        """Answer one request like Jira; fail the test on a request it does not expect."""
        method = str(request.method)
        path = urllib.parse.urlsplit(str(request.url)).path
        if (method, path) == ("GET", "/rest/api/2/myself"):
            return jira_answer(request, 200, self.myself)
        if (method, path) == ("GET", f"/rest/api/2/issue/{ISSUE_KEY}"):
            return jira_answer(request, 200, self.issue)
        if method == "GET" and path.startswith("/rest/api/2/issue/") and path.endswith("/comment"):
            return jira_answer(request, 200, {
                "comments": self.comments, "startAt": 0,
                "maxResults": len(self.comments), "total": len(self.comments)})
        raise AssertionError(f"Unexpected Jira request: {method} {path}")

    def close(self):
        """Nothing to close."""


def read_issue(server: FakeJiraServer) -> JiraIssue:
    """The issue, read with the real jira client from the fake server."""
    client = jira.JIRA(server=JIRA_URL, get_server_info=False)
    client._session.mount(JIRA_URL, server)
    return JiraIssue(jira_handler=client, issue=client.issue(ISSUE_KEY), branch_mapping={})


@pytest.fixture(autouse=True)
def fresh_current_user():
    """Each test reads Robocat's account from its own fake server."""
    get_current_jira_user.cache_clear()


class TestJiraAuthorsWithoutEmail:
    """Jira Cloud sends no email for app accounts and hidden emails (AUT-58)."""

    def test_robocat_finds_its_comments_next_to_an_app_comment(self):
        """An app comment does not crash Robocat; only Robocat's own comments count."""
        issue = read_issue(FakeJiraServer(assignee=ROBOCAT, comments=[
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
        issue = read_issue(FakeJiraServer(assignee=ROBOCAT, comments=[
            comment(1, None, "An anonymous comment."),
            comment(2, ROBOCAT, MERGED_COMMENT),
        ]))

        assert [c.message_id for c in issue.bot_comments()] == [JiraMessageId.MrMergedToBranch]

    def test_robocat_as_app_account_without_email(self):
        """Robocat's own account may have no email (an app account): it finds its comments."""
        issue = read_issue(FakeJiraServer(assignee=ROBOCAT, myself=ROBOCAT_APP, comments=[
            comment(1, ROBOCAT_APP, MERGED_COMMENT),
        ]))

        assert [c.message_id for c in issue.bot_comments()] == [JiraMessageId.MrMergedToBranch]

    def test_assignee_without_email(self):
        """An assignee who hides the email address is read with an empty email."""
        issue = read_issue(FakeJiraServer(assignee=HIDDEN_EMAIL_USER, comments=[]))

        assignee = issue.assignee
        assert assignee is not None
        assert (assignee.name, assignee.email, assignee.username) == (
            "Hidden Email User", "", HIDDEN_EMAIL_USER["accountId"])
