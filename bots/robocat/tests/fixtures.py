import sys
from pathlib import Path
import pytest

from robocat.merge_request_manager import MergeRequestManager
from robocat.project_manager import ProjectManager
from robocat.merge_request import MergeRequest
from robocat.rule.essential_rule import EssentialRule
from robocat.rule.open_source_check_rule import OpenSourceCheckRule
import robocat.project as gitlab_project_module
from tests.mocks.project import ProjectMock
from tests.mocks.merge_request import MergeRequestMock
from tests.mocks.pipeline import PipelineMock
from tests.common_constants import BOT_USERNAME, DEFAULT_MR_ID, DEFAULT_OPEN_SOURCE_APPROVER

# Patch sys.path to include common libraries.
sys.path.append(str((Path(__file__).parent / '../../../').resolve()))
from robocat.app import Bot  # noqa
from robocat.rule.followup_rule import FollowupRule  # noqa
from automation_tools.jira import JiraAccessor  # noqa
from automation_tools.tests.mocks.jira import Jira as JiraMock  # noqa


@pytest.fixture
def mr_state():
    return {}


@pytest.fixture
def project(mr_state, monkeypatch):
    project = ProjectMock()
    # create merge request mock object bonded to "project".
    mr = MergeRequestMock(project=project, **mr_state)

    def create_pipeline(_):
        new_pipeline_id = len(project.pipelines.list())
        pipeline = PipelineMock(
            project=project, id=new_pipeline_id, sha=mr.sha, status="manual")
        project.pipelines.add_mock_pipeline(pipeline)

    monkeypatch.setattr(MergeRequest, "create_pipeline", create_pipeline)

    return project


@pytest.fixture
def mr(project):
    return project.mergerequests.get(DEFAULT_MR_ID)


@pytest.fixture
def mr_manager(project):
    mr = project.mergerequests.get(DEFAULT_MR_ID)
    return MergeRequestManager(MergeRequest(mr, BOT_USERNAME))


@pytest.fixture
def jira(jira_issues, monkeypatch):
    def init_with_mock(this):
        this._jira = JiraMock()
        this._dry_run = False

    monkeypatch.setattr(JiraAccessor, "__init__", init_with_mock)

    accessor = JiraAccessor()
    if jira_issues:
        for issue_data in jira_issues:
            accessor._jira.add_mock_issue(**issue_data)

    return accessor


@pytest.fixture
def essential_rule(monkeypatch):
    return EssentialRule()


@pytest.fixture
def open_source_rule(project):
    project_manager = ProjectManager(project, BOT_USERNAME)
    return OpenSourceCheckRule(project_manager, approver_username=DEFAULT_OPEN_SOURCE_APPROVER)


@pytest.fixture
def followup_rule(project, jira, monkeypatch):
    project_manager = ProjectManager(project, BOT_USERNAME)
    rule = FollowupRule(project_manager=project_manager, jira=jira)

    def return_gitlab_object(*_, private_token):
        gitlab = project.manager.gitlab
        gitlab.set_private_token(private_token)
        return gitlab

    monkeypatch.setattr(gitlab_project_module, "Gitlab", return_gitlab_object)

    return rule


@pytest.fixture
def bot(essential_rule, open_source_rule, followup_rule, monkeypatch):
    def bot_init(bot):
        bot._rule_essential = essential_rule
        bot._rule_open_source_check = open_source_rule
        bot._rule_followup = followup_rule

    monkeypatch.setattr(Bot, "__init__", bot_init)
    return Bot()
