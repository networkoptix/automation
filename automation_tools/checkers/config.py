ALLOWED_VERSIONS_SETS = {
    "VMS": [
        set(['4.2', '4.2_patch', '5.0', '5.0_patch', 'master']),
        set(['4.2_patch', '5.0', '5.0_patch', 'master']),
        set(['4.2_patch', '5.0_patch', 'master']),
        set(['5.0', '5.0_patch', 'master']),
        set(['5.0', '5.0_patch', '5.1', 'master']),
        set(['5.0_patch', '5.1', 'master']),
        set(['5.1', 'master']),
        set(['master']),
        set(['Future']),
    ],
    "MOBILE": [
        set(['22.5', '22.4', 'master']),
        set(['22.5', 'master']),
        set(['Future']),
    ],
}

IGNORE_LABEL = "hide_from_police"
VERSION_SPECIFIC_LABEL = "version_specific"
DONE_EXTERNALLY_LABEL = "done_externally"
