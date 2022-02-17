import pytest
import re
import uuid

from robocat.award_emoji_manager import AwardEmojiManager
from robocat.note import Note, MessageId
from automation_tools.tests.gitlab_constants import FILE_COMMITS_SHA
from automation_tools.tests.mocks.file import (
    NX_SUBMODULE_GOOD_RAW_DATA,
    NX_SUBMODULE_BAD_RAW_DATA_1,
    NX_SUBMODULE_BAD_RAW_DATA_2,
    NX_SUBMODULE_BAD_RAW_DATA_3,
    BAD_README_RAW_DATA)
from tests.fixtures import *


class TestNxSubmoduleCheckRule:
    @pytest.mark.parametrize(("mr_state", "message_id", "is_resolved"), [
        # MR without changes in submodules.
        ({
            "commits_list": [{
                "sha": f"{FILE_COMMITS_SHA['nx_submodule_changes_base']}0",
                "message": "msg0",
                "diffs": [],
                "files": {"dontreadme.md": {"is_new": True, "raw_data": BAD_README_RAW_DATA}},
            }]
        }, MessageId.NxSubmoduleCheckPassed.value, True),
        # MR with valid changes in submodules.
        ({
            "commits_list": [{
                "sha": f"{FILE_COMMITS_SHA['nx_submodule_changes_base']}1",
                "message": "msg1",
                "diffs": [],
                "files": {
                    "conan_profiles/1.txt": {"raw_data": "file 1\n"},
                    "conan_profiles/_nx_submodule": {"raw_data": NX_SUBMODULE_GOOD_RAW_DATA},
                },
            }],
        }, MessageId.NxSubmoduleCheckPassed.value, True),
        # MR with deleted file which is not present in the submodule.
        ({
            "blocking_discussions_resolved": True,
            "commits_list": [{
                "sha": f"{FILE_COMMITS_SHA['nx_submodule_changes_base']}2",
                "message": "msg2",
                "diffs": [],
                "files": {
                    "conan_profiles/1/nonexistent": {"raw_data": "", "is_deleted": True},
                    "conan_profiles/_nx_submodule": {"raw_data": NX_SUBMODULE_GOOD_RAW_DATA},
                },
            }],
        }, MessageId.NxSubmoduleCheckPassed.value, True),
        # MR with huge changes that can't be checked.
        ({
            "blocking_discussions_resolved": True,
            "commits_list": [{
                "sha": f"{FILE_COMMITS_SHA['nx_submodule_changes_base']}3",
                "message": "msg3",
                "diffs": [],
                "files": {
                    "conan_profiles/_nx_submodule": {"raw_data": NX_SUBMODULE_GOOD_RAW_DATA},
                },
            }],
            "mock_huge_mr": True,
        }, MessageId.NxSubmoduleCheckHugeDiffUncheckable.value, False),
    ])
    def test_changes_are_valid(
            self, nx_submodule_check_rule, mr, mr_manager, message_id, is_resolved):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert nx_submodule_check_rule.execute(mr_manager)
            assert bool(mr.blocking_discussions_resolved) == is_resolved

            comments = mr.mock_comments()
            assert len(comments) == 1, f"Got comments: {comments}"

            if is_resolved:
                emoji = AwardEmojiManager.AUTOCHECK_OK_EMOJI
            else:
                emoji = AwardEmojiManager.AUTOCHECK_IMPOSSIBLE_EMOJI
            assert f":{emoji}:" in comments[0], f"Comment is: {comments[0]}"
            message_details_re = re.compile(
                rf"<details><pre>.*{Note.ID_KEY}: {message_id}",
                flags=re.S)
            assert message_details_re.search(comments[0]), f"Comment is: {comments[0]}"

            mr_manager._mr.load_discussions()  # Update notes in the MergeRequest object.

    @pytest.mark.parametrize(("mr_state", "fail_message_id", "explanation"), [
        # MR with deleted _nx_submodule.
        ({
            "commits_list": [{
                "sha": f"{FILE_COMMITS_SHA['nx_submodule_changes_base']}4",
                "message": "msg4",
                "diffs": [],
                "files": {
                    "conan_profiles/_nx_submodule": {
                        "is_deleted": True,
                        "raw_data": "malformed data",
                    },
                },
            }],
        }, MessageId.NxSubmoduleConfigDeleted.value, "config file was deleted"),
        # MR with malformed _nx_submodule.
        ({
            "commits_list": [{
                "sha": f"{FILE_COMMITS_SHA['nx_submodule_changes_base']}5",
                "message": "msg5",
                "diffs": [],
                "files": {
                    "conan_profiles/_nx_submodule": {
                        "is_deleted": False,
                        "raw_data": "malformed data",
                    },
                },
            }],
        }, MessageId.NxSubmoduleConfigMalformed.value, "has wrong format"),
        # MR with bad git url in _nx_submodule.
        ({
            "commits_list": [{
                "sha": f"{FILE_COMMITS_SHA['nx_submodule_changes_base']}6",
                "message": "msg6",
                "diffs": [],
                "files": {
                    "conan_profiles/_nx_submodule": {"raw_data": NX_SUBMODULE_BAD_RAW_DATA_1},
                },
            }],
        }, MessageId.NxSubmoduleConfigBadGitData.value, "'Bad repo url"),
        # MR with bad git commit sha in _nx_submodule.
        ({
            "commits_list": [{
                "sha": f"{FILE_COMMITS_SHA['nx_submodule_changes_base']}7",
                "message": "msg7",
                "diffs": [],
                "files": {
                    "conan_profiles/_nx_submodule": {"raw_data": NX_SUBMODULE_BAD_RAW_DATA_2},
                },
            }],
        }, MessageId.NxSubmoduleConfigBadGitData.value, "Unknown commit"),
        # MR with bad subrepo directory in _nx_submodule.
        (
            {
                "commits_list": [{
                    "sha": f"{FILE_COMMITS_SHA['nx_submodule_changes_base']}8",
                    "message": "msg8",
                    "diffs": [],
                    "files": {
                        "conan_profiles/_nx_submodule": {"raw_data": NX_SUBMODULE_BAD_RAW_DATA_3},
                    },
                }],
            },
            MessageId.NxSubmoduleConfigBadGitData.value,
            "explanation: No such directory"
        ),
        # MR with file that is not present in the subrepo.
        (
            {
                "commits_list": [{
                    "sha": f"{FILE_COMMITS_SHA['nx_submodule_changes_base']}9",
                    "message": "msg9",
                    "diffs": [],
                    "files": {
                        "conan_profiles/nonexistent.txt": {"raw_data": ""},
                        "conan_profiles/_nx_submodule": {"raw_data": NX_SUBMODULE_GOOD_RAW_DATA},
                    },
                }],
            },
            MessageId.InconsistentNxSubmoduleChange.value,
            "explanation: File 'nonexistent.txt' is not found in subrepo"
        ),
        # MR with deleted file that is present in the subrepo.
        (
            {
                "commits_list": [{
                    "sha": f"{FILE_COMMITS_SHA['nx_submodule_changes_base']}a",
                    "message": "msga",
                    "diffs": [],
                    "files": {
                        "conan_profiles/1.txt": {"raw_data": "file 1\n", "is_deleted": True},
                        "conan_profiles/_nx_submodule": {"raw_data": NX_SUBMODULE_GOOD_RAW_DATA},
                    },
                }],
            },
            MessageId.InconsistentNxSubmoduleChange.value,
            "explanation: File '1.txt' is deleted by found in subrepo"
        ),
        # MR with the executable flag set for the file that is not executable in the submodule.
        (
            {
                "commits_list": [{
                    "sha": f"{FILE_COMMITS_SHA['nx_submodule_changes_base']}b",
                    "message": "msgb",
                    "diffs": [],
                    "files": {
                        "conan_profiles/1.txt": {"raw_data": "file 1\n", "mode": "100755"},
                        "conan_profiles/_nx_submodule": {"raw_data": NX_SUBMODULE_GOOD_RAW_DATA},
                    },
                }],
            },
            MessageId.InconsistentNxSubmoduleChange.value,
            "explanation: File '1.txt' has wrong executable flag 'True'"
        ),
        # MR with the executable flag unset for the file that is executable in the submodule.
        (
            {
                "commits_list": [{
                    "sha": f"{FILE_COMMITS_SHA['nx_submodule_changes_base']}c",
                    "message": "msgc",
                    "diffs": [],
                    "files": {
                        "conan_profiles/2.txt": {"raw_data": "file 2\n", "mode": "100644"},
                        "conan_profiles/_nx_submodule": {"raw_data": NX_SUBMODULE_GOOD_RAW_DATA},
                    },
                }],
            },
            MessageId.InconsistentNxSubmoduleChange.value,
            "explanation: File '2.txt' has wrong executable flag"
        ),
        # MR with the different file content.
        (
            {
                "commits_list": [{
                    "sha": f"{FILE_COMMITS_SHA['nx_submodule_changes_base']}d",
                    "message": "msgd",
                    "diffs": [],
                    "files": {
                        "conan_profiles/1.txt": {"raw_data": ""},
                        "conan_profiles/_nx_submodule": {"raw_data": NX_SUBMODULE_GOOD_RAW_DATA},
                    },
                }],
            },
            MessageId.InconsistentNxSubmoduleChange.value,
            "explanation: File '1.txt' differs from its counterpart"
        ),
    ])
    def test_nx_submodule_problems(
            self, nx_submodule_check_rule, mr, mr_manager, fail_message_id, explanation):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not nx_submodule_check_rule.execute(mr_manager)
            assert not mr.blocking_discussions_resolved

            comments = mr.mock_comments()
            assert len(comments) == 1, f"Got comments: {comments}"
            assert f":{AwardEmojiManager.AUTOCHECK_FAILED_EMOJI}:" in comments[0], (
                f"Last comment is: {comments[0]}")
            message_details_re = re.compile(
                rf"<details><pre>.*{Note.ID_KEY}: {fail_message_id}",
                flags=re.S)
            assert message_details_re.search(comments[0]), f"Comment is: {comments[0]}"
            assert explanation in comments[0], f"Comment is: {comments[0]}"

            mr_manager._mr.load_discussions()  # Update notes in the MergeRequest object.

    @pytest.mark.parametrize("mr_state", [{"commits_list": []}])
    def test_update_error_messages(self, nx_submodule_check_rule, mr_state, mr, mr_manager):
        COMMIT_DESCRIPIONS = [
            {
                "files": {
                    "conan_profiles/1.txt": {"raw_data": ""},
                    "conan_profiles/_nx_submodule": {"raw_data": NX_SUBMODULE_GOOD_RAW_DATA},
                },
                "check_result": False,
                "result_message_id": MessageId.InconsistentNxSubmoduleChange.value,
                "explanation": "File '1.txt' differs from its counterpart",
            }, {
                "files": {"conan_profiles/2.txt": {"raw_data": "file 2\n"}},
                "check_result": False,
                "result_message_id": MessageId.InconsistentNxSubmoduleChange.value,
                "explanation": "File '2.txt' has wrong executable flag",
            }, {
                "files": {
                    "conan_profiles/1.txt": {"raw_data": "file 1\n"},
                    "conan_profiles/2.txt": {"raw_data": "file 2\n", "mode": "100755"},
                },
                "check_result": True,
                "result_message_id": MessageId.NxSubmoduleCheckPassed.value,
            }, {
                # Re-introduce problem.
                "files": {"conan_profiles/2.txt": {"raw_data": "file 2\n"}},
                "check_result": False,
                "result_message_id": MessageId.InconsistentNxSubmoduleChange.value,
                "explanation": "File '2.txt' has wrong executable flag",
            },
        ]

        for i, description in enumerate(COMMIT_DESCRIPIONS):
            commit = {
                "sha": uuid.uuid1().hex,
                "message": "msg",
                "diffs": [],
                "files": description["files"]
            }
            mr.add_mock_commit(commit)

            assert bool(nx_submodule_check_rule.execute(mr_manager)) == description["check_result"]
            assert not mr.blocking_discussions_resolved

            comments = mr.mock_comments()

            assert len(comments) == i + 1, f"Got comments: {comments}"

            if description["check_result"]:
                emoji = AwardEmojiManager.AUTOCHECK_OK_EMOJI
            else:
                emoji = AwardEmojiManager.AUTOCHECK_FAILED_EMOJI
            assert f":{emoji}:" in comments[-1], f"Comment is: {comments[-1]}"

            message_details_re = re.compile(
                rf"<details><pre>.*{Note.ID_KEY}: {description['result_message_id']}",
                flags=re.S)
            assert message_details_re.search(comments[-1]), f"Comment is: {comments[-1]}"

            if "explanation" in description:
                assert f"explanation: {description['explanation']}" in comments[-1], (
                    f"Comment is: {comments[-1]}")

            mr_manager._mr.load_discussions()  # Update notes in the MergeRequest object.
