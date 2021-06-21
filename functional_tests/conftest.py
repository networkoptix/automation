import os
from pathlib import Path
import pytest
import shutil
import sys
from tempfile import TemporaryDirectory
from typing import List

import git
import gitlab
import jira
import yaml

import helpers.jira
import helpers.tests_config
from robocat.app import Bot


def pytest_generate_tests(metafunc):
    os.environ["BOT_NAME"] = "Robocat"


def pytest_addoption(parser):
    parser.addoption("--jira-password", action="store", default="FOOBAR")


@pytest.fixture(scope="session")
def gitlab_instance():
    return gitlab.Gitlab.from_config("nx_gitlab")


@pytest.fixture(scope="session")
def project(request, gitlab_instance):
    groups = list(gitlab_instance.groups.list(search=helpers.tests_config.FUNCTEST_GROUP_NAME))
    assert len(groups) == 1, (
        f"There are more than one groups with the name {helpers.tests_config.FUNCTEST_GROUP_NAME}")
    group_id = groups[0].id
    project = gitlab_instance.projects.create({
        "name": helpers.tests_config.FUNCTEST_PROJECT_NAME,
        "namespace_id": group_id,
        "approvals_before_merge": len(helpers.tests_config.APPROVERS),
        "merge_method": "ff",
        "only_allow_merge_if_all_discussions_are_resolved": True,
        "visibility": "internal",
    })

    yield project
    project.delete()


@pytest.fixture(scope="session")
def initial_repo(request, project):
    tmp_directory = TemporaryDirectory()
    repo_directory = Path(tmp_directory.name) / "repo"
    sample_repo_directory = Path(__file__).parent.resolve() / "test_data/repo"
    shutil.copytree(sample_repo_directory, repo_directory)

    repo = git.Repo.init(repo_directory)
    origin = repo.create_remote('origin', project.ssh_url_to_repo)
    repo.index.add([str(x) for x in Path(repo_directory).iterdir() if x.name != ".git"])
    repo.index.commit("Initial commit")
    origin.push("master")

    try:
        for branch_name in helpers.tests_config.TARGET_BRANCHES:
            if branch_name == "master":
                continue
            helpers.repo.create_branch(repo, branch_name)
            (Path(repo.working_dir) / "branch_name.txt").write_text(branch_name)
            helpers.repo.create_and_push_commit(
                repo, branch_name=branch_name,
                updated_files=["branch_name.txt"],
                message=f"Add branch name file ({branch_name})")

        repo.head.reference = repo.heads.master
        repo.head.reset(commit="master", index=True, working_tree=True)

        yield repo

    finally:
        tmp_directory.cleanup()


@pytest.fixture(scope="session")
def bot_config(pytestconfig):
    filepath = Path(__file__).parent.resolve() / "test_data/bot_config.yaml"
    with open(filepath, 'r') as f:
        config = yaml.safe_load(f)
    config["jira"]["password"] = pytestconfig.getoption("jira_password")
    return config


@pytest.fixture
def bot(bot_config, project):
    return Bot(bot_config, project.id)


@pytest.fixture(scope="session")
def jira_handler(bot_config):
    jira_config = bot_config["jira"]
    jira_handler = jira.JIRA(
        server=jira_config["url"],
        basic_auth=(jira_config["login"], jira_config["password"]),
        max_retries=jira_config["retries"],
        timeout=jira_config["timeout"])
    return jira_handler


@pytest.fixture()
def jira_issues(jira_handler, issue_descriptions: List[helpers.jira.IssueDescription]):
    issues = []
    try:
        for descr in issue_descriptions:
            versions = [{"name": v} for v in descr.versions]
            issue_create_parameters = {
                "project": helpers.tests_config.JIRA_PROJECT,
                "summary": descr.title,
                "issuetype": {"name": descr.issuetype.value},
                "assignee": {"accountId": helpers.tests_config.JIRA_ASSIGNEE_ID},
                "fixVersions": versions,
                "labels": ["robocat_test_issue"]
            }
            if descr.issuetype.has_affects_versions:
                issue_create_parameters["versions"] = versions
            issue = jira_handler.create_issue(fields=issue_create_parameters)

            if descr.status is not None:
                transition_name = helpers.jira.get_transition_name(jira_handler, issue, descr.status)
                jira_handler.transition_issue(issue, transition_name)

            issues.append(issue)

        yield issues

    finally:
        for issue in issues:
            issue.delete()


@pytest.fixture()
def repo(initial_repo):
    repo = initial_repo
    repo.remotes.origin.fetch()
    repo.head.reference = repo.heads.master
    repo.head.reset(commit="origin/master", index=True, working_tree=True)
    return repo


@pytest.fixture()
def branch(repo):
    branch.counter += 1
    branch_name = f"test_branch_{branch.counter}"
    repo.create_head(branch_name)
    return branch_name


branch.counter = 0
