## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

# This file contains tests for checking parsing of user input affecting bot behavior (mentioning of
# Jira Issues in title/description, etc.).

import pytest

from tests.fixtures import *


class TestParsingFunctions:
    @pytest.mark.parametrize(("mr_state"), [
        # Pass Issue keys via title.
        {
            "title": "VMS-666, CB-667, MOBILE-668: Merge Request attached to Jira Issue",
        },
        # Pass Issue keys via description.
        {
            "title": "Merge Request attached to Jira Issue",
            "description": "Closes VMS-666\nAlso fixed issues CB-667 and MOBILE-668",
        },
        # Pass Issue keys via description and title.
        {
            "title": "VMS-666: Merge request attached to Jira Issue",
            "description": "This mr implementing CB-667,     MOBILE-668",
        },
        # Add isse keys that are not parsed as a proper issue mentioning.
        {
            "title": "VMS-666: Merge request attached to Jira Issue needed by VMS-667",
            "description": "Resolved CB-667, Implements MOBILE-668 not connected with VMS-669",
        },
    ])
    def test_issue_closing_patterns(self, mr, mr_manager):
        keys = mr_manager.data.issue_keys
        assert set(keys) == set(["VMS-666", "CB-667", "MOBILE-668"])
