## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import pytest

from automation_tools.git import Repo
from automation_tools.tests.gitlab_constants import (
    DEFAULT_COMMIT,
    GOOD_README_COMMIT_NEW_FILE,
    FILE_COMMITS_SHA,
    DEFAULT_JIRA_ISSUE_KEY,
    FORK_PROJECT_ID,
    MERGED_TO_MASTER_MERGE_REQUESTS,
    BOT_USERNAME)
from robocat.award_emoji_manager import AwardEmojiManager
from robocat.bot import (
    Bot,
    GitlabEventData,
    GitlabCommentEventData,
    GitlabEventType)
from robocat.commands.commands import (
    BaseCommand,
    ProcessCommand,
    RunPipelineCommand,
    FollowUpCommand,
    UnknownCommand)
import robocat.commands.parser
from robocat.note import MessageId
from tests.fixtures import *


class TestRobocatCommands:
    @pytest.mark.parametrize(("comment", "command_class"), [
        (f"@{BOT_USERNAME} process", ProcessCommand),
        (f"@{BOT_USERNAME}   process", ProcessCommand),
        (f"  @{BOT_USERNAME}   process", ProcessCommand),
        (f"@{BOT_USERNAME}\n process", None),
        (f"sometext @{BOT_USERNAME} process", None),
        (f"@{BOT_USERNAME} serves", UnknownCommand),
        (f"{BOT_USERNAME} process", None),
        (f"@{BOT_USERNAME} run_pipeline", RunPipelineCommand),
        (f"@{BOT_USERNAME} run-pipeline", RunPipelineCommand),
        (f"@{BOT_USERNAME} follow-up", FollowUpCommand),
        (f"@{BOT_USERNAME} follow_up", FollowUpCommand),
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
        payload = GitlabCommentEventData(
            mr_id=mr.iid, added_comment=f"@{BOT_USERNAME} run_pipeline")
        event_data = GitlabEventData(payload=payload, event_type=GitlabEventType.comment)
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
        payload = GitlabCommentEventData(
            mr_id=mr.iid, added_comment=f"@{BOT_USERNAME} run_pipeline")
        event_data = GitlabEventData(payload=payload, event_type=GitlabEventType.comment)
        bot.process_event(event_data)

        comments = mr.mock_comments()
        assert len(comments) == 2, f"Got comments: {comments}"
        assert f":{AwardEmojiManager.NO_PIPELINE_EMOJI}:" in comments[-1], (
            f"Last comment: {comments[-1]}.")

        pipelines = mr.pipelines()
        assert len(pipelines) == 1, "New pipeline created"
        assert pipelines[0]["status"] == "failed", f"Got pipelines: {pipelines}"

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"], "state": "In progress"}], {
            "title": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[0],
            "description": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[1],
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")],
            "squash": False
        })
    ])
    def test_process_unmerged(self, bot: Bot, mr: MergeRequestMock):
        payload = GitlabCommentEventData(
            mr_id=mr.iid, added_comment=f"@{BOT_USERNAME} follow-up")
        event_data = GitlabEventData(payload=payload, event_type=GitlabEventType.comment)
        bot.process_event(event_data)
        comments = mr.mock_comments()
        assert f":{AwardEmojiManager.COMMAND_NOT_EXECUTED}:" in comments[-1], (
            f"Last comment: {comments}.")

        payload = GitlabCommentEventData(
            mr_id=mr.iid, added_comment=f"@{BOT_USERNAME} process")
        event_data = GitlabEventData(payload=payload, event_type=GitlabEventType.comment)
        bot.process_event(event_data)
        assert mr.state == "merged"

    @pytest.mark.parametrize(("jira_issues", "mr_state", "command"), [
        (
            [{
                "key": DEFAULT_JIRA_ISSUE_KEY,
                "branches": ["master", "vms_5.1"],
                "merge_requests": [
                    MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"],
                ],
                "state": "In Review",
            }],
            {
                "title": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[0],
                "description": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[1],
                "blocking_discussions_resolved": True,
                "needed_approvers_number": 0,
                "commits_list": [GOOD_README_COMMIT_NEW_FILE],
                "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")],
                "source_project_id": FORK_PROJECT_ID,
                "state": "merged",
            },
            "process",
        ), (
            [{
                "key": DEFAULT_JIRA_ISSUE_KEY,
                "branches": ["master", "vms_5.1"],
                "merge_requests": [
                    MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"],
                ],
                "state": "In Review",
            }],
            {
                "title": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[0],
                "description": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[1],
                "blocking_discussions_resolved": True,
                "needed_approvers_number": 0,
                "commits_list": [GOOD_README_COMMIT_NEW_FILE],
                "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")],
                "source_project_id": FORK_PROJECT_ID,
                "state": "merged",
            },
            "follow-up",
        )
    ])
    def test_execute_commands_on_merged(
            self,
            project: ProjectMock,
            repo_accessor: Repo,
            bot: Bot,
            mr: MergeRequestMock,
            command: str):
        # Init git repo state. TODO: Move git repo state to parameters.
        source_project = ProjectMock(id=mr.source_project_id, manager=project.manager)
        for c in mr.commits_list:
            source_project.add_mock_commit("master", c["sha"], c["message"])
        project_remote = project.namespace["full_path"]
        repo_accessor.create_branch(
            target_remote=project_remote, new_branch="vms_5.1", source_branch="master")
        for c in mr.commits_list:
            repo_accessor.repo.add_mock_commit(c["sha"], c["message"])
        repo_accessor.repo.remotes[project_remote].mock_attach_gitlab_project(project)
        repo_accessor.repo.mock_add_gitlab_project(source_project)

        payload = GitlabCommentEventData(
            mr_id=mr.iid, added_comment=f"@{BOT_USERNAME} {command}")
        event_data = GitlabEventData(payload=payload, event_type=GitlabEventType.comment)

        bot.process_event(event_data)

        comments = mr.mock_comments()
        assert len(comments) == 2, f"Got comments: {comments}"
        assert f":{AwardEmojiManager.NOTIFICATION_EMOJI}:" in comments[0], (
            f"First comment: {comments[0]}.")

    @pytest.mark.parametrize(("mr_state", "jira_issues"), [({}, [])])
    def test_set_draft_follow_up_mode(
            self,
            bot: Bot,
            mr: MergeRequestMock,
            mr_manager: MergeRequestManager):
        payload = GitlabCommentEventData(
            mr_id=mr.iid, added_comment=f"@{BOT_USERNAME} draft-follow-up")
        event_data = GitlabEventData(payload=payload, event_type=GitlabEventType.comment)
        bot.process_event(event_data)

        mr_manager._mr.load_discussions()
        notes = mr_manager.notes()
        assert notes[0].message_id == MessageId.CommandSetDraftFollowUpMode, (
            f"Draft follow-up mode marker is not found in notes: {[n.message_id for n in notes]}")
