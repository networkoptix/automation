## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import queue
import time
from pathlib import Path
from unittest.mock import MagicMock, call

import gitlab
import pytest

from automation_tools.tests.mocks.git_mocks import CommitMock, BranchMock
from automation_tools.utils import parse_config_file
from robocat.award_emoji_manager import AwardEmojiManager
from robocat.bot import Bot, GitlabEventData, GitlabJobEventData, GitlabEventType
from robocat.config import Config
from robocat.project import Project
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
from automation_tools.tests.fixtures import repo_versions

_CONFIG_TEMPLATE = (
    Path(__file__).parents[4].resolve() / "bots/robocat/config_template.yaml")


class TestBotInit:
    @pytest.fixture
    def global_config(self):
        return parse_config_file(_CONFIG_TEMPLATE)

    @pytest.fixture
    def mock_gl(self):
        gl = MagicMock()
        gl.user.id = 1
        mock_user = MagicMock()
        mock_user.username = "bot"
        mock_user.email = "bot@test.com"
        mock_user.name = "Bot"
        gl.users.get.return_value = mock_user
        return gl

    def test_robocat_json_404_uses_global_config(
            self, monkeypatch, global_config, mock_gl):
        monkeypatch.setattr(
            Project, "get_file_content",
            lambda *_, **__: (_ for _ in ()).throw(
                gitlab.GitlabGetError(response_code=404)))
        sleep_mock = MagicMock()
        monkeypatch.setattr(time, "sleep", sleep_mock)

        bot = Bot(global_config, 1, queue.PriorityQueue(),
                  raw_gitlab=mock_gl, config_check_only=True)

        assert bot.config == Config(**global_config)
        sleep_mock.assert_not_called()

    def test_robocat_json_500_retries_then_falls_back_to_git(
            self, monkeypatch, global_config, mock_gl, tmp_path):
        monkeypatch.setattr(
            Project, "get_file_content",
            lambda *_, **__: (_ for _ in ()).throw(
                gitlab.GitlabGetError(response_code=500)))
        sleep_mock = MagicMock()
        monkeypatch.setattr(time, "sleep", sleep_mock)

        # Set up a local git repo with robocat.json on origin/master
        import git as gitmodule
        # Create a "remote" repo with the file on a "master" branch
        remote_path = tmp_path / "remote"
        remote_path.mkdir()
        remote_repo = gitmodule.Repo.init(remote_path, initial_branch="master")
        robocat_json = remote_path / "robocat.json"
        robocat_json.write_text('{"jira": {"project_keys": ["GIT_FALLBACK"]}}')
        remote_repo.index.add(["robocat.json"])
        remote_repo.index.commit("initial")
        # Clone it so we get origin/master
        local_path = tmp_path / "local"
        gitmodule.Repo.clone_from(str(remote_path), str(local_path))

        global_config["repo"]["path"] = str(local_path)
        bot = Bot(global_config, 1, queue.PriorityQueue(),
                  raw_gitlab=mock_gl, config_check_only=True)

        assert bot.config.jira.project_keys == ["GIT_FALLBACK"]
        assert sleep_mock.call_count == 2
        assert sleep_mock.call_args_list == [call(5), call(10)]

    def test_robocat_json_500_git_fallback_fetches_latest(
            self, monkeypatch, global_config, mock_gl, tmp_path):
        monkeypatch.setattr(
            Project, "get_file_content",
            lambda *_, **__: (_ for _ in ()).throw(
                gitlab.GitlabGetError(response_code=500)))
        monkeypatch.setattr(time, "sleep", MagicMock())

        import git as gitmodule
        # Create remote and clone it
        remote_path = tmp_path / "remote"
        remote_path.mkdir()
        remote_repo = gitmodule.Repo.init(remote_path, initial_branch="master")
        robocat_json = remote_path / "robocat.json"
        robocat_json.write_text('{"jira": {"project_keys": ["OLD"]}}')
        remote_repo.index.add(["robocat.json"])
        remote_repo.index.commit("initial")
        local_path = tmp_path / "local"
        gitmodule.Repo.clone_from(str(remote_path), str(local_path))

        # Update the remote after clone
        robocat_json.write_text('{"jira": {"project_keys": ["UPDATED"]}}')
        remote_repo.index.add(["robocat.json"])
        remote_repo.index.commit("update config")

        global_config["repo"]["path"] = str(local_path)
        bot = Bot(global_config, 1, queue.PriorityQueue(),
                  raw_gitlab=mock_gl, config_check_only=True)

        assert bot.config.jira.project_keys == ["UPDATED"]

    def test_robocat_json_500_git_fallback_raises_on_fetch_failure(
            self, monkeypatch, global_config, mock_gl, tmp_path):
        monkeypatch.setattr(
            Project, "get_file_content",
            lambda *_, **__: (_ for _ in ()).throw(
                gitlab.GitlabGetError(response_code=500)))
        monkeypatch.setattr(time, "sleep", MagicMock())

        import git as gitmodule
        remote_path = tmp_path / "remote"
        remote_path.mkdir()
        remote_repo = gitmodule.Repo.init(remote_path, initial_branch="master")
        robocat_json = remote_path / "robocat.json"
        robocat_json.write_text('{"jira": {"project_keys": ["STALE"]}}')
        remote_repo.index.add(["robocat.json"])
        remote_repo.index.commit("initial")
        local_path = tmp_path / "local"
        local_repo = gitmodule.Repo.clone_from(str(remote_path), str(local_path))

        # Break the remote URL so fetch fails
        with local_repo.remotes.origin.config_writer as cw:
            cw.set("url", "/nonexistent/path")

        global_config["repo"]["path"] = str(local_path)
        with pytest.raises(RuntimeError, match="Git fallback also failed"):
            Bot(global_config, 1, queue.PriorityQueue(),
                raw_gitlab=mock_gl, config_check_only=True)

    def test_robocat_json_500_git_fallback_clones_when_repo_missing(
            self, monkeypatch, global_config, mock_gl, tmp_path):
        monkeypatch.setattr(
            Project, "get_file_content",
            lambda *_, **__: (_ for _ in ()).throw(
                gitlab.GitlabGetError(response_code=500)))
        sleep_mock = MagicMock()
        monkeypatch.setattr(time, "sleep", sleep_mock)

        # Create a bare "remote" with robocat.json on master
        import git as gitmodule
        remote_path = tmp_path / "remote"
        remote_path.mkdir()
        remote_repo = gitmodule.Repo.init(remote_path, initial_branch="master")
        robocat_json = remote_path / "robocat.json"
        robocat_json.write_text('{"jira": {"project_keys": ["CLONED"]}}')
        remote_repo.index.add(["robocat.json"])
        remote_repo.index.commit("initial")

        # Point config at a path that doesn't exist yet, with the remote URL
        local_path = tmp_path / "clone_target"
        global_config["repo"]["path"] = str(local_path)
        global_config["repo"]["url"] = str(remote_path)

        bot = Bot(global_config, 1, queue.PriorityQueue(),
                  raw_gitlab=mock_gl, config_check_only=True)

        assert bot.config.jira.project_keys == ["CLONED"]
        assert local_path.exists(), "Repo should have been cloned"

    def test_robocat_json_500_raises_when_git_fallback_also_fails(
            self, monkeypatch, global_config, mock_gl, tmp_path):
        monkeypatch.setattr(
            Project, "get_file_content",
            lambda *_, **__: (_ for _ in ()).throw(
                gitlab.GitlabGetError(response_code=500)))
        sleep_mock = MagicMock()
        monkeypatch.setattr(time, "sleep", sleep_mock)

        global_config["repo"]["path"] = str(tmp_path / "nonexistent")
        with pytest.raises(RuntimeError, match="Git fallback also failed"):
            Bot(global_config, 1, queue.PriorityQueue(),
                raw_gitlab=mock_gl, config_check_only=True)

        assert sleep_mock.call_count == 2

    def test_robocat_json_500_then_success_uses_local_config(
            self, monkeypatch, global_config, mock_gl):
        local_json = '{"jira": {"project_keys": ["LOCAL"]}}'
        call_count = [0]

        def get_file_content_side_effect(*_, **__):
            call_count[0] += 1
            if call_count[0] == 1:
                raise gitlab.GitlabGetError(response_code=500)
            return local_json

        monkeypatch.setattr(Project, "get_file_content", get_file_content_side_effect)
        sleep_mock = MagicMock()
        monkeypatch.setattr(time, "sleep", sleep_mock)

        bot = Bot(global_config, 1, queue.PriorityQueue(),
                  raw_gitlab=mock_gl, config_check_only=True)

        assert bot.config.jira.project_keys == ["LOCAL"]
        assert sleep_mock.call_count == 1
        assert sleep_mock.call_args_list == [call(5)]


class TestBot:
    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Return to development on the second handle iteration if essential rule is ok but
        # open source rule check is failed and merge request is not approved by an eligible user.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "state": "In progress",
            "branches": ["master", "vms_5.1_patch"]
        }], {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [BAD_OPENSOURCE_COMMIT],
            "pipelines_list": [(
                BAD_OPENSOURCE_COMMIT["sha"],
                "success",
                [("open-source:check", "failed"), ("new-open-source-files:check", "failed")],
            )],
        }),
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "state": "In progress",
            "branches": ["master", "vms_5.1_patch"]
        }], {
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
            "type": "Task",
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

        bot._polling = True  # To execute post-merge rules immediately after merge.
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

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # INFRA-636: MR initially appears mergeable, but after refresh it needs rebase.
        # prepare_to_merge should re-fetch MR data and detect the change.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"], "state": "Waiting for QA"}], {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")],
            "detailed_merge_status": "mergeable",
        }),
    ])
    def test_prepare_to_merge_refreshes_mr_data(self, bot, mr, mr_manager):
        """prepare_to_merge re-fetches MR data before the final merge decision (INFRA-636).

        Simulates a race condition where the MR appears mergeable initially but
        needs a rebase after refresh (e.g., target branch moved).
        """
        import robocat.merge_request as mr_module
        original_refresh = mr_module.MergeRequest.refresh

        def mock_refresh(mr_self):
            mr_self._gitlab_mr.detailed_merge_status = "need_rebase"

        mr_module.MergeRequest.refresh = mock_refresh
        try:
            bot.handle(mr_manager)
            assert mr.state != "merged", \
                "MR should NOT be merged after refresh detects need_rebase"
            assert mr.mock_rebased, "Rebase should have been triggered after refresh"
        finally:
            mr_module.MergeRequest.refresh = original_refresh

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

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"]}], {}),
    ])
    def test_run_skips_initial_scan_on_gitlab_error(self, bot, monkeypatch):
        def raise_list_error():
            raise gitlab.GitlabListError("500")

        monkeypatch.setattr(
            bot._project_manager, "get_next_open_merge_request", raise_list_error)

        bot._enqueue_initial_open_mrs()

        assert bot._mr_queue.empty()
