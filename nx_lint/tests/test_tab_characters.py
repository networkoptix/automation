import pytest


@pytest.fixture
def rule():
    from nx_lint.rules.tab_characters import TabCharactersRule

    return TabCharactersRule()


def test_tabs_are_identified(rule):
    from .fake_file_cache import MockFileCache

    cache = MockFileCache(lines=["line\t"])
    results = rule.check_file("fake_file", cache)
    assert len(results) == 1
    assert "Tab character." in results[0].message
