BOT_USERNAME = "robocat"
DEFAULT_COMMIT = {"sha": "11", "message": "msg1", "diffs": [], "files": []}
DEFAULT_MR_ID = 7
FILE_COMMITS_SHA = {
    "good_readme": "101",
    "bad_readme": "102",
    "no_open_source_files": "103",
    "new_bad_readme": "104",
}
BAD_OPENSOURCE_COMMIT = {
    "sha": FILE_COMMITS_SHA["bad_readme"],
    "message": "msg1",
    "diffs": [],
    "files": ["open/readme.md"]
}
DEFAULT_OPEN_SOURCE_APPROVER = "mshevchenko"
