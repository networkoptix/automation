ALLOWED_VERSIONS_SETS = {
    "VMS": [
        # Important and urgent fix for all releases.
        set(['5.0_patch', '5.1', '5.1_patch', '6.0', 'master']),

        # Dangerous fix, goes for patches only.
        set(['5.0_patch', '5.1_patch', '6.0', 'master']),

        # Important fix for all releases.
        set(['5.1', '5.1_patch', '6.0', 'master']),

        # Support / patch issue.
        set(['5.1_patch', '6.0', 'master']),

        # Ongoing release development.
        set(['6.0', 'master']),

        # Next release development.
        set(['master']),

        # Future task
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
