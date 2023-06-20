ALLOWED_VERSIONS_SETS = {
    "VMS": [
        set(['5.0', '5.0_patch', '5.1', '5.1_patch', 'master']),
        set(['5.0_patch', '5.1', '5.1_patch', 'master']),
        set(['5.1', '5.1_patch', 'master']),
        set(['5.1_patch', 'master']),
        set(['master']),
        set(['Future']),
    ],
    "MOBILE": [
        set(['23.2', '23.1', 'master']),
        set(['23.2', 'master']),
        set(['master']),
        set(['Future']),
    ],
}

IGNORE_LABEL = "hide_from_police"
VERSION_SPECIFIC_LABEL = "version_specific"
DONE_EXTERNALLY_LABEL = "done_externally"
