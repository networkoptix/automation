import pytest

from robocat.award_emoji_manager import AwardEmojiManager
from tests.common_constants import (
    BAD_OPENSOURCE_COMMIT,
    BAD_OPENCANDIDATE_COMMIT,
    DEFAULT_COMMIT,
    FILE_COMMITS_SHA,
    DEFAULT_OPEN_SOURCE_APPROVER,
    DEFAULT_REQUIRED_APPROVALS_COUNT)
from tests.fixtures import *


class TestOpenSourceRule:
    @pytest.mark.parametrize("mr_state", [
        # MR without open source files.
        {
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["no_open_source_files"],
                "message": "msg",
                "diffs": [],
                "files": {"dontreadme.md": {"is_new": True}},
            }]
        },
        # MR is changing only the files that are excluded from the open-source compliance check.
        {
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["excluded_open_source_files"],
                "message": "msg",
                "diffs": [],
                "files": {
                    "open/readme.md": {"is_new": True},
                    "open/licenses/some_file.md": {"is_new": True},
                    "open/artifacts/nx_kit/src/json11/a/b/c.c": {"is_new": True},
                    "open_candidate/some_path/go.mod": {"is_new": True},
                    "open/1/2/go.sum": {"is_new": True},
                    "open/1/2/SomeData.json": {"is_new": True},
                },
            }],
        },
    ])
    def test_not_applicable(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert open_source_rule.execute(mr_manager)

    @pytest.mark.parametrize("mr_state", [
        {
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": "msg",
                "diffs": [],
                "files": {"open/dontreadme.md": {"is_new": True}},
            }],
            "assignees": [{"username": "user1"}]
        },
        {
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": "msg",
                "diffs": [],
                "files": {"open/dontreadme.md": {"is_new": True}},
            }],
            "assignees": [{"username": "user1"}, {"username": DEFAULT_OPEN_SOURCE_APPROVER}]
        },
        {
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": "msg",
                "diffs": [],
                "files": {"open/dontreadme.md": {"is_new": True}},
            }],
            "mock_huge_mr": True,
            "assignees": [{"username": "user1"}]
        },
    ])
    def test_set_assignee(self, open_source_rule, mr, mr_manager):
        initial_assignee_count = len(mr.assignees)
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not open_source_rule.execute(mr_manager)

            assignees = {a["username"] for a in mr.assignees}
            assert len(assignees) == 2, f"Got assignees: {assignees}"
            assert DEFAULT_OPEN_SOURCE_APPROVER in assignees, f"Got assignees: {assignees}"

            if len(mr.assignees) == initial_assignee_count:
                assert mr_manager._mr.get_approvers_count() == DEFAULT_REQUIRED_APPROVALS_COUNT
            else:
                assert mr_manager._mr.get_approvers_count() == DEFAULT_REQUIRED_APPROVALS_COUNT + 1

    @pytest.mark.parametrize("mr_state", [
        {
            "blocking_discussions_resolved": True,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": "msg",
                "diffs": [],
                "files": {"open/dontreadme.md": {"is_new": True}},
            }],
            "mock_huge_mr": True,
        },
    ])
    def test_cannot_check_files(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not open_source_rule.execute(mr_manager)

            assert not mr.blocking_discussions_resolved

            comments = mr.comments()
            assert len(comments) == 1, f"Got comments: {comments}"
            assert f":{AwardEmojiManager.AUTOCHECK_IMPOSSIBLE_EMOJI}:" in comments[0], (
                f"Last comment is: {comments[0]}")

    @pytest.mark.parametrize("mr_state", [
        {
            "blocking_discussions_resolved": True,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": "msg",
                "diffs": [],
                "files": {"open/dontreadme.md": {"is_new": True}},
            }],
        },
    ])
    def test_files_are_ok_comments(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not open_source_rule.execute(mr_manager)

            assert not mr.blocking_discussions_resolved

            comments = mr.comments()
            assert len(comments) == 1, f"Got comments: {comments}"
            assert f":{AwardEmojiManager.AUTOCHECK_OK_EMOJI}:" in comments[0], (
                f"Last comment is: {comments[0]}")

    @pytest.mark.parametrize("mr_state", [
        {
            "blocking_discussions_resolved": True,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": "msg",
                "diffs": [],
                "files": {"open/dontreadme.md": {"is_new": False}},
            }],
        },
    ])
    def test_files_dont_need_manual_check(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert open_source_rule.execute(mr_manager)

            assert mr.blocking_discussions_resolved

            comments = mr.comments()
            assert len(comments) == 1, f"Got comments: {comments}"
            assert f":{AwardEmojiManager.AUTOCHECK_OK_EMOJI}:" in comments[0], (
                f"Last comment is: {comments[0]}")

    @pytest.mark.parametrize("mr_state", [
        # File is in the "open" directory.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [BAD_OPENSOURCE_COMMIT]
        },
        # File is in the "open_candidate" directory.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [BAD_OPENCANDIDATE_COMMIT]
        },
        # Bad file is not new.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["bad_dontreadme"],
                "message": "msg1",
                "diffs": [],
                "files": {"open/dontreadme.md": {"is_new": False}},
            }],
        },
    ])
    def test_files_are_not_ok_comments(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not open_source_rule.execute(mr_manager)

            assert not mr.blocking_discussions_resolved

            comments = mr.comments()
            assert len(comments) == 4, f"Got comments: {comments}"
            for i, bad_word in enumerate(['Copyrleft', 'shit', 'fuck', 'blya']):
                assert f":{AwardEmojiManager.AUTOCHECK_FAILED_EMOJI}:" in comments[i], (
                    f"Comment {i} is: {comments[i]}")
                assert bad_word in comments[i], f"Comment {i} is: {comments[i]}"
                assert f"resolved only after" in comments[i], (
                    f"Comment {i} is: {comments[i]}")

    @pytest.mark.parametrize("mr_state", [
        # Merge allowed if everything is good and merge request approved by eligible user
        {
            "blocking_discussions_resolved": True,
            "approvers_list": [DEFAULT_OPEN_SOURCE_APPROVER],
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": "msg",
                "diffs": [],
                "files": {"open/dontreadme.md": {"is_new": True}}
            }],
        },
        # Merge allowed even if there are bad files, but merge request approved by an eligible
        # user.
        {
            "blocking_discussions_resolved": True,
            "approvers_list": [DEFAULT_OPEN_SOURCE_APPROVER],
            "commits_list": [BAD_OPENSOURCE_COMMIT]
        },
    ])
    def test_merge_allowed(self, open_source_rule, mr, mr_manager):
        assert open_source_rule.execute(mr_manager)

    # Don't add comments for the errors already found after new commits are added to the merge
    # request.
    @pytest.mark.parametrize("mr_state", [
        {"commits_list": [BAD_OPENSOURCE_COMMIT]},
    ])
    def test_update_comments_for_found_errors(self, open_source_rule, mr, mr_manager):
        open_source_rule.execute(mr_manager)

        comments = mr.comments()
        assert len(comments) == 4, f"Got comments: {comments}"
        for i, bad_word in enumerate(['Copyrleft', 'shit', 'fuck', 'blya']):
            assert f":{AwardEmojiManager.AUTOCHECK_FAILED_EMOJI}:" in comments[i], (
                f"Comment {i} is: {comments[i]}")
            assert bad_word in comments[i], f"Comment {i} is: {comments[i]}"
            assert f"resolved only after" in comments[i], (
                f"Comment {i} is: {comments[i]}")

        # Add commit to the Merge Request with the same file, but without bad words - no new
        # comments must be added.
        updated_bad_open_source_commit = BAD_OPENSOURCE_COMMIT.copy()
        updated_bad_open_source_commit["sha"] = FILE_COMMITS_SHA["good_dontreadme"]
        updated_bad_open_source_commit["files"] = {"open/dontreadme.md": {"is_new": True}}
        mr.commits_list.append(updated_bad_open_source_commit)
        mr._register_commit(updated_bad_open_source_commit)

        open_source_rule.execute(mr_manager)

        comments = mr.comments()
        assert len(comments) == 4, f"Got comments: {comments}"
        for i, bad_word in enumerate(['Copyrleft', 'shit', 'fuck', 'blya']):
            assert f":{AwardEmojiManager.AUTOCHECK_FAILED_EMOJI}:" in comments[i], (
                f"Comment {i} is: {comments[i]}")
            assert bad_word in comments[i], f"Comment {i} is: {comments[i]}"
            assert f"resolved only after" in comments[i], (
                f"Comment {i} is: {comments[i]}")

        # Add commit to mr with the same "bad" file - comments only for new bad words should be
        # added.
        updated_bad_open_source_commit = BAD_OPENSOURCE_COMMIT.copy()
        updated_bad_open_source_commit["sha"] = FILE_COMMITS_SHA["new_bad_dontreadme"]
        updated_bad_open_source_commit["files"] = {"open/dontreadme.md": {"is_new": True}}
        mr.commits_list.append(updated_bad_open_source_commit)
        mr._register_commit(updated_bad_open_source_commit)

        open_source_rule.execute(mr_manager)

        comments = mr.comments()
        assert len(comments) == 5, f"Got comments: {comments}"
        for i, bad_word in enumerate(['Copyrleft', 'shit', 'fuck', 'blya', 'hanwha']):
            assert f":{AwardEmojiManager.AUTOCHECK_FAILED_EMOJI}:" in comments[i], (
                f"Comment {i} is: {comments[i]}")
            assert bad_word in comments[i], f"Comment {i} is: {comments[i]}"
            assert f"resolved only after" in comments[i], (
                f"Comment {i} is: {comments[i]}")

    # Re-check files if the merge request target branch changed.
    @pytest.mark.parametrize("mr_state", [
        {"commits_list": [BAD_OPENSOURCE_COMMIT]},
    ])
    def test_re_check_after_mr_target_branch_changed(self, open_source_rule, mr, mr_manager):
        assert not open_source_rule.execute(mr_manager)
        assert not mr.blocking_discussions_resolved
        assert mr_manager._mr.get_approvers_count() == DEFAULT_REQUIRED_APPROVALS_COUNT + 1

        # Fix files in commit leaving the same sha. We emulate different changes when the user sets
        # the new target branch to the Merge Request.
        updated_bad_open_source_commit = DEFAULT_COMMIT.copy()
        updated_bad_open_source_commit["sha"] = BAD_OPENSOURCE_COMMIT["sha"]
        mr.commits_list = [updated_bad_open_source_commit]
        mr._register_commit(updated_bad_open_source_commit)
        mr.target_branch = "changed_branch"

        assert open_source_rule.execute(mr_manager)
        assert mr_manager._mr.get_approvers_count() == DEFAULT_REQUIRED_APPROVALS_COUNT + 1
