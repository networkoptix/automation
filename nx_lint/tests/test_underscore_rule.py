## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from pathlib import Path

import pytest


@pytest.fixture
def rule():
    from nx_lint.rules.underscore_separator import UnderscoreSeparatorRule

    return UnderscoreSeparatorRule()


@pytest.mark.parametrize(
    "filename, violations",
    [
        ("filename.txt", 0),
        ("file_name.txt", 0),
        ("file-name.txt", 1),
        ("the_file-name.txt", 1),
        ("the-file-name.txt", 1),
        ("-", 1),
    ],
)
def test_filename_printable_chars(rule, filename, violations):
    results = rule.check_file(Path(filename), None)
    assert len(results) == violations
    if len(results) > 0:
        assert "File name contains '-'" in results[0].message
