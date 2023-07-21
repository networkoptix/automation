from .final_newline import FinalNewLineRule
from .trailing_whitespace import TrailingWhitespaceRule
from .filename import FileNameRule
from .empty_lines import EmptyLinesRule
from .control_characters import ControlCharactersRule
from .unicode_characters import UnicodeCharactersRule
from .tab_characters import TabCharactersRule
from .unix_newlines import UnixNewlinesRule
from .rule import Rule

RULES = (
    FinalNewLineRule,
    TrailingWhitespaceRule,
    FileNameRule,
    EmptyLinesRule,
    ControlCharactersRule,
    UnicodeCharactersRule,
    TabCharactersRule,
    UnixNewlinesRule,
)
