## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import urllib.parse
from typing import Any

import automation_tools.git
import git
import gitlab
import jira
import pytest
import requests
from automation_tools.jira import JiraAccessor
from automation_tools.tests.gitlab_constants import BOT_USERNAME
from requests.adapters import BaseAdapter
from robocat.comments import Comment, Emoji
from robocat.project_manager import ProjectManager
from robocat.rule.workflow_check_rule import MAX_DESCRIPTION_LENGTH, WorkflowCheckRule

from tests.fixtures import bot_config
from tests.merge_request_test import (
    GITLAB_URL,
    MERGE_REQUEST_PATH,
    OPEN_MERGE_REQUEST_DATA,
    FakeGitLabServer,
    merge_request_manager,
    mock_gitlab_response,
    posted_comments,
)

JIRA_URL = "https://jira.example.com"
ISSUE_KEY = "CB-1"  # Jira project CB has no allowed Fix Version sets: no version errors.
PROJECT = {  # The fields of the GitLab project that Robocat reads.
    "id": 1,
    "name": "nx",
    "path": "nx",  # The config maps the Jira project CB to "nx".
    "path_with_namespace": "dev/nx",
    "namespace": {"full_path": "dev"},
    "ssh_url_to_repo": "git@gitlab.example.com:dev/nx.git",
}
MERGE_REQUEST = {  # A squash MR for the issue: its commit message need not be its description.
    **OPEN_MERGE_REQUEST_DATA,
    "id": 105,
    "title": f"{ISSUE_KEY}: Fix the bug",
    "web_url": f"{GITLAB_URL}/dev/nx/-/merge_requests/5",
    "draft": False,
    "work_in_progress": False,  # GitLab still sends the old name of "draft"; Robocat reads it.
    "has_conflicts": False,
    "blocking_discussions_resolved": True,
    "squash": True,
    "source_branch": "fix",
    "target_branch": "master",
    "source_project_id": 1,
    "target_project_id": 1,
}
COMMITS = [{"id": OPEN_MERGE_REQUEST_DATA["sha"], "message": f"{ISSUE_KEY}: Fix the bug"}]
ISSUE = {  # The issue as Jira sends it: in progress, assigned to the MR author.
    "id": "10001",
    "key": ISSUE_KEY,
    "fields": {
        "status": {"name": "In progress"},
        "project": {"key": "CB"},
        "issuetype": {"name": "Bug"},
        "labels": [],
        "fixVersions": [],
        "assignee": {"accountId": "712020:developer", "displayName": "Developer", "active": True},
    },
}
TOO_LONG = "Description Message too long! Please shorten it!"


def description(length: int) -> str:
    """An MR description of this length."""
    return ("Шаг 1: проверить merge → master.\n" * length)[:length]


class FakeJiraServer(BaseAdapter):
    """A fake Jira server under a real requests session: the jira library stays real."""

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        """Answer the issue and its project's versions; fail the test on other requests."""
        method = str(request.method)
        path = urllib.parse.urlsplit(str(request.url)).path
        if (method, path) == ("GET", f"/rest/api/2/issue/{ISSUE_KEY}"):
            return mock_gitlab_response(request, 200, ISSUE)
        if (method, path) == ("GET", "/rest/api/2/project/CB/versions"):
            return mock_gitlab_response(request, 200, [])
        raise AssertionError(f"Unexpected Jira request: {method} {path}")

    def close(self):
        """Nothing to close."""


@pytest.fixture
def jira_accessor(monkeypatch) -> JiraAccessor:
    """Robocat's real JiraAccessor and jira client on the fake Jira server."""
    real_client_class = jira.JIRA

    def client(**_: Any) -> jira.JIRA:
        """The real jira client on the fake server (no server info request)."""
        jira_client = real_client_class(server=JIRA_URL, get_server_info=False)
        session = jira_client._session
        assert session is not None  # The real client makes its session in __init__().
        session.mount(JIRA_URL, FakeJiraServer())
        return jira_client

    monkeypatch.setattr(jira, "JIRA", client)
    return JiraAccessor(
        url=JIRA_URL, login="robocat", password="token", timeout=20, retries=0,
        project_keys={"CB"})


@pytest.fixture
def server() -> FakeGitLabServer:
    """A GitLab with the project and the commit of the MR."""
    return FakeGitLabServer({
        ("GET", "/projects/1"): (200, PROJECT),
        ("GET", f"{MERGE_REQUEST_PATH}/commits"): (200, COMMITS),
    })


@pytest.fixture
def workflow_rule(server, jira_accessor, bot_config, tmp_path) -> WorkflowCheckRule:
    """The real workflow rule on the fake GitLab and Jira servers, with a real local git repo."""
    session = requests.Session()
    session.mount(GITLAB_URL, server)
    raw_gitlab = gitlab.Gitlab(GITLAB_URL, private_token="token", session=session)
    git.Repo.init(tmp_path)
    repo = automation_tools.git.Repo(tmp_path, url="unused")
    project_manager = ProjectManager(raw_gitlab.projects.get(1), BOT_USERNAME, repo=repo)
    return WorkflowCheckRule(bot_config, project_manager, jira_accessor)


class TestDescriptionLength:
    """Robocat blocks an MR whose description is longer than the limit (AUT-282)."""

    def test_too_long_description_blocks_the_merge(self, workflow_rule, server):
        """One character over the limit: one thread with the reason, the merge is blocked."""
        too_long = {**MERGE_REQUEST, "description": description(MAX_DESCRIPTION_LENGTH + 1)}

        assert not workflow_rule.execute(merge_request_manager(server, too_long))
        assert not workflow_rule.execute(merge_request_manager(server, too_long))  # Next event.

        assert posted_comments(server) == [Comment.WorkflowDescriptionTooLong]
        body = server.notes[0]["body"]
        assert TOO_LONG in body
        assert f"has\n{MAX_DESCRIPTION_LENGTH + 1} characters, the maximum is " in body
        assert server.notes[0]["resolvable"]  # A thread: it blocks the merge.
        assert Emoji.BAD_ISSUE in [emoji["name"] for emoji in server.award_emoji]

    def test_description_at_the_limit_passes(self, workflow_rule, server):
        """Exactly at the limit: no comment, the workflow check passes."""
        at_limit = {**MERGE_REQUEST, "description": description(MAX_DESCRIPTION_LENGTH)}

        assert workflow_rule.execute(merge_request_manager(server, at_limit))

        assert server.notes == []
        assert Emoji.BAD_ISSUE not in [emoji["name"] for emoji in server.award_emoji]
