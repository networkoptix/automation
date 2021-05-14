from bots.robocat.tests.mocks.file import (
    GOOD_README_RAW_DATA, BAD_README_RAW_DATA, BAD_CMAKELISTS_RAW_DATA)
from automation_tools.tests.mocks.git_mocks import BOT_EMAIL, BOT_NAME, BOT_USERNAME


BOT_USERID = 100
DEFAULT_COMMIT = {"sha": "11", "message": "msg1", "diffs": [], "files": {}}
DEFAULT_MR_ID = 7
DEFAULT_REQUIRED_APPROVALS_COUNT = 2
DEFAULT_PROJECT_ID = 1
FORK_PROJECT_ID = 2
FILE_COMMITS_SHA = {
    "good_dontreadme": "101",
    "bad_dontreadme": "102",
    "no_open_source_files": "103",
    "new_bad_dontreadme": "104",
    "excluded_open_source_files": "105",
    "bad_opencadidate_source_files": "106",
    "opensource_unknown_file": "107",
    "good_opensource_file": "108",
}
CONFLICTING_COMMIT_SHA = "1001"
BAD_OPENSOURCE_COMMIT = {
    "sha": FILE_COMMITS_SHA["bad_dontreadme"],
    "message": "msg1",
    "diffs": [],
    "files": {"open/dontreadme.md": {"is_new": False, "raw_data": BAD_README_RAW_DATA}},
}
BAD_OPENCANDIDATE_COMMIT = {
    "sha": FILE_COMMITS_SHA["bad_opencadidate_source_files"],
    "message": "msg1",
    "diffs": [],
    "files": {
        "open_candidate/CMakeLists.txt": {"is_new": True, "raw_data": BAD_CMAKELISTS_RAW_DATA}},
}
GOOD_README_COMMIT_CHANGED_FILE = {
    "sha": FILE_COMMITS_SHA["good_dontreadme"],
    "message": "msg",
    "diffs": [],
    "files": {"open/dontreadme.md": {"is_new": False, "raw_data": GOOD_README_RAW_DATA}},
}
GOOD_README_COMMIT_NEW_FILE = {
    "sha": FILE_COMMITS_SHA["good_dontreadme"],
    "message": "msg",
    "diffs": [],
    "files": {"open/dontreadme.md": {"is_new": True, "raw_data": GOOD_README_RAW_DATA}},
}
OPEN_SOURCE_APPROVER_COMMON = "approver1"
OPEN_SOURCE_APPROVER_CLIENT = "approver2"
DEFAILT_APPROVE_RULES_LIST = [
    {
        "patterns": ["open_candidate/vms/client/.+", "open_candidate/cloud/.+"],
        "approvers": [OPEN_SOURCE_APPROVER_CLIENT],
    }, {
        "patterns": ["open_candidate/.+", "open/.+"],
        "approvers": [OPEN_SOURCE_APPROVER_COMMON],
    },
]
USERS = [
    {"username": "user1", "name": "User 1", "id": 1, "email": "user1@foo.bar"},
    {"username": "user2", "name": "User 2", "id": 2, "email": "user2@foo.bar"},
    {"username": "approver1", "name": "Approver 1", "id": 10, "email": "approver1@foo.bar"},
    {"username": "approver2", "name": "Approver 2", "id": 11, "email": "approver2@foo.bar"},
    {"username": BOT_USERNAME, "name": BOT_NAME, "id": BOT_USERID, "email": BOT_EMAIL}
]
MERGED_TO_MASTER_MERGE_REQUESTS = {
    "merged": {"iid": 10, "target_branch": "master", "state": "merged"},
    "opened": {"iid": 11, "target_branch": "master", "state": "opened"},
}
MERGED_TO_4_1_MERGE_REQUESTS = {
    "merged": {"iid": 20, "target_branch": "vms_4.1", "state": "merged"},
    "opened": {"iid": 21, "target_branch": "vms_4.1", "state": "opened"},
}

MERGED_TO_4_2_MERGE_REQUESTS = {
    "merged": {"iid": 30, "target_branch": "vms_4.2", "state": "merged"},
    "opened": {"iid": 31, "target_branch": "vms_4.2", "state": "opened"},
}
