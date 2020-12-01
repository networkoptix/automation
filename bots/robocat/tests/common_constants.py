BOT_USERNAME = "robocat"
DEFAULT_COMMIT = {"sha": "11", "message": "msg1", "diffs": [], "files": []}
DEFAULT_MR_ID = 7
FILE_COMMITS_SHA = {
    "good_dontreadme": "101",
    "bad_dontreadme": "102",
    "no_open_source_files": "103",
    "new_bad_dontreadme": "104",
    "excluded_open_source_files": "105",
}
BAD_OPENSOURCE_COMMIT = {
    "sha": FILE_COMMITS_SHA["bad_dontreadme"],
    "message": "msg1",
    "diffs": [],
    "files": ["open/dontreadme.md"]
}
DEFAULT_OPEN_SOURCE_APPROVER = "mshevchenko"
