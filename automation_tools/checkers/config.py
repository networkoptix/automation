## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from dataclasses import dataclass
from typing import Set


@dataclass
class AllowedVersionSet:
    versions: set[str]
    description: str

    def __str__(self):
        return f"{self.description}: {self.versions}"


ALLOWED_VERSIONS_SETS = {
    "VMS": [
        AllowedVersionSet(
            ['6.0.6', '6.0_patch', '6.1', '6.1_patch', 'master', 'mobile_25.2.1'],
            "Technical issue which should go into all branches (e.g. CI-related changes)"
        ),
        AllowedVersionSet(
            ['6.0_patch', '6.0.6', '6.1', '6.1_patch', 'master'],
            "Ongoing minor release development"
        ),
        AllowedVersionSet(
            ['6.0_patch', '6.1', '6.1_patch', 'master'],
            "6.0 Support / patch issue"
        ),
        AllowedVersionSet(
            ['6.0_patch', '6.1', '6.1_patch', 'master', 'mobile_25.2.1'],
            "6.0 Support / patch issue, important for the mobile branch"
        ),
        AllowedVersionSet(
            ['6.1', '6.1_patch', 'master'],
            "Current release development, actual for the desktop VMS part only"
        ),
        AllowedVersionSet(
            ['6.1', '6.1_patch', 'master', 'mobile_25.2.1'],
            "Current release development, important for the mobile branch"
        ),
        AllowedVersionSet(
            ['6.1_patch', 'master'],
            "6.1 Support / patch issue"
        ),
        AllowedVersionSet(
            ['6.1_patch', 'master', 'mobile_25.2.1'],
            "6.1 Support / patch issue, important for the mobile branch"
        ),
        AllowedVersionSet(
            ['master'],
            "Next release development, actual for the desktop VMS part only"
        ),
        AllowedVersionSet(
            ['master', 'mobile_25.2.1'],
            "Next release development, important for the mobile branch"
        ),
        AllowedVersionSet(
            ['Future'],
            "Postponed for the future releases"
        )
    ],
    "MOBILE": [
        AllowedVersionSet(
            ['master'],
            "Next release development"
        ),
        AllowedVersionSet(
            ['master', '25.2.1'],
            "Next release/ support / patch issue"
        ),
        AllowedVersionSet(
            ['Future'],
            "Postponed for the future releases"
        )
    ],
}

IGNORE_LABEL = "hide_from_police"
VERSION_SPECIFIC_LABEL = "version_specific"
DONE_EXTERNALLY_LABEL = "done_externally"
