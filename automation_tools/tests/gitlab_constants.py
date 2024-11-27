## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from copy import deepcopy

from automation_tools.tests.mocks.file import (
    GOOD_README_RAW_DATA, BAD_README_RAW_DATA, BAD_CMAKELISTS_RAW_DATA)

BOT_NAME = "Robo Cat"
BOT_EMAIL = "robocat@foo.bar"
BOT_USERNAME = "robocat"
BOT_USERID = 100
DEFAULT_JIRA_ISSUE_KEY = "VMS-666"
NXLIB_JIRA_ISSUE_KEY = "NXLIB-666"
DEFAULT_CLOUD_ISSUE_KEY = "CLOUD-666"
DEFAULT_COMMIT = {
    "sha": "11",
    "message": f"{DEFAULT_JIRA_ISSUE_KEY}: msg1",
    "diffs": [],
    "files": {},
}
DEFAULT_NXLIB_COMMIT = {
    "sha": "111",
    "message": f"{NXLIB_JIRA_ISSUE_KEY}: msg1",
    "diffs": [],
    "files": {},
}
DEFAULT_CLOUD_COMMIT = {
    "sha": "1111",
    "message": f"{DEFAULT_CLOUD_ISSUE_KEY}: msg1",
    "diffs": [],
    "files": {},
}
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
    "nx_submodule_changes_base": "109",
    "opensource_bad_new_file": "110",
    "opensource_deleted_new_file": "111",
    "apidoc_changes_commit": "112",
    "MULTIPLE_KEEPERS_COMMIT_1": "113",
    "MULTIPLE_KEEPERS_COMMIT_2": "114",
    "MULTIPLE_KEEPERS_COMMIT_3": "115",
}
CONFLICTING_COMMIT_SHA = "1001"
BAD_OPENSOURCE_COMMIT = {
    "sha": FILE_COMMITS_SHA["bad_dontreadme"],
    "message": f"{DEFAULT_JIRA_ISSUE_KEY}: some title\nsome msg1",
    "diffs": [],
    "files": {"open/dontreadme.md": {"is_new": False, "raw_data": BAD_README_RAW_DATA}},
}
BAD_OPENCANDIDATE_COMMIT = {
    "sha": FILE_COMMITS_SHA["bad_opencadidate_source_files"],
    "message": f"{DEFAULT_JIRA_ISSUE_KEY}: some title\nsome msg1",
    "diffs": [],
    "files": {
        "open_candidate/CMakeLists.txt": {"is_new": True, "raw_data": BAD_CMAKELISTS_RAW_DATA}},
}
GOOD_README_COMMIT_CHANGED_FILE = {
    "sha": FILE_COMMITS_SHA["good_dontreadme"],
    "message": f"{DEFAULT_JIRA_ISSUE_KEY}: some title\nsome msg",
    "diffs": [],
    "files": {"open/dontreadme.md": {"is_new": False, "raw_data": GOOD_README_RAW_DATA}},
}
GOOD_README_COMMIT_NEW_FILE = {
    "sha": FILE_COMMITS_SHA["good_dontreadme"],
    "message": f"{DEFAULT_JIRA_ISSUE_KEY}: some title\nsome msg",
    "diffs": [],
    "files": {"open/dontreadme.md": {"is_new": True, "raw_data": GOOD_README_RAW_DATA}},
}
GOOD_README_COMMIT_DELETED_FILE = {
    "sha": FILE_COMMITS_SHA["good_dontreadme"],
    "message": f"{DEFAULT_JIRA_ISSUE_KEY}: some title\nsome msg",
    "diffs": [],
    "files": {"open/dontreadme.md": {"is_new": False, "is_deleted": True, "raw_data": ""}},
}
APIDOC_INFO_CHANGED_COMMIT = {
    "sha": FILE_COMMITS_SHA["apidoc_changes_commit"],
    "message": f"{DEFAULT_JIRA_ISSUE_KEY}: some title\nsome msg",
    "diffs": [{"diff": "@@ -4,1 +4,1 @@\n- Old string\n+ New string"}],
    "files": {
        "somefile.cpp": {
            "is_new": False,
            "is_deleted": False,
            "raw_data": "",
            "diff": "@@ -4,1 +4,1 @@\n- Old string\n+    /**%apidoc Integration id. */",
        },
    },
}
MULTIPLE_KEEPERS_COMMIT_1 = {
    "sha": FILE_COMMITS_SHA["MULTIPLE_KEEPERS_COMMIT_1"],
    "message": f"{DEFAULT_JIRA_ISSUE_KEY}: some title\nsome msg",
    "diffs": [{"diff": "@@ -4,1 +4,1 @@\n- Old string\n+ New string"}],
    "files": {
        "open/dontreadme.md": {"is_new": True, "is_deleted": False, "raw_data": ""},
        "dir1/somefile.cpp": {"is_new": False, "is_deleted": False, "raw_data": ""},
        "somefile.cpp": {
            "is_new": False,
            "is_deleted": False,
            "raw_data": "",
            "diff": "@@ -4,1 +4,1 @@\n- Old string\n+    /**%apidoc Integration id. */",
        },
    },
}
MULTIPLE_KEEPERS_COMMIT_2 = deepcopy(MULTIPLE_KEEPERS_COMMIT_1)
MULTIPLE_KEEPERS_COMMIT_2["sha"] = FILE_COMMITS_SHA["MULTIPLE_KEEPERS_COMMIT_2"]
MULTIPLE_KEEPERS_COMMIT_3 = deepcopy(MULTIPLE_KEEPERS_COMMIT_1)
MULTIPLE_KEEPERS_COMMIT_3["sha"] = FILE_COMMITS_SHA["MULTIPLE_KEEPERS_COMMIT_3"]

OPEN_SOURCE_APPROVER_COMMON = "approver1"
OPEN_SOURCE_APPROVER_CLIENT = "approver2"
OPEN_SOURCE_APPROVER_COMMON_2 = "approver3"
APIDOC_APPROVER = "apidoc_approver1"
CODE_OWNER_1 = "code_owner_1"
CODE_OWNER_2 = "code_owner_2"
CODE_OWNER_3 = "code_owner_3"
UNIVERSAL_APPROVER = "universal_approver"
DEFAULT_APPROVE_RULESET = {
    "relevance_checker": "is_file_open_sourced",
    "rules": [
        {
            "patterns": ["open_candidate/vms/client/.+", "open_candidate/cloud/.+"],
            "approvers": [OPEN_SOURCE_APPROVER_CLIENT],
        }, {
            "patterns": ["open_candidate/.+", "open/((?!unknown_approver_prefix_).+)"],
            "approvers": [OPEN_SOURCE_APPROVER_COMMON, OPEN_SOURCE_APPROVER_COMMON_2],
        },
    ],
}
DEFAULT_APIDOC_APPROVE_RULESET = {
    "relevance_checker": "does_file_diff_contain_apidoc_changes",
    "rules": [{"patterns": [".+"], "approvers": [APIDOC_APPROVER]}],
}
DEFAULT_CODEOWNER_APPROVE_RULESET = {
    "relevance_checker": "match_name_pattern",
    "rules": [
        {"patterns": ["dir1/.+"], "approvers": [CODE_OWNER_1]},
        {"patterns": ["dir2/.+"], "approvers": [CODE_OWNER_2, CODE_OWNER_3]},
        {"patterns": ["dir3/.+"], "approvers": [CODE_OWNER_3]},
    ],
}
DEFAULT_SUBMODULE_DIRS = ["conan_profiles"]
USERS = [
    {"username": "user1", "name": "User 1", "id": 1, "email": "user1@foo.bar"},
    {"username": "user2", "name": "User 2", "id": 2, "email": "user2@foo.bar"},
    {"username": "approver1", "name": "Approver 1", "id": 10, "email": "approver1@foo.bar"},
    {"username": "approver2", "name": "Approver 2", "id": 11, "email": "approver2@foo.bar"},
    {"username": "approver3", "name": "Approver 3", "id": 13, "email": "approver3@foo.bar"},
    {"username": "code_owner_1", "name": "Code owner 1", "id": 14, "email": "codeowner1@foo.bar"},
    {"username": "code_owner_2", "name": "Code owner 2", "id": 15, "email": "codeowner2@foo.bar"},
    {"username": "code_owner_3", "name": "Code owner 3", "id": 16, "email": "codeowner3@foo.bar"},
    {"username": "apidoc_approver1", "name": "Approver 4", "id": 17, "email": "approver4@foo.bar"},
    {"username": "universal_approver", "name": "Approver 5", "id": 18, "email": "app5@foo.bar"},
    {"username": BOT_USERNAME, "name": BOT_NAME, "id": BOT_USERID, "email": BOT_EMAIL},
]
DEFAULT_USER = USERS[0]
MERGED_TO_MASTER_MERGE_REQUESTS = {
    "merged": {"iid": 10, "target_branch": "master", "state": "merged"},
    "opened": {"iid": 11, "target_branch": "master", "state": "opened"},
}
MERGED_TO_5_1_MERGE_REQUESTS = {
    "merged": {"iid": 20, "target_branch": "vms_5.1", "state": "merged"},
    "opened": {"iid": 21, "target_branch": "vms_5.1", "state": "opened"},
}
MERGED_TO_4_2_MERGE_REQUESTS = {
    "merged": {"iid": 30, "target_branch": "vms_4.2", "state": "merged"},
    "opened": {"iid": 31, "target_branch": "vms_4.2", "state": "opened"},
}
MERGED_TO_MASTER_MERGE_REQUESTS_MOBILE = {
    "merged": {"iid": 110, "target_branch": "master", "state": "merged"},
    "opened": {"iid": 111, "target_branch": "master", "state": "opened"},
}
MERGED_TO_21_1_MERGE_REQUESTS_MOBILE = {
    "merged": {"iid": 120, "target_branch": "vms_5.1", "state": "merged"},
    "opened": {"iid": 121, "target_branch": "vms_5.1", "state": "opened"},
}
MERGED_TO_MASTER_MERGE_REQUESTS_CB = {
    "merged": {"iid": 210, "target_branch": "master", "state": "merged"},
    "opened": {"iid": 211, "target_branch": "master", "state": "opened"},
}
MERGED_TO_20_1_MERGE_REQUESTS_CB = {
    "merged": {"iid": 220, "target_branch": "vms_5.1", "state": "merged"},
    "opened": {"iid": 221, "target_branch": "vms_5.1", "state": "opened"},
}

MR_MERGED_COMMENT_TEMPLATE = (
    "Some text\n\n{{noformat}}Message Id: MrMergedToBranch\nData:\n    MrId: 1234\n    MrBranch: "
    "{branch}\n{{noformat}}")
