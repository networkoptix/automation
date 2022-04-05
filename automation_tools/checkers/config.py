ALLOWED_VERSIONS_SETS = {
    "VMS": [
        set(['4.1_patch', '4.2', '4.2_patch', 'master']),
        set(['4.2', '4.2_patch', 'master']),
        set(['4.2_patch', 'master']),
        set(['4.2_patch', '5.0', 'master']),
        set(['4.2', '4.2_patch', '5.0', 'master']),
        set(['5.0', 'master']),
        set(['master']),
        set(['Future']),
    ],
    "MOBILE": [
        set(['21.2', 'master']),
        set(['21.2']),
        set(['22.1', 'master']),
        set(['Future']),
    ],
}

IGNORE_LABEL = "hide_from_police"
VERSION_SPECIFIC_LABEL = "version_specific"
DONE_EXTERNALLY_LABEL = "done_externally"
