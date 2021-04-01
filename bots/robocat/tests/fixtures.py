from pathlib import Path
import pytest

from robocat.merge_request import MergeRequest
import robocat.gitlab
from tests.mocks.project import ProjectMock
from tests.mocks.merge_request import MergeRequestMock
from tests.mocks.pipeline import PipelineMock
import tests.mocks.git_mocks
from tests.common_constants import BOT_USERNAME, DEFAULT_OPEN_SOURCE_APPROVER

from robocat.app import Bot
from robocat.rule.essential_rule import EssentialRule
from robocat.rule.open_source_check_rule import OpenSourceCheckRule
from robocat.rule.followup_rule import FollowupRule
from robocat.rule.jira_issue_check_rule import JiraIssueCheckRule
from robocat.merge_request_manager import MergeRequestManager
from robocat.project_manager import ProjectManager
from automation_tools.jira import JiraAccessor
import automation_tools.git
from automation_tools.tests.mocks.jira import Jira as JiraMock


@pytest.fixture
def mr_state():
    return {}


@pytest.fixture
def repo_accessor(monkeypatch):
    monkeypatch.setattr(automation_tools.git.git, "Repo", tests.mocks.git_mocks.RepoMock)
    monkeypatch.setattr(
        automation_tools.git.git.remote, "Remote", tests.mocks.git_mocks.RemoteMock)
    return automation_tools.git.Repo(Path("foo_path"), "foo_url")


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
def jira(jira_issues, monkeypatch):
    def init_with_mock(this):
        this._jira = JiraMock()

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
def open_source_rule(project, repo_accessor):
    project_manager = ProjectManager(project, BOT_USERNAME, repo=repo_accessor)
    return OpenSourceCheckRule(project_manager, approver_username=DEFAULT_OPEN_SOURCE_APPROVER)


@pytest.fixture
def jira_issue_rule(project, jira):
    return JiraIssueCheckRule(jira=jira)


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
def bot(essential_rule, open_source_rule, followup_rule, jira_issue_rule, repo_accessor,
        monkeypatch):
    def bot_init(bot):
        bot._rule_essential = essential_rule
        bot._rule_open_source_check = open_source_rule
        bot._rule_followup = followup_rule
        bot._rule_jira_issue_check = jira_issue_rule
        bot._repo = repo_accessor

    monkeypatch.setattr(Bot, "__init__", bot_init)
    monkeypatch.setenv("BOT_NAME", "Robocat")

    return Bot()
