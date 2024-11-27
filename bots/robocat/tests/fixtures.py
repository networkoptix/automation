## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from pathlib import Path
import pytest
import queue

from automation_tools.tests.fixtures import jira, repo_accessor
from automation_tools.tests.gitlab_constants import (
    DEFAULT_APPROVE_RULESET,
    DEFAULT_APIDOC_APPROVE_RULESET,
    DEFAULT_CODEOWNER_APPROVE_RULESET,
    BOT_USERNAME)
from automation_tools.tests.mocks.project import ProjectMock
from automation_tools.tests.mocks.merge_request import MergeRequestMock
from automation_tools.tests.mocks.pipeline import PipelineMock
from automation_tools.utils import parse_config_file
from robocat.app import Bot
from robocat.config import Config, ApproveRulesetConfig
from robocat.merge_request import MergeRequest
from robocat.merge_request_manager import MergeRequestManager
from robocat.project_manager import ProjectManager
from robocat.rule.commit_message_check_rule import CommitMessageCheckRule
from robocat.rule.essential_rule import EssentialRule
from robocat.rule.follow_up_rule import FollowUpRule
from robocat.rule.job_status_check_rule import JobStatusCheckRule
from robocat.rule.nx_submodule_check_rule import NxSubmoduleCheckRule
from robocat.rule.post_processing_rule import PostProcessingRule
from robocat.rule.process_related_projects_issues import ProcessRelatedProjectIssuesRule
from robocat.rule.workflow_check_rule import WorkflowCheckRule
import automation_tools.checkers.config
import automation_tools.checkers.config
import robocat.gitlab


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
def code_owner_approve_ruleset():
    return DEFAULT_CODEOWNER_APPROVE_RULESET


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
    return Config(
        **parse_config_file(
            Path(__file__).parents[4].resolve() / "bots/robocat/config_template.yaml"))


@pytest.fixture
def mr_manager(project):
    first_mr_id = list(project.mergerequests.list())[0].iid
    mr = project.mergerequests.get(first_mr_id)
    return MergeRequestManager(MergeRequest(mr, BOT_USERNAME))


@pytest.fixture
def project_manager(project, repo_accessor):
    return ProjectManager(project, BOT_USERNAME, repo=repo_accessor)


@pytest.fixture
def essential_rule(bot_config, project_manager):
    return EssentialRule(bot_config, project_manager, None)


@pytest.fixture
def nx_submodule_check_rule(bot_config, project_manager):
    return NxSubmoduleCheckRule(bot_config, project_manager, None)


@pytest.fixture
def job_status_rule(
    bot_config: Config,
    project_manager,
    open_source_approve_ruleset,
    apidoc_approve_ruleset,
    code_owner_approve_ruleset
):
    rule = bot_config.job_status_check_rule
    rule.open_source.approve_ruleset = ApproveRulesetConfig(**open_source_approve_ruleset)
    rule.apidoc.approve_ruleset = ApproveRulesetConfig(**apidoc_approve_ruleset)
    rule.code_owner_approval.approve_ruleset = ApproveRulesetConfig(**code_owner_approve_ruleset)
    return JobStatusCheckRule(bot_config, project_manager, None)


@pytest.fixture
def commit_message_rule(bot_config: Config, project_manager):
    config = ApproveRulesetConfig(**DEFAULT_APPROVE_RULESET)
    bot_config.job_status_check_rule.open_source.approve_ruleset = config
    return CommitMessageCheckRule(bot_config, project_manager, None)


@pytest.fixture
def workflow_rule(bot_config, project, project_manager, jira, monkeypatch):
    monkeypatch.setattr(
        automation_tools.checkers.config,
        "ALLOWED_VERSIONS_SETS",
        {
            "VMS": [
                set(['5.0', '5.0_patch', '5.1', '5.1_patch', 'master']),
                set(['5.0_patch', '5.1', '5.1_patch', 'master']),
                set(['5.1', '5.1_patch', 'master']),
                set(['5.1_patch', 'master']),
                set(['master']),
                set(['Future']),
            ],
            "MOBILE": [
                set(['23.1', '22.5', 'master']),
                set(['23.1', 'master']),
                set(['master']),
                set(['Future']),
            ],
        })
    return WorkflowCheckRule(bot_config, project_manager, jira)


@pytest.fixture
def follow_up_rule(bot_config, project, project_manager, jira, monkeypatch):
    rule = FollowUpRule(bot_config, project_manager, jira)

    def return_gitlab_object(*_, private_token):
        gitlab = project.manager.gitlab
        gitlab.set_private_token(private_token)
        return gitlab

    monkeypatch.setattr(robocat.gitlab.gitlab, "Gitlab", return_gitlab_object)
    monkeypatch.setenv("BOT_NAME", "Robocat")

    return rule


@pytest.fixture
def process_related_projects_issues_rule(bot_config, project_manager, jira, monkeypatch):
    monkeypatch.setenv("BOT_NAME", "Robocat")
    return ProcessRelatedProjectIssuesRule(bot_config, project_manager, jira)


@pytest.fixture
def post_processing_rule(bot_config, project_manager, jira, monkeypatch):
    monkeypatch.setenv("BOT_NAME", "Robocat")
    return PostProcessingRule(bot_config, project_manager, jira)


@pytest.fixture
def bot(
        commit_message_rule,
        essential_rule,
        nx_submodule_check_rule,
        job_status_rule,
        follow_up_rule,
        workflow_rule,
        process_related_projects_issues_rule,
        post_processing_rule,
        repo_accessor,
        project,
        jira,
        bot_config,
        monkeypatch):
    def bot_init(bot):
        bot._rules = {
            "commit_message": commit_message_rule,
            "essential": essential_rule,
            "nx_submodule": nx_submodule_check_rule,
            "job_status": job_status_rule,
            "follow_up": follow_up_rule,
            "workflow": workflow_rule,
            "process_related": process_related_projects_issues_rule,
            "post_processing": post_processing_rule,
        }
        bot._username = BOT_USERNAME
        bot._repo = repo_accessor
        bot._project_manager = ProjectManager(project, bot._username, repo=bot._repo)
        bot._jira = jira
        bot._polling = False
        bot._mr_queue = queue.PriorityQueue()
        bot.config = bot_config

    monkeypatch.setattr(Bot, "__init__", bot_init)
    monkeypatch.setenv("BOT_NAME", "Robocat")

    return Bot()
