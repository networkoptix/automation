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
        (0x0A, "\\n"),
        (0x0D, "\\r"),
        (0x09, "\\t"),
        (0x15, "\\x15"),
        (0x5C, "\\\\"),
        (0x20, "<space>"),
        (0x7F, "\\x7F"),
        (0x80, "\\x80"),
        (0x41, "A"),
        (0xFF, "\\xFF"),
    ],
)
def test_escape_ascii_char(char, expected):
    from nx_lint.utils import escape_ascii_char

    assert escape_ascii_char(char) == expected


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
        ("\xFF", "\\u00FF"),
        ("\u016D", "\\u016D"),  # LATIN SMALL LETTER U WITH BREVE
        ("\u0416", "\\u0416"),  # CYRILLIC CAPITAL LETTER ZHE
        ("\U0001F300", "\\U0001F300"),  # CYCLONE
    ],
)
def test_escape_unicode_char(char, expected):
    from nx_lint.utils import escape_unicode_char

    assert escape_unicode_char(char) == expected


def test_escape_char_spell_space():
    from nx_lint.utils import escape_ascii_char

    assert escape_ascii_char(b" ", spell_space=False) == " "
    assert escape_ascii_char(b" ", spell_space=True) == "<space>"
    assert escape_ascii_char(b"\t", spell_space=False) == "\\t"
    assert escape_ascii_char(b"\t", spell_space=True) == "\\t"


def test_escape_ascii_char_invalid_type():
    from nx_lint.utils import escape_ascii_char

    with pytest.raises(TypeError):
        escape_ascii_char("A")

    with pytest.raises(TypeError):
        escape_ascii_char("\U0001F300")

    with pytest.raises(ValueError):
        escape_ascii_char(b"")

    with pytest.raises(ValueError):
        escape_ascii_char(b"1234")

    with pytest.raises(ValueError):
        escape_ascii_char(384)


def test_escape_unicode_char_invalid_type():
    from nx_lint.utils import escape_unicode_char

    with pytest.raises(TypeError):
        escape_unicode_char(b"A")

    with pytest.raises(TypeError):
        escape_unicode_char(3.14159265358979)

    with pytest.raises(ValueError):
        escape_unicode_char("")

    with pytest.raises(ValueError):
        escape_unicode_char("1234")
