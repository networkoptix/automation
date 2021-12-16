import pytest

from automation_tools.tests.fixtures import jira, repo_accessor
from automation_tools.tests.mocks.git_mocks import CommitMock, BranchMock
from bots.workflow_police.police.app import WorkflowEnforcer


@pytest.fixture
def police_test_repo(repo_accessor):
    vms1_commit_mock = CommitMock(repo_accessor.repo, sha="1234", message="VMS-1: Fix bug")
    vms2_commit_mock = CommitMock(
        repo_accessor.repo, sha="5678", message="VMS-2: Fix another bug")
    vms3_commit_mock = CommitMock(
        repo_accessor.repo, sha="9ABC", message="VMS-3: Fix brand new bug")
    vms4_commit_mock = CommitMock(
        repo_accessor.repo, sha="DEF", message="VMS-4: Fix bug in master")
    mobile1_commit_mock = CommitMock(repo_accessor.repo, sha="23456", message="MOBILE-1: Fix bug")
    cb1_commit_mock = CommitMock(repo_accessor.repo, sha="34567", message="CB-1: Fix bug")

    repo_accessor.repo.branches["origin/master"] = BranchMock(
        repo_accessor.repo, name="master",
        commits=[
            vms1_commit_mock,
            vms2_commit_mock,
            vms4_commit_mock,
            mobile1_commit_mock,
            cb1_commit_mock,
        ])
    repo_accessor.repo.branches["origin/vms_4.2"] = BranchMock(
        repo_accessor.repo, name="vms_4.2", commits=[vms2_commit_mock])
    repo_accessor.repo.branches["origin/vms_4.2_patch"] = BranchMock(
        repo_accessor.repo, name="vms_4.2_patch", commits=[vms1_commit_mock,  vms3_commit_mock])
    repo_accessor.repo.branches["origin/mobile_21.1"] = BranchMock(
        repo_accessor.repo, name="mobile_21.1", commits=[mobile1_commit_mock])
    repo_accessor.repo.branches["origin/cloud_backend_20.1"] = BranchMock(
        repo_accessor.repo, name="cloud_backend_20.1", commits=[cb1_commit_mock])

    return repo_accessor


@pytest.fixture
def workflow_checker(jira, police_test_repo):
    return WorkflowEnforcer({"jira": {}}, jira, police_test_repo)._workflow_checker


@pytest.fixture
def bot(monkeypatch, jira, police_test_repo):
    monkeypatch.setenv("BOT_NAME", "Police")
    return WorkflowEnforcer({"jira": {}}, jira, police_test_repo)
