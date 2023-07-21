import pytest


@pytest.fixture
def rule():
    from nx_lint.rules.unicode_characters import UnicodeCharactersRule

    return UnicodeCharactersRule()


@pytest.mark.parametrize("lines", [["line" + chr(x)] for x in range(0x80, 0xFF + 1)])
def test_unicode_chars_identified(rule, lines_cache, lines):
    cache = lines_cache(lines)
    results = rule.check_file("fake_file", cache)
    assert len(results) == 1
