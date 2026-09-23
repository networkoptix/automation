## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from dataclasses import dataclass


@dataclass
class AllowedVersionSet:
    versions: set[str]
    description: str

    def __str__(self):
        return f"{self.description}: {sorted(self.versions)}"


ALLOWED_VERSIONS_SETS = {
    "VMS": [
        AllowedVersionSet(
            {'6.0_patch', '6.1', '6.1.2', '6.1.3', '6.1_patch', 'master (6.2)', 'mobile_26.2'},
            "Technical issue which should go into all branches (e.g. CI-related changes)"
        ),
        AllowedVersionSet(
            {'6.1.3', '6.1_patch', 'master (6.2)'},
            "Ongoing minor release development"
        ),
        AllowedVersionSet(
            {'6.0_patch', '6.1_patch', 'master (6.2)'},
            "6.0 Support / patch issue"
        ),
        AllowedVersionSet(
            {'6.1_patch', 'master (6.2)'},
            "6.1 Support / patch issue"
        ),
        AllowedVersionSet(
            {'6.1_patch', 'master (6.2)', 'mobile_26.2'},
            "6.1 Support / patch issue, important for the mobile branch"
        ),
        AllowedVersionSet(
            {'master (6.2)'},
            "Next release development, actual for the desktop VMS part only"
        ),
        AllowedVersionSet(
            {'master (6.2)', 'mobile_26.2'},
            "Next release development, important for the mobile branch"
        ),
        AllowedVersionSet(
            {'Future'},
            "Postponed for the future releases"
        )
    ],
    "MOBILE": [
        AllowedVersionSet(
            {'master (27.1)'},
            "Next release development"
        ),
        AllowedVersionSet(
            {'master (27.1)', '26.2'},
            "Next release development/ongoing development"
        ),
        AllowedVersionSet(
            {'Future'},
            "Postponed for the future releases"
        )
    ],
    "VMSDB": [
        AllowedVersionSet(
            {'master (26.2)'},
            "Next release development"
        ),
        AllowedVersionSet(
            {'master (26.2)', '26.1'},
            "Ongoing release development"
        )
    ],
    "MDS": [
        AllowedVersionSet(
            {'1.1 (master)'},
            "Ongoing development only, not needed in the 1.0 release"
        ),
        AllowedVersionSet(
            {'1.0 (mds_1.0)', '1.1 (master)'},
            "Needed in the 1.0 release and carried forward to master"
        ),
        AllowedVersionSet(
            {'Future'},
            "Postponed for the future releases"
        )
    ],
}

IGNORE_LABEL = "hide_from_police"
VERSION_SPECIFIC_LABEL = "version_specific"

# This label is kept for compatibility reasons. The recommended way is to use "Done Externally"
# issue resolution.
DONE_EXTERNALLY_LABEL = "done_externally"
