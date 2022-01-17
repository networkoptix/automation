from pathlib import Path
import pytest

import automation_tools.git
import automation_tools.jira
import automation_tools.tests.mocks.jira
from automation_tools.tests.mocks.git_mocks import (
    RepoMock, RemoteMock, BOT_EMAIL, BOT_NAME, BOT_USERNAME)


@pytest.fixture
def jira(jira_issues, monkeypatch):
    def init_with_mock(this):
        project_keys_list = list({i["key"].partition("-")[0] for i in jira_issues})
        this.project_keys = set(project_keys_list)
        this._jira = automation_tools.tests.mocks.jira.Jira()

    def version_to_branch_mappings(obj):
        return {p: obj._version_to_branch_mapping(p) for p in obj.project_keys}

    monkeypatch.setattr(automation_tools.jira.JiraAccessor, "__init__", init_with_mock)
    monkeypatch.setattr(
        automation_tools.jira.JiraAccessor,
        "version_to_branch_mappings",
        version_to_branch_mappings)

    accessor = automation_tools.jira.JiraAccessor()
    if jira_issues:
        for issue_data in jira_issues:
            accessor._jira.add_mock_issue(**issue_data)

    return accessor


@pytest.fixture
def repo_accessor(monkeypatch):
    monkeypatch.setattr(automation_tools.git.git, "Repo", RepoMock)
    monkeypatch.setattr(
        automation_tools.git.git.remote, "Remote", RemoteMock)
    committer = automation_tools.utils.User(
        email=BOT_EMAIL, name=BOT_NAME, username=BOT_USERNAME)
    return automation_tools.git.Repo(Path("foo_path"), "foo_url", committer=committer)
