from pathlib import Path
import pytest
import shutil
import sys
from tempfile import TemporaryDirectory

import git
import gitlab
import yaml

import helpers.tests_config

from robocat.app import Bot


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
        "approvals_before_merge": helpers.tests_config.APPROVALS_NUMBER,
        "visibility": "internal",
    })

    yield project
    project.delete()


@pytest.fixture(scope="session")
def repo(request, project):
    tmp_directory = TemporaryDirectory()
    repo_directory = Path(tmp_directory.name) / "repo"
    sample_repo_directory = Path(__file__).parent.resolve() / "test_data/repo"
    shutil.copytree(sample_repo_directory, repo_directory)

    repo = git.Repo.init(repo_directory)
    origin = repo.create_remote('origin', project.ssh_url_to_repo)
    repo.index.add([str(x) for x in Path(repo_directory).iterdir() if x.name != ".git"])
    repo.index.commit("Initial commit")
    origin.push("master")

    yield repo
    tmp_directory.cleanup()


@pytest.fixture(scope="session")
def bot(pytestconfig, project):
    filepath = Path(__file__).parent.resolve() / "test_data/bot_config.yaml"
    with open(filepath, 'r') as f:
        config = yaml.safe_load(f)
    config["jira"]["password"] = pytestconfig.getoption("jira_password")
    return Bot(config, project.id)
