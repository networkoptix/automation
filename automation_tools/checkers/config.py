ALLOWED_VERSIONS_SETS = {
    "VMS": [
        set(['4.2', '4.2_patch', '5.0', '5.0_patch', 'master']),
        set(['4.2_patch', '5.0', '5.0_patch', 'master']),
        set(['4.2_patch', '5.0_patch', 'master']),
        set(['5.0', '5.0_patch', 'master']),
        set(['5.0_patch', 'master']),
        set(['master']),
        set(['Future']),
    ],
    "MOBILE": [
        set(['21.2', 'master']),
        set(['21.2']),
        set(['22.1', '22.3', 'master']),
        set(['22.3', 'master']),
        set(['Future']),
    ],
}

IGNORE_LABEL = "hide_from_police"
VERSION_SPECIFIC_LABEL = "version_specific"
DONE_EXTERNALLY_LABEL = "done_externally"
