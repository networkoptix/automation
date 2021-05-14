import pytest

from automation_tools.tests.fixtures import jira, repo_accessor
from automation_tools.tests.mocks.git_mocks import CommitMock, BranchMock
from bots.workflow_police.police.app import WorkflowEnforcer


@pytest.fixture
def police_test_repo(repo_accessor):
    vms1_commit_mock = CommitMock(repo_accessor.repo, sha="12345", message="VMS-1: Fix bug")
    vms2_commit_mock = CommitMock(
        repo_accessor.repo, sha="6789A", message="VMS-2: Fix another bug")
    vms3_commit_mock = CommitMock(
        repo_accessor.repo, sha="BCDEF", message="VMS-3: Fix brand new bug")
    repo_accessor.repo.branches["origin/master"] = BranchMock(
        repo_accessor.repo, name="master", commits=[vms1_commit_mock, vms2_commit_mock])
    repo_accessor.repo.branches["origin/vms_4.2"] = BranchMock(
        repo_accessor.repo, name="vms_4.2", commits=[vms2_commit_mock])
    repo_accessor.repo.branches["origin/vms_4.2_patch"] = BranchMock(
        repo_accessor.repo, name="vms_4.2_patch", commits=[vms1_commit_mock,  vms3_commit_mock])

    return repo_accessor


@pytest.fixture
def workflow_checker(jira, police_test_repo):
    return WorkflowEnforcer({}, jira, police_test_repo)._workflow_checker


@pytest.fixture
def bot(monkeypatch, jira, police_test_repo):
    monkeypatch.setenv("BOT_NAME", "Police")
    return WorkflowEnforcer({}, jira, police_test_repo)
