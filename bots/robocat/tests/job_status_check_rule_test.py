## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import pytest

from robocat.award_emoji_manager import AwardEmojiManager
from robocat.note import NoteDetails, MessageId
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
    APIDOC_APPROVER,
    CODE_OWNER_1,
    CODE_OWNER_2,
    CODE_OWNER_3,
    UNIVERSAL_APPROVER,
    DEFAULT_REQUIRED_APPROVALS_COUNT,
    MULTIPLE_KEEPERS_COMMIT_1,
    MULTIPLE_KEEPERS_COMMIT_2,
    MULTIPLE_KEEPERS_COMMIT_3,
    APIDOC_INFO_CHANGED_COMMIT,
    DEFAULT_USER)
from automation_tools.tests.mocks.file import (
    GOOD_README_RAW_DATA, BAD_README_RAW_DATA_2, GOOD_CPP_RAW_DATA)
from automation_tools.tests.mocks.git_mocks import random_sha
from tests.fixtures import *


class TestJobStatusCheckRule:
    @pytest.mark.parametrize("mr_state", [
        # The MR without open-source files (no check job in the pipeline list).
        {
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["no_open_source_files"],
                "message": "msg",
            }],
            "pipelines_list": [(
                FILE_COMMITS_SHA["no_open_source_files"],
                "success",
                [],
            )],
        },
    ])
    def test_not_applicable(self, job_status_rule, mr, mr_manager):
        for _ in range(2):  # The state must not change after any number of rule executions.
            assert job_status_rule.execute(mr_manager)

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
        # Non-follow-up Merge Request with new files.
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
            "assignees": [],
        },
    ])
    def test_set_open_source_approvers(self, job_status_rule, mr, mr_manager):
        reviewers_before = {r["username"] for r in mr.reviewers}
        approvers_before = (
            {a["username"] for a in mr.assignees} | reviewers_before | set([mr.author["username"]])
        )
        authorized_approvers = {
            OPEN_SOURCE_APPROVER_COMMON,
            OPEN_SOURCE_APPROVER_COMMON_2,
            OPEN_SOURCE_APPROVER_CLIENT,
        }

        for _ in range(2):  # The state must not change after any number of rule executions.
            assert not job_status_rule.execute(mr_manager)

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
        {
            "commits_list": [APIDOC_INFO_CHANGED_COMMIT],
            "assignees": [{"username": "user1"}],
            "pipelines_list": [(
                GOOD_README_COMMIT_NEW_FILE["sha"],
                "success",
                [("apidoc:check", "failed")],
            )],
        },
    ])
    def test_set_apidoc_approvers(self, job_status_rule, mr, mr_manager):
        for _ in range(2):  # The state must not change after any number of rule executions.
            assert not job_status_rule.execute(mr_manager)

            assignees = {a["username"] for a in mr.assignees}
            assert APIDOC_APPROVER in assignees, (
                f"Authorized approver(s) not assigned: {assignees}")

    @pytest.mark.parametrize(("mr_state", "expected_approvers"), [
        # File changed in the directory for wich the first code owner is responsible.
        [{
            "commits_list": [
                {
                    "sha": random_sha(),
                    "message": f"VMS-1: some title\nsome msg",
                    "files": {
                        "dir1/somefile.cpp": {
                            "is_new": False, "is_deleted": False, "raw_data": "",
                        },
                    },
                },
            ],
            "assignees": [{"username": "user1"}],
            "pipelines_list": [(
                random_sha(), "success", [("code-owner-approval:check", "failed")],
            )],
        }, {CODE_OWNER_1, "user1"}],
        # File added to the directory for wich the first code owner is responsible.
        [{
            "commits_list": [
                {
                    "sha": random_sha(),
                    "message": f"VMS-1: some title\nsome msg",
                    "files": {
                        "dir1/somefile.cpp": {
                            "is_new": True, "is_deleted": False, "raw_data": "",
                        },
                    },
                },
            ],
            "assignees": [{"username": "user1"}],
            "pipelines_list": [(
                random_sha(), "success", [("code-owner-approval:check", "failed")],
            )],
        }, {CODE_OWNER_1, "user1"}],
        # File removed from the directory for wich the first code owner is responsible.
        [{
            "commits_list": [
                {
                    "sha": random_sha(),
                    "message": f"VMS-1: some title\nsome msg",
                    "files": {
                        "dir1/somefile.cpp": {
                            "is_new": False, "is_deleted": True, "raw_data": "",
                        },
                    },
                },
            ],
            "assignees": [{"username": "user1"}],
            "pipelines_list": [(
                random_sha(), "success", [("code-owner-approval:check", "failed")],
            )],
        }, {CODE_OWNER_1, "user1"}],
        # File changed in the directory for wich the second and third code owner are responsible.
        [{
            "commits_list": [
                {
                    "sha": random_sha(),
                    "message": f"VMS-1: some title\nsome msg",
                    "files": {
                        "dir2/somefile.cpp": {
                            "is_new": False, "is_deleted": False, "raw_data": "",
                        },
                    },
                },
            ],
            "assignees": [{"username": "user1"}],
            "pipelines_list": [(
                random_sha(), "success", [("code-owner-approval:check", "failed")],
            )],
        }, {CODE_OWNER_2, CODE_OWNER_3, "user1"}],
        # Files changed in two directories. One of the approvers is common for both directories.
        [{
            "commits_list": [
                {
                    "sha": random_sha(),
                    "message": f"VMS-1: some title\nsome msg",
                    "files": {
                        "dir2/somefile.cpp": {
                            "is_new": False, "is_deleted": False, "raw_data": "",
                        },
                        "dir3/somefile.cpp": {
                            "is_new": False, "is_deleted": False, "raw_data": "",
                        },
                    },
                },
            ],
            "assignees": [{"username": "user1"}],
            "pipelines_list": [(
                random_sha(), "success", [("code-owner-approval:check", "failed")],
            )],
        }, {CODE_OWNER_2, CODE_OWNER_3, "user1"}],
        # Files changed in two directories. No common code owners.
        [{
            "commits_list": [
                {
                    "sha": random_sha(),
                    "message": f"VMS-1: some title\nsome msg",
                    "files": {
                        "dir1/somefile.cpp": {
                            "is_new": False, "is_deleted": False, "raw_data": "",
                        },
                        "dir3/somefile.cpp": {
                            "is_new": False, "is_deleted": False, "raw_data": "",
                        },
                    },
                },
            ],
            "assignees": [{"username": "user1"}],
            "pipelines_list": [(
                random_sha(), "success", [("code-owner-approval:check", "failed")],
            )],
        }, {CODE_OWNER_1, CODE_OWNER_3, "user1"}],
        # Files changed in the directory for wich one of its code owners is already assigned.
        [{
            "commits_list": [
                {
                    "sha": random_sha(),
                    "message": f"VMS-1: some title\nsome msg",
                    "files": {
                        "dir2/somefile.cpp": {
                            "is_new": False, "is_deleted": False, "raw_data": "",
                        },
                    },
                },
            ],
            "assignees": [{"username": CODE_OWNER_2}],
            "pipelines_list": [(
                random_sha(), "success", [("code-owner-approval:check", "failed")],
            )],
        }, {CODE_OWNER_2}],
    ])
    def test_set_code_owner_approvers(self, job_status_rule, mr, mr_manager, expected_approvers):
        for _ in range(2):  # The state must not change after any number of rule executions.
            assert not job_status_rule.execute(mr_manager)

            assignees = {a["username"] for a in mr.assignees}
            assert expected_approvers == assignees, (
                f"Authorized approver(s) not assigned: {assignees}")

    @pytest.mark.parametrize(("mr_state", "expected_approvers"), [
        # The MR author is not a keeper.
        [{
            "commits_list": [MULTIPLE_KEEPERS_COMMIT_1],
            "assignees": [{"username": "user1"}],
            "pipelines_list": [(
                MULTIPLE_KEEPERS_COMMIT_1["sha"],
                "success",
                [
                    ("apidoc:check", "failed"),
                    ("new-open-source-files:check", "failed"),
                    ("code-owner-approval:check", "failed"),
                ],
            )],
        }, {
            OPEN_SOURCE_APPROVER_COMMON,
            OPEN_SOURCE_APPROVER_COMMON_2,
            APIDOC_APPROVER,
            CODE_OWNER_1,
            "user1",
        }],
        # The MR author is an open-source keeper.
        [{
            "commits_list": [MULTIPLE_KEEPERS_COMMIT_2],
            "assignees": [{"username": "user1"}],
            "author": {"username": OPEN_SOURCE_APPROVER_COMMON, "name": DEFAULT_USER["name"]},
            "pipelines_list": [(
                MULTIPLE_KEEPERS_COMMIT_2["sha"],
                "success",
                [
                    ("apidoc:check", "failed"),
                    ("new-open-source-files:check", "failed"),
                    ("code-owner-approval:check", "failed"),
                ],
            )],
        }, {APIDOC_APPROVER, CODE_OWNER_1, "user1"}],
    ])
    def test_set_approvers_for_multiple_rules(
            self, job_status_rule, mr, mr_manager, expected_approvers):
        for _ in range(2):  # The state must not change after any number of rule executions.
            assert not job_status_rule.execute(mr_manager)

            assignees = {a["username"] for a in mr.assignees}
            assert expected_approvers == assignees, (
                f"Authorized approver(s) not assigned: {assignees}")

    @pytest.mark.parametrize((
        "mr_state",
        "open_source_approve_ruleset",
        "apidoc_approve_ruleset",
        "code_owner_approve_ruleset",
        "expected_approvers",
        "expected_result"), [
        # The MR author is not a keeper.
        [{
            "commits_list": [MULTIPLE_KEEPERS_COMMIT_3],
            "assignees": [{"username": "user1"}],
            "pipelines_list": [(
                MULTIPLE_KEEPERS_COMMIT_3["sha"],
                "success",
                [
                    ("apidoc:check", "failed"),
                    ("new-open-source-files:check", "failed"),
                    ("code-owner-approval:check", "failed"),
                ],
            )],
        }, {
            "relevance_checker": "is_file_open_sourced",
            "rules": [{
                "patterns": ["open_candidate/.+"],
                "approvers": [OPEN_SOURCE_APPROVER_COMMON, UNIVERSAL_APPROVER],
            }],
        }, {
            "relevance_checker": "does_file_diff_contain_apidoc_changes",
            "rules": [{"patterns": [".+"], "approvers": [APIDOC_APPROVER, UNIVERSAL_APPROVER]}],
        }, {
            "relevance_checker": "match_name_pattern",
            "rules": [{"patterns": ["dir1/.+"], "approvers": [CODE_OWNER_1, UNIVERSAL_APPROVER]}],
        }, {
            UNIVERSAL_APPROVER,
            APIDOC_APPROVER,
            OPEN_SOURCE_APPROVER_COMMON,
            CODE_OWNER_1,
            "user1",
        }, False],
        # Open-source approver is an assignee.
        [{
            "commits_list": [MULTIPLE_KEEPERS_COMMIT_3],
            "assignees": [{"username": OPEN_SOURCE_APPROVER_COMMON}],
            "author": {"username": OPEN_SOURCE_APPROVER_COMMON, "name": DEFAULT_USER["name"]},
            "pipelines_list": [(
                MULTIPLE_KEEPERS_COMMIT_3["sha"],
                "success",
                [
                    ("apidoc:check", "failed"),
                    ("new-open-source-files:check", "failed"),
                    ("code-owner-approval:check", "failed"),
                ],
            )],
        }, {
            "relevance_checker": "is_file_open_sourced",
            "rules": [{
                "patterns": ["open_candidate/.+"],
                "approvers": [OPEN_SOURCE_APPROVER_COMMON, UNIVERSAL_APPROVER],
            }],
        }, {
            "relevance_checker": "does_file_diff_contain_apidoc_changes",
            "rules": [{"patterns": [".+"], "approvers": [APIDOC_APPROVER, UNIVERSAL_APPROVER]}],
        }, {
            "relevance_checker": "match_name_pattern",
            "rules": [{"patterns": ["dir1/.+"], "approvers": [CODE_OWNER_1, UNIVERSAL_APPROVER]}],
        }, {
            UNIVERSAL_APPROVER, APIDOC_APPROVER, CODE_OWNER_1, OPEN_SOURCE_APPROVER_COMMON,
        }, False],
        # The MR author is an open-source approver.
        [{
            "commits_list": [MULTIPLE_KEEPERS_COMMIT_3],
            "assignees": [{"username": "user1"}],
            "author": {"username": OPEN_SOURCE_APPROVER_COMMON, "name": DEFAULT_USER["name"]},
            "pipelines_list": [(
                MULTIPLE_KEEPERS_COMMIT_3["sha"],
                "success",
                [
                    ("apidoc:check", "failed"),
                    ("new-open-source-files:check", "failed"),
                    ("code-owner-approval:check", "failed"),
                ],
            )],
        }, {
            "relevance_checker": "is_file_open_sourced",
            "rules": [{
                "patterns": ["open_candidate/.+"],
                "approvers": [OPEN_SOURCE_APPROVER_COMMON, UNIVERSAL_APPROVER],
            }],
        }, {
            "relevance_checker": "does_file_diff_contain_apidoc_changes",
            "rules": [{"patterns": [".+"], "approvers": [APIDOC_APPROVER, UNIVERSAL_APPROVER]}],
        }, {
            "relevance_checker": "match_name_pattern",
            "rules": [{"patterns": ["dir1/.+"], "approvers": [CODE_OWNER_1, UNIVERSAL_APPROVER]}],
        }, {UNIVERSAL_APPROVER, APIDOC_APPROVER, CODE_OWNER_1, "user1", }, False],
        # The universal approver is an assignee.
        [{
            "commits_list": [MULTIPLE_KEEPERS_COMMIT_3],
            "assignees": [{"username": UNIVERSAL_APPROVER}],
            "pipelines_list": [(
                MULTIPLE_KEEPERS_COMMIT_3["sha"],
                "success",
                [
                    ("apidoc:check", "failed"),
                    ("new-open-source-files:check", "failed"),
                    ("code-owner-approval:check", "failed"),
                ],
            )],
        }, {
            "relevance_checker": "is_file_open_sourced",
            "rules": [{
                "patterns": ["open_candidate/.+"],
                "approvers": [OPEN_SOURCE_APPROVER_COMMON, UNIVERSAL_APPROVER],
            }],
        }, {
            "relevance_checker": "does_file_diff_contain_apidoc_changes",
            "rules": [{"patterns": [".+"], "approvers": [APIDOC_APPROVER, UNIVERSAL_APPROVER]}],
        }, {
            "relevance_checker": "match_name_pattern",
            "rules": [{"patterns": ["dir1/.+"], "approvers": [CODE_OWNER_1, UNIVERSAL_APPROVER]}],
        }, {UNIVERSAL_APPROVER}, False],
        # The MR author is a universal approver.
        [{
            "commits_list": [MULTIPLE_KEEPERS_COMMIT_3],
            "author": {"username": UNIVERSAL_APPROVER, "name": DEFAULT_USER["name"]},
            "assignees": [{"username": "user1"}],
            "pipelines_list": [(
                MULTIPLE_KEEPERS_COMMIT_3["sha"],
                "success",
                [
                    ("apidoc:check", "failed"),
                    ("new-open-source-files:check", "failed"),
                    ("code-owner-approval:check", "failed"),
                ],
            )],
        }, {
            "relevance_checker": "is_file_open_sourced",
            "rules": [{
                "patterns": ["open_candidate/.+"],
                "approvers": [OPEN_SOURCE_APPROVER_COMMON, UNIVERSAL_APPROVER],
            }],
        }, {
            "relevance_checker": "does_file_diff_contain_apidoc_changes",
            "rules": [{"patterns": [".+"], "approvers": [APIDOC_APPROVER, UNIVERSAL_APPROVER]}],
        }, {
            "relevance_checker": "match_name_pattern",
            "rules": [{"patterns": ["dir1/.+"], "approvers": [CODE_OWNER_1, UNIVERSAL_APPROVER]}],
        }, {"user1"}, True],
    ])
    def test_set_universal_approver(
            self, job_status_rule, mr, mr_manager, expected_approvers, expected_result):
        for _ in range(2):  # The state must not change after any number of rule executions.
            assert bool(job_status_rule.execute(mr_manager)) == expected_result

            assignees = {a["username"] for a in mr.assignees}
            assert expected_approvers == assignees, (
                f"Authorized approver(s) not assigned: {assignees}")

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
    def test_good_new_files_comments(self, job_status_rule, mr, mr_manager):
        for _ in range(2):  # The state must not change after any number of rule executions.
            assert not job_status_rule.execute(mr_manager)

            assert mr.blocking_discussions_resolved

            comments = mr.mock_comments()

            assert len(comments) == 2, f"Got comments: {comments}"

            is_manual_check_emoji_in_comment = (
                f":{AwardEmojiManager.NEED_MANUAL_CHECK_EMOJI}:" in comments[0])
            is_message_id_right = (
                f"{NoteDetails._ID_KEY}: {MessageId.JobStatusCheckNeedsApproval.value}"
                in comments[0])
            assert is_manual_check_emoji_in_comment and is_message_id_right, (
                f"First comment is: {comments[0]}")

            assert f"Update assignee list" in comments[1], (f"Last comment is: {comments[1]}")

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
        # Has new files in non-follow-up Merge Request, but the author is an authorized approver.
        {
            "blocking_discussions_resolved": True,
            "commits_list": [GOOD_README_COMMIT_NEW_FILE],
            "author": {"username": OPEN_SOURCE_APPROVER_COMMON, "name": DEFAULT_USER["name"]},
            "pipelines_list": [(
                GOOD_README_COMMIT_NEW_FILE["sha"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "failed")],
            )],
        },
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
    def test_no_new_files(self, job_status_rule, mr, mr_manager):
        for _ in range(2):  # The state must not change after any number of rule executions.
            assert job_status_rule.execute(mr_manager)
            assert mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            assert len(comments) == 0, f"Got comments: {comments}"

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

    @pytest.mark.parametrize("mr_state", [
        # Bad changes in the new file of the non-follow-up Merge Request.
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
    def test_bad_changes_new_files(self, job_status_rule, mr, mr_manager):
        for _ in range(2):  # The state must not change after any number of rule executions.
            assert not job_status_rule.execute(mr_manager)
            assert mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            assert len(comments) == 2, f"Got comments: {comments}"
            assert f":{AwardEmojiManager.NEED_MANUAL_CHECK_EMOJI}:" in comments[0], (
                f"First comment is: {comments[0]}")
            message_details = (
                f"{NoteDetails._ID_KEY}: {MessageId.JobStatusCheckNeedsApproval.value}")
            assert message_details in comments[0], f"First comment is: {comments[0]}"
            assert f"Update assignee list" in comments[1], f"Last comment is: {comments[1]}"

            mr_manager._mr.load_discussions()  # Update notes in the MergeRequest object.

    @pytest.mark.parametrize("mr_state", [
        # Merging is allowed if everything is good and the Merge Request is approved by an eligible
        # user.
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
        # Merging is allowed even if there are bad files, but the Merge request is approved by an
        # eligible user.
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
    def test_merge_allowed(self, job_status_rule, mr, mr_manager):
        assert job_status_rule.execute(mr_manager)

    # Don't add comments for the errors already found after new commits are added to the Merge
    # Request.
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
    def test_update_comments_for_found_errors(self, job_status_rule, mr, mr_manager):
        def add_commit_and_execute_rule(sha, files, has_errors, has_new_files):
            # Add a new commit.
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
            job_status_rule.execute(mr_manager)

        expected_comments_number = 0

        job_status_rule.execute(mr_manager)
        comments = mr.mock_comments()
        assert len(comments) == expected_comments_number, f"Got comments: {comments}"

        # Add a commit to the Merge Request with a "good" file - now we have new files in the MR,
        # so it must be checked manually.
        expected_comments_number += 2

        add_commit_and_execute_rule(
            sha=FILE_COMMITS_SHA["good_opensource_file"],
            files={"open/good.cpp": {"is_new": True, "raw_data": GOOD_CPP_RAW_DATA}},
            has_errors=True,
            has_new_files=True)

        comments = mr.mock_comments()
        assert len(comments) == expected_comments_number, f"Got comments: {comments}"
        assert f":{AwardEmojiManager.NEED_MANUAL_CHECK_EMOJI}:" in comments[-2], (
            f"Unexpected comment: {comments[-2]}")
        assert f":{AwardEmojiManager.NOTIFICATION_EMOJI}:" in comments[-1], (
            f"Unexpected comment: {comments[-1]}")

        # Add a commit to the MR with the same "bad" file - no comments should be added.
        add_commit_and_execute_rule(
            sha=FILE_COMMITS_SHA["new_bad_dontreadme"],
            files={"open/dontreadme.md": {"is_new": True, "raw_data": BAD_README_RAW_DATA_2}},
            has_errors=True,
            has_new_files=True)

        comments = mr.mock_comments()
        assert len(comments) == expected_comments_number, f"Got comments: {comments}"

        # Add a commit to the Merge Request with the same file, but without bad words - no new
        # commits should be added.
        add_commit_and_execute_rule(
            sha=FILE_COMMITS_SHA["good_dontreadme"],
            files={"open/dontreadme.md": {"is_new": True, "raw_data": GOOD_README_RAW_DATA}},
            has_errors=False,
            has_new_files=True)

        comments = mr.mock_comments()
        assert len(comments) == expected_comments_number, f"Got comments: {comments}"
        assert f":{AwardEmojiManager.NEED_MANUAL_CHECK_EMOJI}:" in comments[-2], (
            f"Unexpected comment: {comments[-2]}")

        # Add a commit to the Merge Request removing the new file - no new commits should be
        # added.
        add_commit_and_execute_rule(
            sha=FILE_COMMITS_SHA["opensource_deleted_new_file"],
            files={"open/good.cpp.md": {"is_deleted": True, "raw_data": GOOD_README_RAW_DATA}},
            has_errors=False,
            has_new_files=False)

        comments = mr.mock_comments()
        assert len(comments) == expected_comments_number, f"Got comments: {comments}"
        assert f":{AwardEmojiManager.NEED_MANUAL_CHECK_EMOJI}:" in comments[-2], (
            f"Unexpected comment: {comments[-2]}")

    # Re-check the files if the Merge Request target branch has changed.
    @pytest.mark.parametrize("mr_state", [
        {
            "commits_list": [BAD_OPENSOURCE_COMMIT],
            "pipelines_list": [(
                BAD_OPENSOURCE_COMMIT["sha"],
                "success",
                [("open-source:check", "success"), ("new-open-source-files:check", "success")],
            )],
        },
    ])
    def test_re_check_after_mr_target_branch_changed(self, job_status_rule, mr, mr_manager):
        initial_approvers_count = mr_manager._mr.get_approvers_count()
        assert job_status_rule.execute(mr_manager)
        assert mr.blocking_discussions_resolved
        assert mr_manager._mr.get_approvers_count() == initial_approvers_count

        # Fix files in the commit, keeping the same sha. We emulate different changes when the user
        # sets a new target branch to the Merge Request.
        updated_bad_open_source_commit = DEFAULT_COMMIT.copy()
        updated_bad_open_source_commit["sha"] = BAD_OPENSOURCE_COMMIT["sha"]
        updated_bad_open_source_commit["files"] = {
            "open/dontreadme.md": {"is_new": True, "raw_data": GOOD_README_RAW_DATA},
        }
        mr.commits_list = [updated_bad_open_source_commit]
        mr._register_commit(updated_bad_open_source_commit)
        mr.add_mock_pipeline({
            "jobs": {("open-source:check", "success"), ("new-open-source-files:check", "failed")},
        })
        mr_manager._get_last_pipeline_by_status.cache_clear()
        mr.target_branch = "changed_branch"

        assert not job_status_rule.execute(mr_manager)
        assert mr_manager._mr.get_approvers_count() == initial_approvers_count + 1
