## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

ALLOWED_VERSIONS_SETS = {
    "VMS": [
        # Technical issue which should go into all branches (e.g. CI adaptation).
        set(['5.1_patch', '6.0.3', '6.0_patch', 'master', 'mobile_25.1']),

        # Ongoing minor release development.
        set(['6.0_patch', '6.0.3', 'master']),

        # Support / patch issue.
        set(['6.0_patch', 'master']),

        # Support / patch issue, important for the mobile branch.
        set(['6.0_patch', 'master', 'mobile_25.1']),

        # Next release development, actual for the desktop VMS part only.
        set(['master']),

        # Next release development, important for the mobile branch.
        set(['master', 'mobile_25.1']),

        # Future task
        set(['Future']),
    ],
    "MOBILE": [
        set(['25.1', 'master']),
        set(['master']),
        set(['Future']),
    ],
}

IGNORE_LABEL = "hide_from_police"
VERSION_SPECIFIC_LABEL = "version_specific"
DONE_EXTERNALLY_LABEL = "done_externally"
