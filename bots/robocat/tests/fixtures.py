import sys
from pathlib import Path
import pytest

from robocat.merge_request_manager import MergeRequestManager
from robocat.merge_request import MergeRequest
from robocat.rule.essential_rule import EssentialRule
from robocat.rule.open_source_check_rule import OpenSourceCheckRule
from tests.mocks.project import ProjectMock
from tests.mocks.merge_request import MergeRequestMock
from tests.mocks.pipeline import PipelineMock
from tests.common_constants import BOT_USERNAME, DEFAULT_MR_ID, DEFAULT_OPEN_SOURCE_APPROVER

# Patch sys.path to include common libraries that are used by Bot.
sys.path.append(str((Path(__file__).parent / '../../../').resolve()))
from robocat.app import Bot  # noqa


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
        project.pipelines.mock_add_pipeline(pipeline)

    monkeypatch.setattr(MergeRequest, "create_pipeline", create_pipeline)

    return project


@pytest.fixture
def essential_rule(project):
    return EssentialRule(project)


@pytest.fixture
def open_source_rule(project):
    return OpenSourceCheckRule(project, approver_username=DEFAULT_OPEN_SOURCE_APPROVER)


@pytest.fixture
def mr(project):
    return project.mergerequests.get(DEFAULT_MR_ID)


@pytest.fixture
def mr_manager(project):
    mr = project.mergerequests.get(DEFAULT_MR_ID)
    return MergeRequestManager(MergeRequest(mr, BOT_USERNAME))


@pytest.fixture
def bot(essential_rule, open_source_rule, monkeypatch):
    def bot_init(bot):
        bot._rule_essential = essential_rule
        bot._rule_open_source_check = open_source_rule

    monkeypatch.setattr(Bot, "__init__", bot_init)
    return Bot()
