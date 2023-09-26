import pytest


@pytest.mark.parametrize(
    "input,expected",
    [
        (({}, {}), {}),
        (({"a": 1}, {}), {"a": 1}),
        (({}, {"a": 1}), {"a": 1}),
        (({"a": 1}, {"a": 2}), {"a": 2}),
        (({"a": 1, "b": 2}, {"b": 3, "c": 4}), {"a": 1, "b": 3, "c": 4}),
        (
            ({"a": 1, "b": {"c": 2}}, {"b": {"d": 3}, "e": 4}),
            {"a": 1, "b": {"c": 2, "d": 3}, "e": 4},
        ),
        (
            ({"a": 1, "b": {"c": 2}}, {"a": 2, "b": {"d": 3}, "e": 4}),
            {"a": 2, "b": {"c": 2, "d": 3}, "e": 4},
        ),
    ],
)
def test_merge_dicts(input, expected):
    from automation_tools.utils import merge_dicts

    assert dict(merge_dicts(*input)) == expected
