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
            "assignees": [{"username": "user1"}]
        },
        {
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "assignees": [{"username": "user1"}, {"username": OPEN_SOURCE_APPROVER_COMMON}]
        },
        {
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "reviewers": [{"username": OPEN_SOURCE_APPROVER_COMMON}],
            "assignees": [{"username": "user1"}]
        },
        {
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "reviewers": [{"username": OPEN_SOURCE_APPROVER_COMMON_2}],
            "assignees": [{"username": "user1"}]
        },
        {
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": "msg",
                "diffs": [],
                "files": {"open/unknown_approver_prefix_dontreadme.md": {
                    "is_new": True, "raw_data": GOOD_README_RAW_DATA
                }},
            }],
            "mock_huge_mr": True,
            "assignees": [{"username": "user1"}]
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
            "mock_huge_mr": False,
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

            approvers = (
                {r["username"] for r in mr.reviewers} | assignees | set([mr.author["username"]]))
            if mr.mock_huge_mr:
                assert len(approvers) == 4, f"Got approvers: {approvers}"
            elif approvers_before.intersection(authorized_approvers):
                assert len(approvers) == 2, f"Got approvers: {approvers}"
            else:
                assert len(approvers) == 3, f"Got approvers: {approvers}"

            if approvers_before.intersection(authorized_approvers):
                assert mr_manager._mr.get_approvers_count() == DEFAULT_REQUIRED_APPROVALS_COUNT
            else:
                assert mr_manager._mr.get_approvers_count() == DEFAULT_REQUIRED_APPROVALS_COUNT + 1

    @pytest.mark.parametrize("mr_state", [
        {
            "blocking_discussions_resolved": True,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "mock_huge_mr": True,
        },
    ])
    def test_cannot_check_files(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not open_source_rule.execute(mr_manager)

            assert not mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            assert len(comments) == 2, f"Got comments: {comments}"
            assert f"Update assignee list" in comments[0], (
                f"First comment is: {comments[0]}")
            assert f":{AwardEmojiManager.AUTOCHECK_IMPOSSIBLE_EMOJI}:" in comments[1], (
                f"Last comment is: {comments[1]}")
            message_details = (
                f"<details><pre>{Note.ID_KEY}: {MessageId.OpenSourceHugeDiffCallKeeper.value}")
            assert message_details in comments[1], f"Last comment is: {comments[1]}"

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

    @pytest.mark.parametrize("mr_state", [
        # Simple Merge Request with "good" changes in a new file.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
        },
    ])
    def test_files_are_ok_comments(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not open_source_rule.execute(mr_manager)

            assert not mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            assert len(comments) == 2, f"Got comments: {comments}"
            assert f"Update assignee list" in comments[0], (
                f"First comment is: {comments[0]}")
            assert f":{AwardEmojiManager.AUTOCHECK_OK_EMOJI}:" in comments[1], (
                f"Last comment is: {comments[1]}")
            message_details = (
                f"<details><pre>{Note.ID_KEY}: {MessageId.OpenSourceNoProblemNeedApproval.value}")
            assert message_details in comments[1], f"Last comment is: {comments[1]}"

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

    @pytest.mark.parametrize("mr_state", [
        # Simple Merge Request with "good" changes in an old file.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [GOOD_README_COMMIT_CHANGED_FILE],
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
        },
    ])
    def test_files_dont_need_manual_check(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert open_source_rule.execute(mr_manager)

            assert mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            assert len(comments) == 1, f"Got comments: {comments}"
            assert f":{AwardEmojiManager.AUTOCHECK_OK_EMOJI}:" in comments[0], (
                f"Last comment is: {comments[0]}")

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

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
            "commits_list": [BAD_OPENSOURCE_COMMIT],
        },
        # Unknown file type.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["opensource_unknown_file"],
                "message": "msg1",
                "diffs": [],
                "files": {"open/badtype.foobar": {"is_new": True, "raw_data": ""}},
            }],
        },
        # New file is in the follow-up Merge Request.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["opensource_unknown_file"],
                "message": "msg1",
                "diffs": [],
                "files": {"open/badtype.foobar": {"is_new": True, "raw_data": ""}},
            }],
        },
    ])
    def test_files_are_not_ok_comments(self, open_source_rule, mr, mr_manager):
        has_new_files = next(iter(mr.commits_list[0]["files"].values()))["is_new"]
        file_type_is_unknown = (
            mr.commits_list[0]["sha"] == FILE_COMMITS_SHA["opensource_unknown_file"])

        for _ in range(2):  # State must not change after any number of rule executions.
            assert not open_source_rule.execute(mr_manager)
            assert not mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            if has_new_files:
                check_phrase = "must be approved"
                comments_number = 5 if not file_type_is_unknown else 2
            else:
                check_phrase = "Fix all the issues, or ask"
                comments_number = 4
            assert len(comments) == comments_number, f"Got comments: {comments}"
            for i, comment in enumerate(comments):
                if has_new_files and i == 0:
                    assert f"Update assignee list" in comments[0], (
                        f"First comment is: {comments[0]}")
                    continue
                assert f":{AwardEmojiManager.AUTOCHECK_FAILED_EMOJI}:" in comment, (
                    f"Comment {i} is: {comment}")
                assert check_phrase in comment, f"Comment {i} is: {comment}"
                for error_token in ["fuck", "blya", "shit", "Copyrleft", "Unknown file type"]:
                    if error_token in comment:
                        break
                else:
                    assert False, f"Unexpected comment {comment}"

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

    @pytest.mark.parametrize("mr_state", [
        # Merge allowed if everything is good and merge request approved by eligible user
        {
            "blocking_discussions_resolved": True,
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
        },
        # Merge allowed even if there are bad files, but merge request approved by an eligible
        # user.
        {
            "blocking_discussions_resolved": True,
            "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
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
        def check_comments(
                bad_words: List[Tuple[str, bool]],
                expected_comments_number: int,
                is_resolved: bool = False):
            comments = mr.mock_comments()
            if is_resolved:
                error_comments = comments[:-1]
                ok_comment = comments[-1]
            else:
                error_comments = comments
                ok_comment = None

            assert len(error_comments) == expected_comments_number, f"Got comments: {comments}"

            has_approvers_added_comment = expected_comments_number > len(bad_words)
            for i, comment in enumerate(error_comments):
                if has_approvers_added_comment and "Update assignee list" in comment:
                    assert f":{AwardEmojiManager.NOTIFICATION_EMOJI}:" in comment, (
                        f"Comment {i} is: {comment}")
                    continue
                assert f":{AwardEmojiManager.AUTOCHECK_FAILED_EMOJI}:" in comment, (
                    f"Comment {i} is: {comment}")
                for bad_word_tuples in bad_words:
                    bad_word, has_new_files = bad_word_tuples
                    if bad_word not in comment:
                        continue

                    if has_new_files:
                        check_phrase = "must be approved"
                    else:
                        check_phrase = "Fix all the issues, or ask"
                    assert check_phrase in comment, (
                        f"Comment {i} is: {comment}")

                    break
                else:
                    assert False, f"Unexpected comment {comment}"

            if ok_comment:
                assert f":{AwardEmojiManager.AUTOCHECK_OK_EMOJI}:" in ok_comment, (
                    f"Last comment is: {ok_comment}")

        expected_comments_number = 4

        open_source_rule.execute(mr_manager)

        check_comments(
            [('fuck', False), ('blya', False), ('shit', False), ('Copyrleft', False)],
            expected_comments_number=expected_comments_number)
        mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

        # Add commit to the Merge Request with a "good" file - now we have new files in MR, so it
        # must be checked manually.
        good_commit = {
            "sha": FILE_COMMITS_SHA["good_opensource_file"],
            "message": "msg",
            "diffs": [],
            "files": {"open/good.cpp": {"is_new": True, "raw_data": GOOD_CPP_RAW_DATA}},
        }
        mr.add_mock_commit(good_commit)
        expected_comments_number += 1  # New file added.

        open_source_rule.execute(mr_manager)

        check_comments(
            [('fuck', False), ('blya', False), ('shit', False), ('Copyrleft', False)],
            expected_comments_number=expected_comments_number)
        mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

        # Add commit to mr with the same "bad" file - comments only for new bad words should be
        # added.
        updated_bad_open_source_commit = BAD_OPENSOURCE_COMMIT.copy()
        updated_bad_open_source_commit["sha"] = FILE_COMMITS_SHA["new_bad_dontreadme"]
        updated_bad_open_source_commit["files"] = {
            "open/dontreadme.md": {"is_new": True, "raw_data": BAD_README_RAW_DATA_2}}
        mr.add_mock_commit(updated_bad_open_source_commit)
        expected_comments_number += 1  # Error added.

        open_source_rule.execute(mr_manager)

        check_comments([
            ('fuck', False), ('blya', False), ('shit', False), ('Copyrleft', False),
            ('hanwha', True)],
            expected_comments_number=expected_comments_number)
        mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

        # Add commit to the Merge Request with the same file, but without bad words - "everything
        # is ok" comment should be added.
        updated_bad_open_source_commit = BAD_OPENSOURCE_COMMIT.copy()
        updated_bad_open_source_commit["sha"] = FILE_COMMITS_SHA["good_dontreadme"]
        updated_bad_open_source_commit["files"] = {
            "open/dontreadme.md": {"is_new": True, "raw_data": GOOD_README_RAW_DATA}}
        mr.add_mock_commit(updated_bad_open_source_commit)

        open_source_rule.execute(mr_manager)

        check_comments([
            ('fuck', False), ('blya', False), ('shit', False), ('Copyrleft', False),
            ('hanwha', True)],
            expected_comments_number=expected_comments_number,
            is_resolved=True)

    # Re-check files if the merge request target branch changed.
    @pytest.mark.parametrize("mr_state", [
        {"commits_list": [BAD_OPENSOURCE_COMMIT]},
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
        mr.target_branch = "changed_branch"

        assert open_source_rule.execute(mr_manager)
        assert mr_manager._mr.get_approvers_count() == initial_approvers_count

    @pytest.mark.parametrize("mr_state", [
        {
            "blocking_discussions_resolved": True,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "author": {"username": OPEN_SOURCE_APPROVER_COMMON},
        },
    ])
    def test_files_are_ok_comments_author_is_approver(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert open_source_rule.execute(mr_manager)
            assert mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            assert len(comments) == 1, f"Got comments: {comments}"
            assert f":{AwardEmojiManager.AUTOCHECK_OK_EMOJI}:" in comments[0], (
                f"Last comment is: {comments[0]}")

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

    @pytest.mark.parametrize("mr_state", [
        # File is in the "open" directory.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [BAD_OPENSOURCE_COMMIT],
            "author": {"username": OPEN_SOURCE_APPROVER_COMMON},
        },
        # File is in the "open_candidate" directory.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [BAD_OPENCANDIDATE_COMMIT],
            "author": {"username": OPEN_SOURCE_APPROVER_COMMON},
        },
        # Bad file is not new.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [BAD_OPENSOURCE_COMMIT],
            "author": {"username": OPEN_SOURCE_APPROVER_COMMON},
        },
        # Unknown file type.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["opensource_unknown_file"],
                "message": "msg1",
                "diffs": [],
                "files": {"open/badtype.foobar": {"is_new": True, "raw_data": ""}},
            }],
            "author": {"username": OPEN_SOURCE_APPROVER_COMMON},
        },
    ])
    def test_files_are_not_ok_comments_author_is_approver(self, open_source_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert open_source_rule.execute(mr_manager)
            assert not mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            file_type_is_unknown = (
                mr.commits_list[0]["sha"] == FILE_COMMITS_SHA["opensource_unknown_file"])
            expected_comments_count = 1 if file_type_is_unknown else 4
            assert len(comments) == expected_comments_count, f"Got comments: {comments}"
            for i, comment in enumerate(comments):
                assert f":{AwardEmojiManager.AUTOCHECK_FAILED_EMOJI}:" in comment, (
                    f"Comment {i} is: {comment}")
                assert "check carefully all the issues" in comment, f"Comment {i} is: {comment}"
                for error_token in ["fuck", "blya", "shit", "Copyrleft", "Unknown file type"]:
                    if error_token in comment:
                        break
                else:
                    assert False, f"Unexpected comment {comment}"

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.
