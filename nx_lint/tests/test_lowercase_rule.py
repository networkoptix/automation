## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from pathlib import Path

import pytest


@pytest.fixture
def rule():
    from nx_lint.rules.lowercase_filename import LowerCaseFileNameRule

    return LowerCaseFileNameRule()


@pytest.mark.parametrize(
    "filename, violations",
    [
        ("file.txt", 0),
        ("File.txt", 1),
        ("FileName.txt", 1),
    ],
)
def test_filename_printable_chars(rule, filename, violations):
    results = rule.check_file(Path(filename), None)
    assert len(results) == violations
    if len(results) > 0:
        assert "File name contains uppercase letters" in results[0].message
