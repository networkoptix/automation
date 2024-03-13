## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import pytest


@pytest.fixture
def rule():
    from nx_lint.rules.successive_empty_lines import SuccessiveEmptyLinesRule

    return SuccessiveEmptyLinesRule()


@pytest.mark.parametrize(
    "lines, violation_count, line_num",
    [
        (["line1", "line2", "line3"], 0, 0),
        (["", "line2", ""], 0, 0),
        (["line1", "", "line4"], 0, 0),
        (["line1", "", "", "line4"], 1, 2),
        (["line1", "line2", "", "", "line4"], 1, 3),
        (["line1", "line2", "", "", "", "line4"], 1, 3),
        (["line1", "line2", "", "", "", "", "line4"], 1, 3),
    ],
)
def test_successive_empty_lines(rule, lines_cache, lines, violation_count, line_num):
    cache = lines_cache(lines)
    results = rule.check_file("fake_file", cache)
    assert len(results) == violation_count
    if violation_count > 0:
        assert results[0].line == line_num
