import pytest

from automation_tools.tests.gitlab_constants import (
    DEFAULT_COMMIT,
    GOOD_README_COMMIT_NEW_FILE,
    FILE_COMMITS_SHA,
    DEFAULT_JIRA_ISSUE_KEY)
from automation_tools.tests.mocks.git_mocks import BOT_USERNAME
from robocat.award_emoji_manager import AwardEmojiManager
from robocat.bot import Bot, GitlabEventData, GitlabEventType
from robocat.commands.commands import BaseCommand, ServeCommand, RunPipelineCommand
import robocat.commands.parser
from tests.fixtures import *


class TestRobocatCommands:
    @pytest.mark.parametrize(("comment", "command_class"), [
        (f"@{BOT_USERNAME} process", ServeCommand),
        (f"@{BOT_USERNAME}   process", ServeCommand),
        (f"  @{BOT_USERNAME}   process", ServeCommand),
        (f"@{BOT_USERNAME}\n process", None),
        (f"sometext @{BOT_USERNAME} process", None),
        (f"@{BOT_USERNAME} serves", None),
        (f"{BOT_USERNAME} process", None),
        (f"@{BOT_USERNAME} run_pipeline", RunPipelineCommand)
    ])
    def test_command_parsing(self, comment: str, command_class: BaseCommand):
        command = robocat.commands.parser.create_command_from_text(
            username=BOT_USERNAME,
            text=comment)
        assert command == command_class or isinstance(command, command_class)

    @pytest.mark.parametrize(("mr_state", "jira_issues"), [
        ({"pipelines_list": [(f"{DEFAULT_COMMIT['sha']}0", "failed")]}, [])
    ])
    def test_run_pipeline(self, bot: Bot, mr: MergeRequestMock):
        event_data = GitlabEventData(
            mr_id=mr.iid,
            event_type=GitlabEventType.comment,
            added_comment=f"@{BOT_USERNAME} run_pipeline")
        bot.process_event(event_data)

        comments = mr.mock_comments()
        assert len(comments) == 2, f"Got comments: {comments}"
        assert f":{AwardEmojiManager.PIPELINE_EMOJI}:" in comments[-1], (
            f"Last comment: {comments[-1]}.")

        pipelines = mr.pipelines()
        assert len(pipelines) == 2, "No new pipeline created"
        assert pipelines[0]["status"] == "running", f"Got pipelines: {pipelines}"

    @pytest.mark.parametrize(("mr_state", "jira_issues"), [
        ({"pipelines_list": [(DEFAULT_COMMIT['sha'], "failed")]}, [])
    ])
    def test_refuse_run_pipeline(self, bot: Bot, mr: MergeRequestMock):
        event_data = GitlabEventData(
            mr_id=mr.iid,
            event_type=GitlabEventType.comment,
            added_comment=f"@{BOT_USERNAME} run_pipeline")
        bot.process_event(event_data)

        comments = mr.mock_comments()
        assert len(comments) == 2, f"Got comments: {comments}"
        assert f":{AwardEmojiManager.NO_PIPELINE_EMOJI}:" in comments[-1], (
            f"Last comment: {comments[-1]}.")

        pipelines = mr.pipelines()
        assert len(pipelines) == 1, "New pipeline created"
        assert pipelines[0]["status"] == "failed", f"Got pipelines: {pipelines}"

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"]}], {
            "title": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[0],
            "description": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[1],
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")],
            "squash": False
        })
    ])
    def test_serve(self, bot: Bot, mr: MergeRequestMock):
        event_data = GitlabEventData(
            mr_id=mr.iid,
            event_type=GitlabEventType.comment,
            added_comment=f"@{BOT_USERNAME} process")
        bot.process_event(event_data)
        assert mr.state == "merged"
