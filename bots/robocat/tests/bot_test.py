import pytest

from automation_tools.tests.mocks.git_mocks import CommitMock, BranchMock, BOT_EMAIL, BOT_NAME
from robocat.award_emoji_manager import AwardEmojiManager
from automation_tools.tests.gitlab_constants import (
    BAD_OPENSOURCE_COMMIT,
    DEFAULT_COMMIT,
    GOOD_README_COMMIT_NEW_FILE,
    FILE_COMMITS_SHA,
    OPEN_SOURCE_APPROVER_COMMON,
    DEFAULT_JIRA_ISSUE_KEY,
    USERS)
from tests.fixtures import *


class TestBot:
    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Return to development on the second handle iteration if essential rule is ok but
        # open source rule check is failed and merge request is not approved by an eligible user.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.1"]}], {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [BAD_OPENSOURCE_COMMIT],
            "pipelines_list": [(BAD_OPENSOURCE_COMMIT["sha"], "success")]
        }),
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.1"]}], {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")]
        }),
    ])
    def test_autoreturn_to_develop(self, bot, mr, mr_manager):
        bot.handle(mr_manager)
        assert not mr.state == "merged"
        assert not mr.blocking_discussions_resolved

        bot.handle(mr_manager)
        assert not mr.state == "merged"
        assert mr.work_in_progress

        # Nothing changes after the third handler run.
        comments_before = mr.mock_comments()
        pipelines_before = mr.pipelines()
        emojis_before = [e.name for e in mr.awardemojis.list()]

        bot.handle(mr_manager)
        assert not mr.state == "merged"
        assert mr.work_in_progress

        comments_after = mr.mock_comments()
        pipelines_after = mr.pipelines()
        emojis_after = [e.name for e in mr.awardemojis.list()]
        assert comments_before == comments_after
        assert pipelines_before == pipelines_after
        assert emojis_before == emojis_after

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # One commit.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"]}], {
            "title": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[0],
            "description": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[1],
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")],
            "squash": False
        }),
        # One commit, "Closes <issue_key>" auto-added.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"]}], {
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
        }),
        # Two commits, no squashing.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"]}], {
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
        }),
    ])
    def test_merge_no_local_squash(self, bot, mr, mr_manager, repo_accessor):
        repo_accessor.repo.mock_reset_commands_log()

        bot.handle(mr_manager)
        assert mr.state == "merged"
        assert not mr.mock_rebased

        local_git_actions = repo_accessor.repo.mock_read_commands_log()
        assert not local_git_actions, f"Local git actions: {local_git_actions}"

        emojis = mr.awardemojis.list()
        assert not any(
            e for e in emojis if e.name == AwardEmojiManager.UNFINISHED_PROCESSING_EMOJI), (
            'Hasn\'t unfinished processing flag.')

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Two commits, squashing is required.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"]}], {
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
            e for e in emojis if e.name == AwardEmojiManager.UNFINISHED_PROCESSING_EMOJI), (
            'Hasn\'t unfinished processing flag.')

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"]}], {
            "mock_needs_rebase": True,
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")]
        }),
    ])
    def test_rebase(self, bot, mr, mr_manager):
        bot.handle(mr_manager)
        assert not mr.state == "merged"
        assert mr.mock_rebased

        emojis = mr.awardemojis.list()
        assert not any(
            e for e in emojis if e.name == AwardEmojiManager.UNFINISHED_PROCESSING_EMOJI), (
            'Hasn\'t unfinished processing flag.')
