import pytest
from typing import List, Tuple

from robocat.award_emoji_manager import AwardEmojiManager
from robocat.note import Note, MessageId
from automation_tools.tests.gitlab_constants import (
    BAD_OPENSOURCE_COMMIT,
    BAD_OPENCANDIDATE_COMMIT,
    GOOD_README_COMMIT_CHANGED_FILE,
    GOOD_README_COMMIT_NEW_FILE,
    DEFAULT_COMMIT,
    FILE_COMMITS_SHA,
    OPEN_SOURCE_APPROVER_COMMON,
    OPEN_SOURCE_APPROVER_COMMON_2,
    OPEN_SOURCE_APPROVER_CLIENT,
    DEFAULT_REQUIRED_APPROVALS_COUNT)
from automation_tools.tests.mocks.file import (
    GOOD_README_RAW_DATA, BAD_README_RAW_DATA, BAD_README_RAW_DATA_2, GOOD_CPP_RAW_DATA)
from tests.fixtures import *


class TestOpenSourceRule:
    @pytest.mark.parametrize("mr_state", [
        # MR without open source files.
        {
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["no_open_source_files"],
                "message": "msg",
                "diffs": [],
                "files": {"dontreadme.md": {"is_new": True, "raw_data": BAD_README_RAW_DATA}},
            }]
        },
        # MR is changing only the files that are excluded from the open-source compliance check.
        {
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["excluded_open_source_files"],
                "message": "msg",
                "diffs": [],
                "files": {
                    "open/readme.md": {"is_new": True, "raw_data": BAD_README_RAW_DATA},
                    "open/licenses/file.md": {"is_new": True, "raw_data": BAD_README_RAW_DATA},
                    "open/artifacts/nx_kit/src/json11/a/b/c.c": {
                        "is_new": True, "raw_data": BAD_README_RAW_DATA},
                    "open_candidate/some_path/go.mod": {
                        "is_new": True, "raw_data": BAD_README_RAW_DATA},
                    "open/1/2/go.sum": {"is_new": True, "raw_data": BAD_README_RAW_DATA},
                    "open/1/2/SomeData.json": {"is_new": True, "raw_data": BAD_README_RAW_DATA},
                    "open/1/2/file.ts": {"is_new": True, "raw_data": BAD_README_RAW_DATA},
                    "open/1/2/file.ts": {"is_new": True, "raw_data": BAD_README_RAW_DATA},
                    "open/1/2/file.svg": {"is_new": True, "raw_data": BAD_README_RAW_DATA},
                    "open/1/2/file.ui": {"is_new": True, "raw_data": BAD_README_RAW_DATA},
                },
            }],
        },
    ])
    def test_not_applicable(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert open_source_rule.execute(mr_manager)

    @pytest.mark.parametrize("mr_state", [
        {
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "assignees": [{"username": "user1"}],
            "pipelines_list": [(
                GOOD_README_COMMIT_NEW_FILE["sha"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "failed")],
            )],
        },
        {
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "assignees": [{"username": "user1"}, {"username": OPEN_SOURCE_APPROVER_COMMON}],
            "pipelines_list": [(
                GOOD_README_COMMIT_NEW_FILE["sha"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "failed")],
            )],
        },
        {
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "reviewers": [{"username": OPEN_SOURCE_APPROVER_COMMON}],
            "assignees": [{"username": "user1"}],
            "pipelines_list": [(
                GOOD_README_COMMIT_NEW_FILE["sha"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "failed")],
            )],
        },
        {
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "reviewers": [{"username": OPEN_SOURCE_APPROVER_COMMON_2}],
            "assignees": [{"username": "user1"}],
            "pipelines_list": [(
                GOOD_README_COMMIT_NEW_FILE["sha"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "failed")],
            )],
        },
        # Open-source file with undefined preferred approver.
        {
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": "msg",
                "diffs": [],
                "files": {"open/unknown_approver_prefix_dontreadme.md": {
                    "is_new": True, "raw_data": GOOD_README_RAW_DATA
                }},
            }],
            "assignees": [{"username": "user1"}],
            "pipelines_list": [(
                FILE_COMMITS_SHA["good_dontreadme"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "failed")],
            )],
        },
        # Not a follow-up Merge Request with new files.
        {
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": "msg",
                "diffs": [],
                "files": {"open/dontreadme.md": {
                    "is_new": True, "raw_data": GOOD_README_RAW_DATA
                }},
            }],
            "pipelines_list": [(
                FILE_COMMITS_SHA["good_dontreadme"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "failed")],
            )],
        },
    ])
    def test_set_assignee(self, open_source_rule, mr, mr_manager):
        reviewers_before = {r["username"] for r in mr.reviewers}
        approvers_before = (
            {a["username"] for a in mr.assignees} | reviewers_before | set([mr.author["username"]])
        )
        authorized_approvers = {
            OPEN_SOURCE_APPROVER_COMMON, OPEN_SOURCE_APPROVER_COMMON_2,
            OPEN_SOURCE_APPROVER_CLIENT}

        for _ in range(2):  # State must not change after any number of rule executions.
            assert not open_source_rule.execute(mr_manager)

            assignees = {a["username"] for a in mr.assignees}
            if reviewers_before.intersection(authorized_approvers):
                assert not authorized_approvers.intersection(assignees), (
                    f"Authorized approver(s) assigned: {assignees}")
            else:
                assert assignees.intersection(authorized_approvers), (
                    f"Authorized approver(s) not assigned: {assignees}")

            has_file_without_preferred_approver = any(
                [f for f in mr.changes()["changes"] if f["new_path"].startswith("open/unknown_")])
            addition_approvers = 1 if has_file_without_preferred_approver else 0

            approvers = (
                {r["username"] for r in mr.reviewers} | assignees | set([mr.author["username"]]))
            if approvers_before.intersection(authorized_approvers):
                assert len(approvers) == 2 + addition_approvers, f"Got approvers: {approvers}"
            else:
                assert len(approvers) == 3 + addition_approvers, f"Got approvers: {approvers}"

            if approvers_before.intersection(authorized_approvers):
                assert mr_manager._mr.get_approvers_count() == DEFAULT_REQUIRED_APPROVALS_COUNT
            else:
                assert mr_manager._mr.get_approvers_count() == DEFAULT_REQUIRED_APPROVALS_COUNT + 1

    @pytest.mark.parametrize("mr_state", [
        # Simple Merge Request with "good" changes in a new file.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "pipelines_list": [(
                GOOD_README_COMMIT_NEW_FILE["sha"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "failed")],
            )],
        },
    ])
    def test_good_new_files_comments(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not open_source_rule.execute(mr_manager)

            assert not mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            assert len(comments) == 2, f"Got comments: {comments}"
            assert f":{AwardEmojiManager.NEED_MANUAL_CHECK_EMOJI}:" in comments[0], (
                f"First comment is: {comments[0]}")
            message_details = f"{Note.ID_KEY}: {MessageId.OpenSourceNoProblemNeedApproval.value}"
            assert message_details in comments[0], f"First comment is: {comments[0]}"
            assert f"Update assignee list" in comments[1], (
                f"Last comment is: {comments[1]}")

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

    @pytest.mark.parametrize("mr_state", [
        # Simple Merge Request with "good" changes in an old file.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [GOOD_README_COMMIT_CHANGED_FILE],
            "pipelines_list": [(
                GOOD_README_COMMIT_CHANGED_FILE["sha"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "success")],
            )],
        },
        # Follow-up Merge Request with new files.
        {
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": "msg",
                "diffs": [],
                "files": {"open/dontreadme.md": {
                    "is_new": True, "raw_data": GOOD_README_RAW_DATA
                }},
            }],
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "pipelines_list": [(
                GOOD_README_COMMIT_NEW_FILE["sha"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "failed")],
            )],
        },
        # Has new files in non-followup Merge Request but the author is an authorized approver.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "author": {"username": OPEN_SOURCE_APPROVER_COMMON},
            "pipelines_list": [(
                GOOD_README_COMMIT_NEW_FILE["sha"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "failed")],
            )],
        },
    ])
    def test_changes_are_ok(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert open_source_rule.execute(mr_manager)
            assert mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            assert len(comments) == 1, f"Got comments: {comments}"
            assert f":{AwardEmojiManager.AUTOCHECK_OK_EMOJI}:" in comments[0], (
                f"Last comment is: {comments[0]}")

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

    @pytest.mark.parametrize("mr_state", [
        # Bad changes in the new file of the non-followup Merge Request.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [BAD_OPENCANDIDATE_COMMIT],
            "pipelines_list": [(
                BAD_OPENCANDIDATE_COMMIT["sha"],
                "success",
                [("open-source:check", "failed"), ("new-open-source-files:check", "failed")],
            )],
        },
        # Bad changes in the new file of the follow-up Merge Request.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["opensource_bad_new_file"],
                "message": "msg1",
                "diffs": [],
                "files": {"open/badtype.foobar": {"is_new": True, "raw_data": ""}},
            }],
            "pipelines_list": [(
                FILE_COMMITS_SHA["opensource_bad_new_file"],
                "success",
                [("open-source:check", "failed"), ("new-open-source-files:check", "failed")],
            )],
        },
    ])
    def test_bad_changes_new_files(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not open_source_rule.execute(mr_manager)
            assert not mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            assert len(comments) == 2, f"Got comments: {comments}"
            assert f":{AwardEmojiManager.AUTOCHECK_FAILED_EMOJI}:" in comments[0], (
                f"First comment is: {comments[0]}")
            if mr_manager.is_followup():
                message_details = (
                    f"{Note.ID_KEY}: {MessageId.OpenSourceHasBadChangesCallKeeperOptional.value}")
            else:
                message_details = (
                    f"{Note.ID_KEY}: {MessageId.OpenSourceHasBadChangesCallKeeperMandatory.value}")
            assert message_details in comments[0], f"First comment is: {comments[0]}"
            assert f"Update assignee list" in comments[1], f"Last comment is: {comments[1]}"

            mr_manager._mr.load_discussions()  # Update notes in the MergeRequest object.

    @pytest.mark.parametrize("mr_state", [
        # Bad changes in the old file of the non-follow-up Merge Request.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [BAD_OPENSOURCE_COMMIT],
            "pipelines_list": [(
                BAD_OPENSOURCE_COMMIT["sha"],
                "success",
                [("open-source:check", "failed"), ("new-open-source-files:check", "success")],
            )],
        },
        # Bad changes in the old file of the follow-up Merge Request.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["opensource_unknown_file"],
                "message": "msg1",
                "diffs": [],
                "files": {"open/badtype.foobar": {"is_new": False, "raw_data": ""}},
            }],
            "pipelines_list": [(
                FILE_COMMITS_SHA["opensource_unknown_file"],
                "success",
                [("open-source:check", "failed"), ("new-open-source-files:check", "success")],
            )],
        },
    ])
    def test_bad_changes_no_new_files(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not open_source_rule.execute(mr_manager)
            assert not mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            assert len(comments) == 1, f"Got comments: {comments}"
            assert f":{AwardEmojiManager.AUTOCHECK_FAILED_EMOJI}:" in comments[0], (
                f"First comment is: {comments[0]}")
            message_details = (
                f"\n{Note.ID_KEY}: {MessageId.OpenSourceHasBadChangesCallKeeperOptional.value}")
            assert message_details in comments[0], f"First comment is: {comments[0]}"

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

    @pytest.mark.parametrize("mr_state", [
        # Merge allowed if everything is good and merge request approved by an eligible user.
        {
            "blocking_discussions_resolved": True,
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "pipelines_list": [(
                GOOD_README_COMMIT_NEW_FILE["sha"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "success")],
            )],
        },
        # Merge allowed even if there are bad files, but merge request approved by an eligible
        # user.
        {
            "blocking_discussions_resolved": True,
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "commits_list": [BAD_OPENSOURCE_COMMIT],
            "pipelines_list": [(
                BAD_OPENSOURCE_COMMIT["sha"],
                "success",
                [("open-source:check", "failed"), ("new-open-source-files:check", "failed")],
            )],
        },
    ])
    def test_merge_allowed(self, open_source_rule, mr, mr_manager):
        assert open_source_rule.execute(mr_manager)

    # Don't add comments for the errors already found after new commits are added to the merge
    # request.
    @pytest.mark.parametrize("mr_state", [
        {
            "commits_list": [BAD_OPENSOURCE_COMMIT],
            "pipelines_list": [(
                BAD_OPENSOURCE_COMMIT["sha"],
                "success",
                [("open-source:check", "failed"), ("new-open-source-files:check", "success")],
            )],
        },
    ])
    def test_update_comments_for_found_errors(self, open_source_rule, mr, mr_manager):
        def add_commit_and_execute_rule(sha, files, has_errors, has_new_files):
            # Add new commit.
            commit_data = BAD_OPENSOURCE_COMMIT.copy()
            commit_data["sha"] = sha
            commit_data["files"] = files
            pipeline_data = {
                "jobs": {
                    ("open-source:check", "failed" if has_errors else "success"),
                    ("new-open-source-files:check", "failed" if has_new_files else "success"),
                },
            }
            mr.add_mock_commit(commit_data)
            mr.add_mock_pipeline(pipeline_data)
            mr_manager._get_last_pipeline_by_status.cache_clear()

            # Reload discussions and execute the rule for the new Merge Request state.
            mr_manager._mr.load_discussions()
            open_source_rule.execute(mr_manager)

        expected_comments_number = 1

        open_source_rule.execute(mr_manager)
        comments = mr.mock_comments()
        assert len(comments) == expected_comments_number, f"Got comments: {comments}"

        # Add commit to the Merge Request with a "good" file - now we have new files in the MR, so
        # it must be checked manually.
        expected_comments_number += 2

        add_commit_and_execute_rule(
            sha=FILE_COMMITS_SHA["good_opensource_file"],
            files={"open/good.cpp": {"is_new": True, "raw_data": GOOD_CPP_RAW_DATA}},
            has_errors=True,
            has_new_files=True)

        comments = mr.mock_comments()
        assert len(comments) == expected_comments_number, f"Got comments: {comments}"
        assert f":{AwardEmojiManager.AUTOCHECK_FAILED_EMOJI}:" in comments[-2], (
                f"Unexpected comment: {comments[-2]}")
        assert f":{AwardEmojiManager.NOTIFICATION_EMOJI}:" in comments[-1], (
                f"Unexpected comment: {comments[-1]}")

        # Add the commit to the MR with the same "bad" file - no comments should be added.

        add_commit_and_execute_rule(
            sha=FILE_COMMITS_SHA["new_bad_dontreadme"],
            files={"open/dontreadme.md": {"is_new": True, "raw_data": BAD_README_RAW_DATA_2}},
            has_errors=True,
            has_new_files=True)

        comments = mr.mock_comments()
        assert len(comments) == expected_comments_number, f"Got comments: {comments}"

        # Add the commit to the Merge Request with the same file, but without bad words - the
        # "manual check is required" comment should be added.
        expected_comments_number += 1

        add_commit_and_execute_rule(
            sha=FILE_COMMITS_SHA["good_dontreadme"],
            files={"open/dontreadme.md": {"is_new": True, "raw_data": GOOD_README_RAW_DATA}},
            has_errors=False,
            has_new_files=True)

        comments = mr.mock_comments()
        assert len(comments) == expected_comments_number, f"Got comments: {comments}"
        assert f":{AwardEmojiManager.NEED_MANUAL_CHECK_EMOJI}:" in comments[-1], (
                f"Unexpected comment: {comments[-1]}")

        # Add the commit to the Merge Request removing the new file - the "everything is ok"
        # comment should be added.
        expected_comments_number += 1

        add_commit_and_execute_rule(
            sha=FILE_COMMITS_SHA["opensource_deleted_new_file"],
            files={"open/good.cpp.md": {"is_deleted": True, "raw_data": GOOD_README_RAW_DATA}},
            has_errors=False,
            has_new_files=False)

        comments = mr.mock_comments()
        assert len(comments) == expected_comments_number, f"Got comments: {comments}"
        assert f":{AwardEmojiManager.AUTOCHECK_OK_EMOJI}:" in comments[-1], (
                f"Unexpected comment: {comments[-1]}")

    # Re-check files if the merge request target branch changed.
    @pytest.mark.parametrize("mr_state", [
        {
            "commits_list": [BAD_OPENSOURCE_COMMIT],
            "pipelines_list": [(
                BAD_OPENSOURCE_COMMIT["sha"],
                "success",
                [("open-source:check", "failed"), ("new-open-source-files:check", "success")],
            )],
        },
    ])
    def test_re_check_after_mr_target_branch_changed(self, open_source_rule, mr, mr_manager):
        initial_approvers_count = mr_manager._mr.get_approvers_count()
        assert not open_source_rule.execute(mr_manager)
        assert not mr.blocking_discussions_resolved
        assert mr_manager._mr.get_approvers_count() == initial_approvers_count

        # Fix files in commit leaving the same sha. We emulate different changes when the user sets
        # the new target branch to the Merge Request.
        updated_bad_open_source_commit = DEFAULT_COMMIT.copy()
        updated_bad_open_source_commit["sha"] = BAD_OPENSOURCE_COMMIT["sha"]
        mr.commits_list = [updated_bad_open_source_commit]
        mr._register_commit(updated_bad_open_source_commit)
        mr.add_mock_pipeline({
            "jobs": {("open-source:check", "success"), ("new-open-source-files:check", "success")},
        })
        mr_manager._get_last_pipeline_by_status.cache_clear()
        mr.target_branch = "changed_branch"

        assert open_source_rule.execute(mr_manager)
        assert mr_manager._mr.get_approvers_count() == initial_approvers_count

    @pytest.mark.parametrize("mr_state", [
        # The bad file is new.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [BAD_OPENCANDIDATE_COMMIT],
            "author": {"username": OPEN_SOURCE_APPROVER_COMMON},
            "pipelines_list": [(
                BAD_OPENCANDIDATE_COMMIT["sha"],
                "success",
                [("open-source:check", "failed"), ("new-open-source-files:check", "failed")],
            )],
        },
        # Bad file is not new.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [BAD_OPENSOURCE_COMMIT],
            "author": {"username": OPEN_SOURCE_APPROVER_COMMON},
            "pipelines_list": [(
                BAD_OPENSOURCE_COMMIT["sha"],
                "success",
                [("open-source:check", "failed"), ("new-open-source-files:check", "success")],
            )],
        },
    ])
    def test_files_are_not_ok_comments_author_is_approver(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert open_source_rule.execute(mr_manager)
            assert not mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            assert len(comments) == 1, f"Got comments: {comments}"
            assert "check carefully all the issues" in comments[0], (
                f"Unexpected comment: {comments[0]}")

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.
