## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import pytest


@pytest.fixture
def rule():
    from nx_lint.rules.empty_lines import EmptyLinesRule

    return EmptyLinesRule()


@pytest.mark.parametrize(
    "lines, violations",
    [
        (["line1", "line2", "line3"], 0),
        (["line1", "", "", "line4"], 0),
        (["", "line3"], 1),
        (["", "", "line3"], 1),
    ],
)
def test_leading_empty_lines(rule, lines_cache, lines, violations):
    cache = lines_cache(lines)
    results = rule.check_file("fake_file", cache)
    assert len(results) == violations
    if len(results) == 1:
        assert results[0].line == 1


@pytest.mark.parametrize(
    "lines, violations",
    [
        (["line1", "line2", "line3"], 0),
        (["line1", "", "", "line4"], 0),
        (["line1", "line2", ""], 1),
        (["line1", "line2", "", ""], 1),
    ],
)
def test_trailing_empty_lines(rule, lines_cache, lines, violations):
    cache = lines_cache(lines)
    results = rule.check_file("fake_file", cache)
    assert len(results) == violations
    if len(results) == 1:
        assert results[0].line == len(lines)
