## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import pytest

from automation_tools.tests.mocks.git_mocks import CommitMock, BranchMock
from robocat.award_emoji_manager import AwardEmojiManager
from robocat.bot import GitlabEventData, GitlabJobEventData, GitlabEventType
from automation_tools.tests.gitlab_constants import (
    BAD_OPENSOURCE_COMMIT,
    DEFAULT_COMMIT,
    GOOD_README_COMMIT_NEW_FILE,
    FILE_COMMITS_SHA,
    OPEN_SOURCE_APPROVER_COMMON,
    DEFAULT_JIRA_ISSUE_KEY,
    USERS,
    BOT_EMAIL,
    BOT_NAME,
)
from tests.fixtures import *


class TestBot:
    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Return to development on the second handle iteration if essential rule is ok but
        # open source rule check is failed and merge request is not approved by an eligible user.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [BAD_OPENSOURCE_COMMIT],
            "pipelines_list": [(
                BAD_OPENSOURCE_COMMIT["sha"],
                "success",
                [("open-source:check", "failed"), ("new-open-source-files:check", "failed")],
            )],
        }),
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "pipelines_list": [(
                GOOD_README_COMMIT_NEW_FILE["sha"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "failed")],
            )],
        }),
    ])
    def test_no_merge_on_check_fail(self, bot, mr, mr_manager):
        bot.handle(mr_manager)
        assert not mr.state == "merged"

        bot.handle(mr_manager)
        assert not mr.state == "merged"
        assert not mr.work_in_progress

        mr_manager._mr.load_discussions()  # Update notes in the Merge Request object.

        # Nothing changes after the third handler run.
        comments_before = mr.mock_comments()
        pipelines_before = mr.pipelines()
        emojis_before = [e.name for e in mr.awardemojis.list()]

        bot.handle(mr_manager)
        assert not mr.state == "merged"
        assert not mr.work_in_progress
        assert mr.blocking_discussions_resolved

        comments_after = mr.mock_comments()
        pipelines_after = mr.pipelines()
        emojis_after = [e.name for e in mr.awardemojis.list()]
        assert comments_before == comments_after
        assert pipelines_before == pipelines_after
        assert emojis_before == emojis_after

    @pytest.mark.parametrize(("jira_issues", "mr_state", "expected_status"), [
        # One commit, no changes in open-source.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master"],
            "state": "In Review",
            "typ": "Task",
        }], {
            "title": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[0],
            "description": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[1],
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")],
            "squash": False
        }, "Waiting for QA"),
        # One commit, good changes in open-source.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"], "state": "In Review"}], {
            "title": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[0],
            "description": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[1],
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "pipelines_list": [(
                GOOD_README_COMMIT_NEW_FILE["sha"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "success")],
            )],
            "squash": False
        }, "Closed"),
        # One commit, "Closes <issue_key>" auto-added.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"], "state": "In Review"}], {
            "title": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[0],
            "description": (
                GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[1] +
                f"\nCloses {DEFAULT_JIRA_ISSUE_KEY}"),
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: some title\nsome msg",
                "diffs": [],
                "files": {},
            }],
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")],
            "squash": False
        }, "Closed"),
        # Two commits, no squashing.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"], "state": "In Review"}], {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: msg",
                "files": {},
            }, GOOD_README_COMMIT_NEW_FILE],
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")],
            "squash": False,
        }, "Closed"),
    ])
    def test_merge_no_local_squash(
            self, bot, mr, mr_manager, repo_accessor, jira, jira_issues, expected_status):
        repo_accessor.repo.mock_reset_commands_log()

        bot.handle(mr_manager)
        assert mr.state == "merged"
        assert not mr.mock_rebased

        local_git_actions = repo_accessor.repo.mock_read_commands_log()
        assert not local_git_actions, f"Local git actions: {local_git_actions}"

        emojis = mr.awardemojis.list()
        assert not any(
            e for e in emojis if e.name == AwardEmojiManager.UNFINISHED_POST_MERGING_EMOJI), (
            "Hasn't unfinished processing flag.")

        issue = jira._jira.issue(jira_issues[0]["key"])
        assert issue.fields.status.name == expected_status
        assert len(issue.fields.comment.comments) == 2

        assert "has been merged to branch\n*nx:master*" in issue.fields.comment.comments[0].body

        if expected_status in ["Closed", "DONE"]:
            expected_transition = "closed"
        else:
            expected_transition = "moved to QA"
        assert issue.fields.comment.comments[1].body.startswith(f"Issue {expected_transition}")

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Two commits, squashing is required.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"], "state": "In progress"}], {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": "msg",
                "files": {},
            }, GOOD_README_COMMIT_NEW_FILE],
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")],
            "mock_base_commit_sha": "0123457789AB",
        }),
    ])
    def test_merge_with_local_squash(self, bot, mr, mr_manager, project, repo_accessor):
        repo_accessor.repo.mock_reset_commands_log()
        base_commit_mock = CommitMock(
            repo_accessor.repo, sha="0123457789AB", message="base commit")
        remote_branch_name = f"{project.namespace['full_path']}/{mr.source_branch}"
        repo_accessor.repo.branches[remote_branch_name] = BranchMock(
            repo_accessor.repo, name=mr.source_branch, commits=[base_commit_mock])

        bot.handle(mr_manager)
        assert mr.state == "merged"
        assert not mr.mock_rebased

        local_git_actions = repo_accessor.repo.mock_read_commands_log()
        assert len(local_git_actions) == 7, f"Local git actions: {local_git_actions}"
        assert local_git_actions[0].startswith(f"add remote '{project.namespace['full_path']}'"), (
            f"Local git action 1: {local_git_actions[0]}")
        assert local_git_actions[2].startswith(f"fetch '{project.namespace['full_path']}'"), (
            f"Local git actions: {local_git_actions[2]}")
        hard_reset_test_string = (
            f"hard reset '{mr.source_branch}' to "
            f"'{project.namespace['full_path']}/{mr.source_branch}'")
        assert local_git_actions[3].startswith(hard_reset_test_string), (
            f"Local git actions: {local_git_actions[3]}")
        soft_reset_test_string = (
            f"soft reset '{mr.source_branch}' to '{mr.mock_base_commit_sha}'")
        assert local_git_actions[4].startswith(soft_reset_test_string), (
            f"Local git actions: {local_git_actions[4]}")
        commit_author_test_string = (
            f"author: '{USERS[0]['name']} <{USERS[0]['email']}>'")
        commit_committer_test_string = (
            f"committer: '{BOT_NAME} <{BOT_EMAIL}>'")
        assert commit_author_test_string in local_git_actions[5], (
            f"Wrong commit author: {local_git_actions[5]}")
        assert commit_committer_test_string in local_git_actions[5], (
            f"Wrong commit committer: {local_git_actions[5]}")
        assert local_git_actions[5].startswith(f"commit to branch '{mr.source_branch}'"), (
            f"Local git actions: {local_git_actions[5]}")
        push_test_string = (
            f"forced push '{mr.source_branch}' to '{project.namespace['full_path']}'")
        assert local_git_actions[6].startswith(push_test_string), (
            f"Local git actions: {local_git_actions[6]}")

        emojis = mr.awardemojis.list()
        assert not any(
            e for e in emojis if e.name == AwardEmojiManager.UNFINISHED_POST_MERGING_EMOJI), (
            "The Unfinished Processing flag should not be set.")

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"], "state": "In progress"}], {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")],
            "detailed_merge_status": "need_rebase",
        }),
    ])
    def test_rebase(self, bot, mr, mr_manager):
        bot.handle(mr_manager)
        assert not mr.state == "merged"
        assert mr.mock_rebased

        emojis = mr.awardemojis.list()
        assert not any(
            e for e in emojis if e.name == AwardEmojiManager.UNFINISHED_POST_MERGING_EMOJI), (
            'Hasn\'t unfinished processing flag.')

    @pytest.mark.parametrize(("jira_issues", "mr_state", "should_trigger_processing"), [
        # "Check" stage is finished
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"]}], {
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "pipelines_list": [(
                FILE_COMMITS_SHA["good_dontreadme"],
                "success",
                [
                    ("open-source:check", "success", "check"),
                    ("new-open-source-files:check", "failed", "check"),
                    ("windows-x64:build", "success", "build"),
                    ("unit:test", "success", "test"),
                ])],
        }, True),
        # "Check" stage is finished, but the job triggered the event is from another stage.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"]}], {
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "pipelines_list": [(
                FILE_COMMITS_SHA["good_dontreadme"],
                "success",
                [
                    ("open-source:check", "success", "PRE"),
                    ("new-open-source-files:check", "failed", "check"),
                    ("windows-x64:build", "success", "build"),
                    ("unit:test", "success", "test"),
                ])],
        }, False),
        # The job, triggered the event is finished, but some other job from the "check" stage is
        # not.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"]}], {
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "pipelines_list": [(
                FILE_COMMITS_SHA["good_dontreadme"],
                "success",
                [
                    ("open-source:check", "success", "check"),
                    ("new-open-source-files:check", "running", "check"),
                    ("windows-x64:build", "success", "build"),
                    ("unit:test", "success", "test"),
                ])],
        }, False),
        # The job, triggered the event is not finished, although other jobs from the "check" stage
        # are.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"]}], {
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "pipelines_list": [(
                FILE_COMMITS_SHA["good_dontreadme"],
                "success",
                [
                    ("open-source:check", "success", "running"),
                    ("new-open-source-files:check", "success", "check"),
                    ("windows-x64:build", "success", "build"),
                    ("unit:test", "success", "test"),
                ])],
        }, False),
    ])
    def test_process_job_event(self, bot, mr, mr_manager, should_trigger_processing):
        first_job = mr.project.pipelines.list()[0].jobs.list()[1]
        payload = GitlabJobEventData(
            job_id=first_job.id,
            pipeline_id=first_job.pipeline_ref.id,
            project_id=first_job.project_id,
            name=first_job.name,
            status=first_job.status,
            stage=first_job.stage,
            allow_failure=True)
        event_data = GitlabEventData(payload=payload, event_type=GitlabEventType.job)
        bot.process_event(event_data)

        emojis = mr.awardemojis.list()
        has_emoji_set_by_bot = any(e for e in emojis if e.name == AwardEmojiManager.WATCH_EMOJI)
        assert should_trigger_processing == has_emoji_set_by_bot, (
            'MR was not processed.')

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"]}], {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "manual")],
            "detailed_merge_status": "ci_must_pass",
        }),
    ])
    def test_run_latest_pipeline_before_merge(self, bot, mr, mr_manager):
        bot.handle(mr_manager)

        assert mr.project.pipelines.pipelines[0].status == "running"
        assert not mr.state == "merged"

        emojis = mr.awardemojis.list()
        assert not any(
            e for e in emojis if e.name == AwardEmojiManager.UNFINISHED_POST_MERGING_EMOJI), (
            "The Unfinished Processing flag should not be set.")
