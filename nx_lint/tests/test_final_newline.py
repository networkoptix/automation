import pytest
import nx_lint.utils


@pytest.fixture
def rule(monkeypatch):
    import nx_lint.rules.final_newline

    monkeypatch.setattr(nx_lint.rules.final_newline, "is_text_file", lambda _: True)

    return nx_lint.rules.final_newline.FinalNewLineRule()


@pytest.mark.parametrize(
    "lines, violations",
    [
        (["line1", "line2", "line3"], 1),
        (["line1", "line2", "line3\n"], 0),
        (["line1", "line2", "line3\r"], 1),
    ],
)
def test_final_newline(rule, lines_cache, lines, violations, monkeypatch):
    cache = lines_cache(lines)
    results = rule.check_file("fake_file", cache)
    assert len(results) == violations
    if len(results) == 1:
        assert results[0].line == 3
