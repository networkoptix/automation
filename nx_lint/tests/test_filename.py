from pathlib import Path

import pytest


@pytest.fixture
def rule():
    from nx_lint.rules.filename import FileNameRule

    return FileNameRule()


@pytest.mark.parametrize(
    "filename, violations",
    [
        ("file", 0),
        ("file.txt", 0),
        ("fil\x02e.txt", 1),
        ("f\x04il\x02e.txt", 1),
        ("f\x04il\x02e.txt\x05", 1),
    ],
)
def test_filename_printable_chars(rule, filename, violations):
    results = rule.check_file(Path(filename), None)
    assert len(results) == violations
    if len(results) > 0:
        assert "Prohibited characters" in results[0].message


@pytest.mark.parametrize(
    "filename, violations",
    [
        ("file.txt", 0),
        ("file<.txt", 1),
        ("file>.txt", 1),
        ("file:.txt", 1),
        ('file".txt', 1),
        ("file\\.txt", 1),
        ("file|.txt", 1),
        ("file?.txt", 1),
        ("file*.txt", 1),
    ],
)
def test_windows_incompatible_chars(rule, filename, violations):
    results = rule.check_file(Path(filename), None)
    assert len(results) == violations
    if len(results) > 0:
        assert "Prohibited characters" in results[0].message


@pytest.mark.parametrize(
    "filename, violations",
    [
        ("file.txt", 0),
        ("aux", 1),
        ("con", 1),
        ("nul", 1),
        ("prn", 1),
        *((f"com{i}", 1) for i in range(10)),
        *((f"lpt{i}", 1) for i in range(10)),
    ],
)
def test_windows_incompatible_names(rule, filename, violations):
    results = rule.check_file(Path(filename), None)
    assert len(results) == violations
    if len(results) > 0:
        assert "name is incompatible with Windows" in results[0].message


def test_spaces_in_filename(rule):
    results = rule.check_file(Path("file name.txt"), None)
    assert len(results) == 1


def test_dashes_in_filename(rule):
    results = rule.check_file(Path("file-name.txt"), None)
    assert len(results) == 0
