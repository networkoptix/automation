import pytest

from robocat.award_emoji_manager import AwardEmojiManager
from robocat.rule.essential_rule import EssentialRule
from tests.robocat_constants import DEFAULT_COMMIT, DEFAULT_JIRA_ISSUE_KEY
from tests.fixtures import *


class TestEssentialRule:
    def test_initial_comment(self, essential_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not essential_rule.execute(mr_manager)

            emojis = mr.awardemojis.list()
            assert any(e for e in emojis if e.name == AwardEmojiManager.WATCH_EMOJI), (
                "Has watch emoji.")

            comments = mr.mock_comments()
            assert len(comments) == 2, f"Got comments: {comments}"
            assert any(c for c in comments if f":{AwardEmojiManager.INITIAL_EMOJI}:" in c), (
                f"Last comment: {mr.mock_comments()[0]}.")

    @pytest.mark.parametrize("mr_state", [
        {"commits_list": []}
    ])
    def test_wait_commits(self, essential_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not essential_rule.execute(mr_manager)

            emojis = mr.awardemojis.list()
            assert any(e for e in emojis if e.name == AwardEmojiManager.WAIT_EMOJI), (
                "Has wait emoji.")

            comments = mr.mock_comments()
            assert len(comments) == 1, f"Got comments: {comments}"
            assert "Waiting for commits" in comments[-1], (f"Last comment: {comments[-1]}.")

    @pytest.mark.parametrize("mr_state", [
        {
            "needed_approvers_number": 1,
            "pipelines_list": [
                (DEFAULT_COMMIT["sha"], "running")]
        }
    ])
    def test_wait_approvals(self, essential_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not essential_rule.execute(mr_manager)

            emojis = mr.awardemojis.list()
            assert any(e for e in emojis if e.name == AwardEmojiManager.WAIT_EMOJI), (
                "Has wait emoji.")

            comments = mr.mock_comments()
            assert len(comments) == 2, f"Got comments: {comments}"
            assert "Waiting for approvals" in comments[-1], (f"Last comment: {comments[-1]}.")

    @pytest.mark.parametrize("mr_state", [
        {
            "needed_approvers_number": 0,
            "pipelines_list": [
                (DEFAULT_COMMIT["sha"], "running")]
        }
    ])
    def test_wait_pipelines(self, essential_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not essential_rule.execute(mr_manager)

            emojis = mr.awardemojis.list()
            assert any(e for e in emojis if e.name == AwardEmojiManager.WAIT_EMOJI), (
                "Has wait emoji.")

            comments = mr.mock_comments()
            assert len(comments) == 2, f"Got comments: {comments}"
            assert "Waiting for pipeline" in comments[-1], (f"Last comment: {comments[-1]}.")

    @pytest.mark.parametrize("mr_state", [
        # Pipeline started ignoring insufficient approvers number because there were no pipeline
        # runs at all.
        {},
        # Pipeline started even if the build failed when requested
        {
            "emojis_list": [AwardEmojiManager.PIPELINE_EMOJI],
            "commits_list": [
                DEFAULT_COMMIT,
                {"sha": "22", "message": DEFAULT_COMMIT["message"]},
            ],
            "pipelines_list": [(DEFAULT_COMMIT["sha"], "failed")]
        },
        # First pipeline started even if there are non-resolved discusions
        {"blocking_discussions_resolved": False},
        # Pipeline started if fail was in previous commit, in new commit nothing has changed
        # (rebase) and otherwise MR is ready to merge (no unresolved discussions and enough
        # approvals)
        {
            "needed_approvers_number": 0,
            "commits_list": [
                {"sha": "22", "message": DEFAULT_COMMIT["message"]},
                DEFAULT_COMMIT],
            "pipelines_list": [
                ("22", "failed"),
                (DEFAULT_COMMIT["sha"], "manual")]
        },
        # Pipeline started if fail was in previous commit, in new commit commit message changed
        # (ammend) and otherwise MR is ready to merge (no unresolved discussions and enough
        # approvals)
        {
            "needed_approvers_number": 0,
            "commits_list": [
                {"sha": "23", "message": "old_message"},
                DEFAULT_COMMIT],
            "pipelines_list": [
                ("23", "failed"),
                (DEFAULT_COMMIT["sha"], "manual")]
        },
        # Pipeline started if fail was in previous commit, in new commit commit changes were
        # introduced and otherwise MR is ready to merge (no unresolved discussions and enough
        # approvals)
        {
            "needed_approvers_number": 0,
            "commits_list": [
                {
                    "sha": "24",
                    "message": DEFAULT_COMMIT["message"],
                    "diffs": ["old diff"]
                },
                DEFAULT_COMMIT],
            "pipelines_list": [
                ("24", "failed"),
                (DEFAULT_COMMIT["sha"], "manual")]
        },
        # Pipeline started if success was in previous commit, in new commit commit message changed
        # (ammend) and otherwise MR is ready to merge (no unresolved discussions and enough
        # approvals)
        {
            "needed_approvers_number": 0,
            "commits_list": [
                {"sha": "25", "message": "old_message"},
                DEFAULT_COMMIT],
            "pipelines_list": [
                ("25", "success"),
                (DEFAULT_COMMIT["sha"], "manual")]
        },
        # Pipeline started if success was in previous commit, in new commit commit changes were
        # introduced and otherwise MR is ready to merge (no unresolved discussions and enough
        # approvals)
        {
            "needed_approvers_number": 0,
            "commits_list": [
                {
                    "sha": "26",
                    "message": DEFAULT_COMMIT["message"],
                    "diffs": ["old diff"]
                },
                DEFAULT_COMMIT],
            "pipelines_list": [
                ("26", "success"),
                (DEFAULT_COMMIT["sha"], "manual")]
        },
        # Pipeline started if previous commit pipeline is still running, in new commit commit
        # message changed (ammend) and otherwise MR is ready to merge (no unresolved discussions
        # and enough approvals)
        {
            "needed_approvers_number": 0,
            "commits_list": [
                {"sha": "27", "message": "old_message"},
                DEFAULT_COMMIT],
            "pipelines_list": [
                ("27", "running"),
                (DEFAULT_COMMIT["sha"], "manual")]
        },
        # Pipeline started if previous commit pipeline is still running, in new commit changes were
        # introduced and otherwise MR is ready to merge (no unresolved discussions and enough
        # approvals)
        {
            "needed_approvers_number": 0,
            "commits_list": [
                {
                    "sha": "28",
                    "message": DEFAULT_COMMIT["message"],
                    "diffs": ["old diff"]
                },
                DEFAULT_COMMIT],
            "pipelines_list": [
                ("28", "running"),
                (DEFAULT_COMMIT["sha"], "manual")]
        },
    ])
    def test_run_pipeline(self, essential_rule, mr, mr_manager):
        if current_sha_pipelines := [p for p in mr.pipelines() if p["sha"] == mr.sha]:
            last_pipeline_status = current_sha_pipelines[0]["status"]
        else:
            last_pipeline_status = None
        is_pipeline_creation_requested = any(
            e for e in mr.emojis_list if e == AwardEmojiManager.PIPELINE_EMOJI)
        initial_pipelines_number = len(mr.pipelines())
        expected_comments_count = 2 if mr.blocking_discussions_resolved else 3

        for _ in range(2):  # State must not change after any number of rule executions.
            assert not essential_rule.execute(mr_manager)

            assert not mr.work_in_progress

            comments = mr.mock_comments()
            assert len(comments) == expected_comments_count, f"Got comments: {comments}"
            assert f":{AwardEmojiManager.PIPELINE_EMOJI}:" in comments[-1], (
                f"Last comment: {comments[-1]}.")

            pipelines = mr.pipelines()
            if is_pipeline_creation_requested:
                if last_pipeline_status == "manual":
                    assert len(pipelines) == initial_pipelines_number, (
                        "Don't create new pipeline if merge request has one ready to start.")
                else:
                    assert len(pipelines) == initial_pipelines_number + 1, (
                        "Create new pipeline if requested.")
            assert pipelines[0]["status"] == "running", f"Got pipelines: {pipelines}"

            emojis = mr.awardemojis.list()
            assert not any(e for e in emojis if e.name == AwardEmojiManager.PIPELINE_EMOJI), (
                "No pipeline start emoji.")

    @pytest.mark.parametrize("mr_state", [
        # Don't run pipeline if there are no commits
        {
            "needed_approvers_number": 0,
            "commits_list": []
        },
        # Don't run pipeline if work in progress
        {
            "needed_approvers_number": 0,
            "work_in_progress": True,
        },
        # Don't run pipeline if has conflicts
        {
            "needed_approvers_number": 0,
            "has_conflicts": True
        },
        # Don't run pipeline if there are not enough approvers and pipeline ran at lease once
        {
            "needed_approvers_number": 1,
            "commits_list": [
                {"sha": "22", "message": DEFAULT_COMMIT["message"]},
                DEFAULT_COMMIT],
            "pipelines_list": [
                ("22", "failed"),
                (DEFAULT_COMMIT["sha"], "manual")]
        },
        # Don't run pipeline if pipeline is already running and nothing has changed
        {
            "needed_approvers_number": 0,
            "pipelines_list": [(DEFAULT_COMMIT["sha"], "running")]
        },
        # Don't run pipeline if previous pipeline failed and nothing has changed
        {
            "needed_approvers_number": 0,
            "pipelines_list": [
                (DEFAULT_COMMIT["sha"], "failed"),
                (DEFAULT_COMMIT["sha"], "manual")]
        },
        # Don't run pipeline if previous pipeline succeeded and nothing has changed
        {
            "needed_approvers_number": 0,
            "pipelines_list": [
                (DEFAULT_COMMIT["sha"], "success"),
                (DEFAULT_COMMIT["sha"], "manual")]
        },
        # Don't run pipeline if pipeline is already running and MR was rebased
        # threads
        {
            "needed_approvers_number": 0,
            "commits_list": [
                {"sha": "22", "message": DEFAULT_COMMIT["message"]},
                DEFAULT_COMMIT],
            "pipelines_list": [
                ("22", "running"),
                (DEFAULT_COMMIT["sha"], "manual")]
        },
        # Don't run pipeline if previous pipeline failed, MR was rebased and there are unresolved
        # threads
        {
            "needed_approvers_number": 0,
            "blocking_discussions_resolved": False,
            "commits_list": [
                {"sha": "22", "message": DEFAULT_COMMIT["message"]},
                DEFAULT_COMMIT],
            "pipelines_list": [
                ("22", "failed"),
                (DEFAULT_COMMIT["sha"], "manual")]
        },
        # Don't run pipeline if previous pipeline succeeded and MR was rebased
        {
            "needed_approvers_number": 0,
            "commits_list": [
                {"sha": "22", "message": DEFAULT_COMMIT["message"]},
                DEFAULT_COMMIT],
            "pipelines_list": [
                ("22", "success"),
                (DEFAULT_COMMIT["sha"], "manual")]
        },
        # User-requested pipeline not started if previous pipeline ran for the same sha
        {
            "emojis_list": [AwardEmojiManager.PIPELINE_EMOJI],
            "pipelines_list": [(DEFAULT_COMMIT["sha"], "failed")]
        },
    ])
    def test_norun_pipeline(self, essential_rule, mr, mr_manager):
        initial_pipelines_number = len(mr.pipelines())
        if mr.sha:
            last_pipeline_status = next(p for p in mr.pipelines() if p["sha"] == mr.sha)["status"]

        for _ in range(2):  # State must not change after any number of rule executions.
            essential_rule.execute(mr_manager)

            pipelines = mr.pipelines()
            assert len(pipelines) == initial_pipelines_number
            if mr.sha and last_pipeline_status != "running":
                assert pipelines[0]["status"] != "running", f"Got pipelines: {pipelines}"

            comments = mr.mock_comments()
            assert not any(
                c for c in comments if f"# :{AwardEmojiManager.PIPELINE_EMOJI}:" in c), (
                f"Got comments: {comments}")

    @pytest.mark.parametrize(("mr_state", "expected_result", "expected_comment"), [
        # Has conflicts.
        ({
            "needed_approvers_number": 0,
            "has_conflicts": True
        }, EssentialRule.ExecutionResult.has_conflicts, "Please, do manual rebase"),
        # Has unresolved threads, and the pipeline has succeeded.
        ({
            "needed_approvers_number": 0,
            "blocking_discussions_resolved": False,
            "pipelines_list": [(DEFAULT_COMMIT["sha"], "success")]
        }, EssentialRule.ExecutionResult.unresolved_threads, "Please, resolve all discussions"),
        # Has unresolved threads, and the pipeline has failed.
        ({
            "needed_approvers_number": 0,
            "blocking_discussions_resolved": False,
            "pipelines_list": [(DEFAULT_COMMIT["sha"], "failed")]
        }, EssentialRule.ExecutionResult.unresolved_threads, "Please, resolve all discussions"),
        # No unresolved threads, pipeline has failed, and no new commits.
        ({
            "needed_approvers_number": 0,
            "pipelines_list": [(DEFAULT_COMMIT["sha"], "failed")]
        }, EssentialRule.ExecutionResult.pipeline_failed, "Please, fix the errors"),
        # Bad Jira Project.
        ({
            "title": "UNKNOWN-666: Test mr",
        }, EssentialRule.ExecutionResult.bad_project_list, "Please, link this Merge Request"),
    ])
    def test_return_to_development(
            self, essential_rule, mr, mr_manager, expected_result, expected_comment):

        assert essential_rule.execute(mr_manager) == expected_result

        assert mr.work_in_progress

        comments = mr.mock_comments()
        assert "Merge Request returned to development" in comments[-1], (
            f"Got comments: {comments}")
        assert expected_comment in comments[-1], f"Got comment: {comments[-1]}"

        assert essential_rule.execute(mr_manager) in [
            EssentialRule.ExecutionResult.work_in_progress, expected_result]

    @pytest.mark.parametrize("mr_state", [
        # Good MR linked to a good Jira Project.
        {
            "emojis_list": [AwardEmojiManager.WATCH_EMOJI],
            "needed_approvers_number": 2,
            "approvers_list": ["user1", "user2"],
            "pipelines_list": [(DEFAULT_COMMIT["sha"], "success")],
        },
        # Good MR linked to one good and one bad Jira Project.
        {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, UNKNOWN-666: Test mr",
            "emojis_list": [AwardEmojiManager.WATCH_EMOJI],
            "needed_approvers_number": 2,
            "approvers_list": ["user1", "user2"],
            "pipelines_list": [(DEFAULT_COMMIT["sha"], "success")],
            "commits_list": [
                {
                    "sha": DEFAULT_COMMIT["sha"],
                    "message": "{DEFAULT_JIRA_ISSUE_KEY}, UNKNOWN-666: Commit for test mr",
                },
            ],
        },
    ])
    def test_merge_allowed(self, essential_rule, mr, mr_manager):
        for _ in range(2):
            assert essential_rule.execute(mr_manager)
