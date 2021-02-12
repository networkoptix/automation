BOT_NAME = "Robo Cat"
BOT_USERNAME = "robocat"
BOT_USERID = 100
DEFAULT_COMMIT = {"sha": "11", "message": "msg1", "diffs": [], "files": []}
DEFAULT_MR_ID = 7
DEFAULT_REQUIRED_APPROVALS_COUNT = 2
FILE_COMMITS_SHA = {
    "good_dontreadme": "101",
    "bad_dontreadme": "102",
    "no_open_source_files": "103",
    "new_bad_dontreadme": "104",
    "excluded_open_source_files": "105",
    "bad_opencadidate_source_files": "106",
}
CONFLICTING_COMMIT_SHA = "1001"
BAD_OPENSOURCE_COMMIT = {
    "sha": FILE_COMMITS_SHA["bad_dontreadme"],
    "message": "msg1",
    "diffs": [],
    "files": ["open/dontreadme.md"]
}
BAD_OPENCANDIDATE_COMMIT = {
    "sha": FILE_COMMITS_SHA["bad_opencadidate_source_files"],
    "message": "msg1",
    "diffs": [],
    "files": ["open_candidate/CMakeLists.txt"]
}
DEFAULT_OPEN_SOURCE_APPROVER = "mshevchenko"
USERS = [
    {"username": "user1", "id": 1},
    {"username": "user2", "id": 2},
    {"username": "mshevchenko", "id": 10},
    {"username": BOT_USERNAME, "id": BOT_USERID}
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
