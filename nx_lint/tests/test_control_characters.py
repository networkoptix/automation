import pytest


@pytest.fixture
def rule():
    from nx_lint.rules.control_characters import ControlCharactersRule

    return ControlCharactersRule()


@pytest.mark.parametrize(
    "lines",
    [[f"line{chr(x)}"] for x in range(0x00, 0x1F) if x not in (0x0A, 0x09)]
    + [["line\x7F"]],
)
def test_control_characters_identified(rule, lines_cache, lines):
    cache = lines_cache(lines)
    results = rule.check_file("fake_file", cache)
    assert len(results) == 1


def test_newline_is_not_control_character(rule):
    from .fake_file_cache import MockFileCache

    cache = MockFileCache(lines=["line\n"])
    results = rule.check_file("fake_file", cache)
    assert len(results) == 0


def test_tab_is_not_control_character(rule):
    # Though tabs are technically control characters, they are not checked by this rule.
    from .fake_file_cache import MockFileCache

    cache = MockFileCache(lines=["line\t"])
    results = rule.check_file("fake_file", cache)
    assert len(results) == 0
