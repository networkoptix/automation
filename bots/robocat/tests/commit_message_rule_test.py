import pytest

from robocat.award_emoji_manager import AwardEmojiManager
from robocat.note import Note, MessageId
from automation_tools.tests.gitlab_constants import (
    GOOD_README_COMMIT_CHANGED_FILE,
    GOOD_README_COMMIT_NEW_FILE,
    GOOD_README_COMMIT_DELETED_FILE,
    DEFAULT_JIRA_ISSUE_KEY,
    FILE_COMMITS_SHA,
    OPEN_SOURCE_APPROVER_COMMON,
    OPEN_SOURCE_APPROVER_COMMON_2,
    OPEN_SOURCE_APPROVER_CLIENT,
    BAD_README_RAW_DATA)
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
    ])
    def test_not_applicable(self, commit_message_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert commit_message_rule.execute(mr_manager)

    @pytest.mark.parametrize("mr_state", [
        # Simple Merge Request containing a new open source file.
        {
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "blocking_discussions_resolved": True,
        },
        # Simple Merge Request containing a changed open source file.
        {
            "commits_list": [GOOD_README_COMMIT_CHANGED_FILE],
            "blocking_discussions_resolved": True,
        },
        # Simple Merge Request containing a deleted open source file.
        {
            "commits_list": [GOOD_README_COMMIT_DELETED_FILE],
            "blocking_discussions_resolved": True,
        },
    ])
    def test_commit_message_is_ok(self, commit_message_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert commit_message_rule.execute(mr_manager)

            assert mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            assert len(comments) == 1, f"Got comments: {comments}"
            assert f":{AwardEmojiManager.AUTOCHECK_OK_EMOJI}:" in comments[0], (
                f"Comment is: {comments[0]}")
            message_details = (
                f"<details><pre>{Note.ID_KEY}: {MessageId.CommitMessageIsOk.value}")
            assert message_details in comments[0], f"Comment is: {comments[0]}"

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

    @pytest.mark.parametrize(("mr_state", "expected_result", "expected_message_id"), [
        # Simple Merge Request containing a new open source file with a bad commit message.
        (
            {
                "commits_list": [{
                    "sha": f'{GOOD_README_COMMIT_NEW_FILE["sha"]}1',
                    "message": f"{DEFAULT_JIRA_ISSUE_KEY}: title\n\nchanges in copyright\ngpl",
                    "diffs": GOOD_README_COMMIT_NEW_FILE["diffs"],
                    "files": GOOD_README_COMMIT_NEW_FILE["files"],
                }],
                "blocking_discussions_resolved": True,
            },
            commit_message_rule().ExecutionResult.commit_message_not_ok,
            MessageId.BadCommitMessage,
        ),
        # Same as the previous but the author is an open source keeper.
        (
            {
                "commits_list": [{
                    "sha": f'{GOOD_README_COMMIT_NEW_FILE["sha"]}2',
                    "message": f"{DEFAULT_JIRA_ISSUE_KEY}: title\n\nchanges in copyright\ngpl",
                    "diffs": GOOD_README_COMMIT_NEW_FILE["diffs"],
                    "files": GOOD_README_COMMIT_NEW_FILE["files"],
                }],
                "author": {"username": OPEN_SOURCE_APPROVER_COMMON},
                "blocking_discussions_resolved": True,
            },
            commit_message_rule().ExecutionResult.merge_authorized,
            MessageId.BadCommitMessageByKeeper,
        ),
        # Same as the first case but some of the reviewers are open source keepers.
        (
            {
                "commits_list": [{
                    "sha": f'{GOOD_README_COMMIT_NEW_FILE["sha"]}3',
                    "message": f"{DEFAULT_JIRA_ISSUE_KEY}: title\n\nfix in copyright\nlicensing",
                    "diffs": GOOD_README_COMMIT_NEW_FILE["diffs"],
                    "files": GOOD_README_COMMIT_NEW_FILE["files"],
                }],
                "reviewers": [{"username": OPEN_SOURCE_APPROVER_COMMON_2}],
                "blocking_discussions_resolved": True,
            },
            commit_message_rule().ExecutionResult.commit_message_not_ok,
            MessageId.BadCommitMessage,
        ),
    ])
    def test_commit_message_is_not_ok(
            self, commit_message_rule, mr, mr_manager, expected_result, expected_message_id):
        reviewers_before = {r["username"] for r in mr.reviewers}
        authorized_approvers = {
            OPEN_SOURCE_APPROVER_COMMON, OPEN_SOURCE_APPROVER_COMMON_2,
            OPEN_SOURCE_APPROVER_CLIENT}
        is_author_keeper = mr.author["username"] in authorized_approvers

        for _ in range(2):  # State must not change after any number of rule executions.
            assert commit_message_rule.execute(mr_manager) == expected_result

            assert not mr.blocking_discussions_resolved

            approvers_was_set = False
            assignees = {a["username"] for a in mr.assignees}
            approvers = {r["username"] for r in mr.reviewers} | assignees
            if is_author_keeper:
                assert len(approvers) == 0, f"Got approvers: {approvers}"
            elif reviewers_before.intersection(authorized_approvers):
                assert len(approvers) == 1, f"Got approvers: {approvers}"
            else:
                assert len(approvers) == 2, f"Got approvers: {approvers}"
                approvers_was_set = True

            comments = mr.mock_comments()
            assert len(comments) == (3 if approvers_was_set else 2), f"Got comments: {comments}"
            for comment in comments[0:1]:
                assert f":{AwardEmojiManager.AUTOCHECK_FAILED_EMOJI}:" in comment, (
                    f"Comment is: {comment}")
                message_details = f"\n{Note.ID_KEY}: {expected_message_id.value}\n"
                assert message_details in comment, f"Comment is: {comment}"

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.
