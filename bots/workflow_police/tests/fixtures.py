from pathlib import Path
import pytest

from automation_tools.tests.fixtures import jira, repo_accessor
from automation_tools.tests.mocks.git_mocks import CommitMock, BranchMock
from automation_tools.tests.mocks.merge_request import MergeRequestMock
from automation_tools.tests.mocks.project import ProjectMock
from automation_tools.utils import parse_config_file
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
    repo_accessor.repo.branches["origin/vms_5.0_patch"] = BranchMock(
        repo_accessor.repo, name="vms_5.0_patch", commits=[vms1_commit_mock,  vms3_commit_mock])
    repo_accessor.repo.branches["origin/mobile_21.1"] = BranchMock(
        repo_accessor.repo, name="mobile_21.1", commits=[mobile1_commit_mock])
    repo_accessor.repo.branches["origin/mobile_22.1"] = BranchMock(
        repo_accessor.repo, name="mobile_22.1", commits=[mobile1_commit_mock])
    repo_accessor.repo.branches["origin/mobile_22.3"] = BranchMock(
        repo_accessor.repo, name="mobile_22.3", commits=[mobile1_commit_mock])
    repo_accessor.repo.branches["origin/mobile_22.4"] = BranchMock(
        repo_accessor.repo, name="mobile_22.4", commits=[mobile1_commit_mock])
    repo_accessor.repo.branches["origin/cloud_backend_20.1"] = BranchMock(
        repo_accessor.repo, name="cloud_backend_20.1", commits=[cb1_commit_mock])

    return repo_accessor


@pytest.fixture
def mr_states():
    return [{}]


@pytest.fixture
def project(mr_states):
    project = ProjectMock()
    # create merge request mock object bonded to "project".
    for mr_state in mr_states:
        MergeRequestMock(project=project, **mr_state)
    return project


@pytest.fixture
def workflow_enforcer(monkeypatch, jira, police_test_repo, project):
    config = parse_config_file(Path(__file__).parents[1].resolve() / "config.test.yaml")
    del config["gitlab"]
    del config["jira"]

    def _update_repos(obj, *_, **__):
        obj._repos["default"] = police_test_repo
        return police_test_repo

    def _related_project_by_class(obj, *_, **__):
        return project

    monkeypatch.setattr(WorkflowEnforcer, "_update_repos", _update_repos)
    monkeypatch.setattr(WorkflowEnforcer, "_related_project_by_class", _related_project_by_class)

    workflow_enforcer = WorkflowEnforcer(config)
    workflow_enforcer._jira = jira
    workflow_enforcer._gitlab = project.manager.gitlab

    return workflow_enforcer


@pytest.fixture
def workflow_checker(workflow_enforcer):
    return workflow_enforcer._workflow_checker


@pytest.fixture
def bot(monkeypatch, workflow_enforcer):
    monkeypatch.setenv("BOT_NAME", "Police")
    return workflow_enforcer
