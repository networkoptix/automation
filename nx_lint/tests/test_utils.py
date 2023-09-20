import pytest


@pytest.mark.parametrize(
    "line, parts",
    [
        (b"", []),
        (b" ", [b" "]),
        (b"foo\nbar", [b"foo\n", b"bar"]),
        (b"foo\nbar\n", [b"foo\n", b"bar\n"]),
        (b"foo\n bar", [b"foo\n", b" bar"]),
        (b"foo\r\nbar", [b"foo\r\n", b"bar"]),
        (b"foo\nbar\nbaz", [b"foo\n", b"bar\n", b"baz"]),
        (b"foo\r\nbar\r\nbaz", [b"foo\r\n", b"bar\r\n", b"baz"]),
    ],
)
def test_splitlines(line, parts):
    from nx_lint.utils import split_lines

    assert list(split_lines(line)) == parts


@pytest.mark.parametrize("char, result", [*((c, True) for c in range(32, 127))])
def test_is_ascii_printable(char, result):
    from nx_lint.utils import is_ascii_printable

    assert is_ascii_printable(char) == result


@pytest.mark.parametrize(
    "char_codes, result",
    [
        ([32], b" "),
        ([9], b"\t"),
        ([1, 2, 3], b"\x01\x02\x03"),
        ([0x0D, 0x0A], b"\r\n"),
        ([0x0A], b"\n"),
    ],
)
def test_as_bytes(char_codes, result):
    from nx_lint.utils import as_bytes

    assert as_bytes(*char_codes) == result


@pytest.mark.parametrize(
    "char, expected",
    [
        ("\x0A", "\\n"),
        ("\x0D", "\\r"),
        ("\x09", "\\t"),
        ("\x15", "\\x15"),
        ("\x5C", "\\\\"),
        ("\x20", " "),
        ("\x7F", "\\x7F"),
        ("\x41", "A"),
        ("\xFF", "\\xFF"),
        ("\u016D", "\\u016D"),  # LATIN SMALL LETTER U WITH BREVE
        ("\u0416", "\\u0416"),  # CYRILLIC CAPITAL LETTER ZHE
    ],
)
def test_escape_char(char, expected):
    from nx_lint.utils import escape_char

    assert escape_char(char) == expected
