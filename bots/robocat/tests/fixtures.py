import pytest

from automation_tools.tests.mocks.git_mocks import BOT_NAME, BOT_USERNAME
from robocat.merge_request import MergeRequest
import robocat.gitlab
from tests.mocks.project import ProjectMock
from tests.mocks.merge_request import MergeRequestMock
from tests.mocks.pipeline import PipelineMock
from tests.robocat_constants import DEFAILT_APPROVE_RULES_LIST

from robocat.app import Bot
from robocat.rule.essential_rule import EssentialRule
from robocat.rule.open_source_check_rule import OpenSourceCheckRule
from robocat.rule.followup_rule import FollowupRule
from robocat.rule.workflow_check_rule import WorkflowCheckRule
from robocat.merge_request_manager import MergeRequestManager
from robocat.project_manager import ProjectManager
from automation_tools.tests.fixtures import jira, repo_accessor


@pytest.fixture
def mr_state():
    return {}


@pytest.fixture
def project(mr_state, monkeypatch):
    project = ProjectMock()
    # create merge request mock object bonded to "project".
    mr = MergeRequestMock(project=project, **mr_state)

    def create_pipeline(_, project_id, mr_id):
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
def mr_manager(project):
    first_mr_id = list(project.mergerequests.list())[0].iid
    mr = project.mergerequests.get(first_mr_id)
    return MergeRequestManager(MergeRequest(mr, BOT_USERNAME))


@pytest.fixture
def essential_rule(monkeypatch):
    return EssentialRule()


@pytest.fixture
def open_source_rule(project, repo_accessor):
    project_manager = ProjectManager(project, BOT_USERNAME, repo=repo_accessor)
    return OpenSourceCheckRule(project_manager, approve_rules=DEFAILT_APPROVE_RULES_LIST)


@pytest.fixture
def workflow_rule(project, jira):
    return WorkflowCheckRule(jira=jira)


@pytest.fixture
def followup_rule(project, jira, monkeypatch, repo_accessor):
    project_manager = ProjectManager(project, BOT_USERNAME, repo=repo_accessor)
    rule = FollowupRule(project_manager=project_manager, jira=jira)

    def return_gitlab_object(*_, private_token):
        gitlab = project.manager.gitlab
        gitlab.set_private_token(private_token)
        return gitlab

    monkeypatch.setattr(robocat.gitlab.gitlab, "Gitlab", return_gitlab_object)
    monkeypatch.setenv("BOT_NAME", "Robocat")

    return rule


@pytest.fixture
def bot(essential_rule, open_source_rule, followup_rule, workflow_rule, repo_accessor,
        monkeypatch):
    def bot_init(bot):
        bot._rule_essential = essential_rule
        bot._rule_open_source_check = open_source_rule
        bot._rule_followup = followup_rule
        bot._rule_workflow_check = workflow_rule
        bot._repo = repo_accessor

    monkeypatch.setattr(Bot, "__init__", bot_init)
    monkeypatch.setenv("BOT_NAME", "Robocat")

    return Bot()
