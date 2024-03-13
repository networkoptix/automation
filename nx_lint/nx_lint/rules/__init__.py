## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from .final_newline import FinalNewLineRule
from .trailing_whitespace import TrailingWhitespaceRule
from .filename import FileNameRule
from .empty_lines import EmptyLinesRule
from .control_characters import ControlCharactersRule
from .unicode_characters import UnicodeCharactersRule
from .tab_characters import TabCharactersRule
from .unix_newlines import UnixNewlinesRule
from .lowercase_filename import LowerCaseFileNameRule
from .underscore_separator import UnderscoreSeparatorRule
from .successive_empty_lines import SuccessiveEmptyLinesRule
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
    LowerCaseFileNameRule,
    UnderscoreSeparatorRule,
    SuccessiveEmptyLinesRule,
)
