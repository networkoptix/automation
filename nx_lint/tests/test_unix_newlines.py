## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import pytest


@pytest.fixture
def rule():
    from nx_lint.rules.unix_newlines import UnixNewlinesRule

    return UnixNewlinesRule()


@pytest.mark.parametrize(
    "lines, violations",
    [
        (["line"], 0),
        (["line\n"], 0),
        (["line\r\n"], 1),
        (["line\r"], 1),
    ],
)
def test_unix_newlines(rule, lines_cache, lines, violations):
    cache = lines_cache(lines)
    results = rule.check_file("fake_file", cache)
    assert len(results) == violations
    if len(results) == 1:
        assert results[0].line == 1
