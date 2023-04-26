from pathlib import Path
import pytest

from automation_tools.tests.mocks.git_mocks import BOT_USERNAME
from robocat.merge_request import MergeRequest
import robocat.gitlab
from automation_tools.tests.mocks.project import ProjectMock
from automation_tools.tests.mocks.merge_request import MergeRequestMock
from automation_tools.tests.mocks.pipeline import PipelineMock
from automation_tools.tests.gitlab_constants import (
    DEFAULT_APPROVE_RULESET,
    DEFAULT_APIDOC_APPROVE_RULESET,
    DEFAULT_SUBMODULE_DIRS)
from automation_tools.tests.jira_constants import DEFAULT_PROJECT_KEYS_TO_CHECK
from robocat.app import Bot
from robocat.rule.commit_message_check_rule import CommitMessageCheckRule
from robocat.rule.essential_rule import EssentialRule
from robocat.rule.nx_submodule_check_rule import NxSubmoduleCheckRule
from robocat.rule.job_status_check_rule import JobStatusCheckRule
from robocat.rule.process_related_projects_issues import ProcessRelatedProjectIssuesRule
from robocat.rule.follow_up_rule import FollowUpRule
from robocat.rule.workflow_check_rule import WorkflowCheckRule
from robocat.merge_request_manager import MergeRequestManager
from robocat.project_manager import ProjectManager
from automation_tools.tests.fixtures import jira, repo_accessor
from automation_tools.utils import parse_config_file


@pytest.fixture
def mr_state():
    return {}


@pytest.fixture
def open_source_approve_ruleset():
    return DEFAULT_APPROVE_RULESET


@pytest.fixture
def apidoc_approve_ruleset():
    return DEFAULT_APIDOC_APPROVE_RULESET


@pytest.fixture
def project(mr_state, monkeypatch):
    project = ProjectMock()
    # create merge request mock object bonded to "project".
    mr = MergeRequestMock(project=project, **mr_state)

    def create_pipeline(_, *__, **___):
        new_pipeline_id = len(project.pipelines.list())
        pipeline = PipelineMock(
            project=project, id=new_pipeline_id, sha=mr.sha, status="manual")
        project.pipelines.add_mock_pipeline(pipeline)

    monkeypatch.setattr(robocat.gitlab.Gitlab, "create_detached_pipeline", create_pipeline)
    return project


@pytest.fixture
def mr(project):
    first_mr_id = list(project.mergerequests.list())[0].iid
    return project.mergerequests.get(first_mr_id)


@pytest.fixture
def bot_config():
    return parse_config_file(Path(__file__).parents[1].resolve() / "config.test.yaml")


@pytest.fixture
def mr_manager(project):
    first_mr_id = list(project.mergerequests.list())[0].iid
    mr = project.mergerequests.get(first_mr_id)
    return MergeRequestManager(MergeRequest(mr, BOT_USERNAME))


@pytest.fixture
def essential_rule():
    return EssentialRule(DEFAULT_PROJECT_KEYS_TO_CHECK)


@pytest.fixture
def nx_submodule_check_rule(project, repo_accessor):
    project_manager = ProjectManager(project, BOT_USERNAME, repo=repo_accessor)
    return NxSubmoduleCheckRule(project_manager, nx_submodule_dirs=DEFAULT_SUBMODULE_DIRS)


@pytest.fixture
def job_status_rule(project, repo_accessor, open_source_approve_ruleset, apidoc_approve_ruleset):
    project_manager = ProjectManager(project, BOT_USERNAME, repo=repo_accessor)
    return JobStatusCheckRule(
        project_manager,
        open_source_approve_ruleset=open_source_approve_ruleset,
        apidoc_changes_approve_ruleset=apidoc_approve_ruleset)


@pytest.fixture
def commit_message_rule():
    return CommitMessageCheckRule(
        approve_ruleset=DEFAULT_APPROVE_RULESET)


@pytest.fixture
def workflow_rule(project, jira):
    return WorkflowCheckRule(jira=jira)


@pytest.fixture
def follow_up_rule(project, jira, monkeypatch, repo_accessor):
    project_manager = ProjectManager(project, BOT_USERNAME, repo=repo_accessor)
    rule = FollowUpRule(project_manager=project_manager, jira=jira)

    def return_gitlab_object(*_, private_token):
        gitlab = project.manager.gitlab
        gitlab.set_private_token(private_token)
        return gitlab

    monkeypatch.setattr(robocat.gitlab.gitlab, "Gitlab", return_gitlab_object)
    monkeypatch.setenv("BOT_NAME", "Robocat")

    return rule


@pytest.fixture
def process_related_projects_issues_rule(jira, bot_config, monkeypatch):
    monkeypatch.setenv("BOT_NAME", "Robocat")
    return ProcessRelatedProjectIssuesRule(
        jira=jira, **bot_config["process_related_merge_requests_rule"])


@pytest.fixture
def bot(
        commit_message_rule,
        essential_rule,
        nx_submodule_check_rule,
        job_status_rule,
        follow_up_rule,
        workflow_rule,
        process_related_projects_issues_rule,
        repo_accessor,
        project,
        jira,
        monkeypatch):
    def bot_init(bot):
        bot._rule_commit_message = commit_message_rule
        bot._rule_essential = essential_rule
        bot._rule_nx_submodules_check = nx_submodule_check_rule
        bot._rule_job_status_check = job_status_rule
        bot._rule_follow_up = follow_up_rule
        bot._rule_workflow_check = workflow_rule
        bot._rule_process_related_projects_issues = process_related_projects_issues_rule
        bot._username = BOT_USERNAME
        bot._repo = repo_accessor
        bot._project_manager = ProjectManager(project, bot._username, repo=bot._repo)
        bot._jira = jira
        bot._polling = False

    monkeypatch.setattr(Bot, "__init__", bot_init)
    monkeypatch.setenv("BOT_NAME", "Robocat")

    return Bot()
