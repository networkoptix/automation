## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "exclusion, excluded, included",
    [
        (
            {"unicode_chars": ["foo1.txt"]},
            [("foo1.txt", "unicode_chars")],
            [("bar1.txt", "unicode_chars")],
        ),
        (
            {"unicode_chars": ["foo2.txt", "bar2.txt"]},
            [("foo2.txt", "unicode_chars"), ("bar2.txt", "unicode_chars")],
            [],
        ),
        (
            {"unicode_chars": ["foo3.txt"]},
            [],
            [("foo3.txt", "empty_lines"), ("bar3.txt", "empty_lines")],
        ),
        (
            {"unicode_chars": ["foo5.txt"]},
            [],
            [("quaz/foo5.txt", "unicode_chars")]
        ),
        (
            {"unicode_chars": ["**/foo5.txt"]},
            [("quaz/foo5.txt", "unicode_chars")],
            []
        ),
        (
            {"unicode_chars": ["foo7.txt"], "empty_lines": ["bar7.txt"]},
            [("foo7.txt", "unicode_chars"), ("bar7.txt", "empty_lines")],
            [("foo7.txt", "empty_lines"), ("bar7.txt", "unicode_chars")],
        ),
    ],
)
def test_rule_exclusion(exclusion, excluded, included):
    from nx_lint.config import Config
    from nx_lint.linter import Linter

    config = Config([], [], ["unicode_chars", "empty_lines"], {}, exclusion)
    linter = Linter(config, False)

    for file_path, rule in excluded:
        assert rule not in (r.identifier for r in linter._rules_for_file(Path(file_path)))
    for file_path, rule in included:
        assert rule in (r.identifier for r in linter._rules_for_file(Path(file_path)))
