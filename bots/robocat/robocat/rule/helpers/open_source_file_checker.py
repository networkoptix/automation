import re
from pathlib import Path
from collections import namedtuple
from typing import List
from itertools import chain
import enum

# Paths configuration.
OPENSOURCE_ROOT = "open"
EXCLUDED_DIRS = {"artifacts/nx_kit/src/json11", "licenses"}
EXCLUDED_FILES = {"readme.md"}

MPL = (
    'Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/')
SHEBANG_SUFFICIES_MAP = {"sh": "#!/bin/bash"}

FileError = namedtuple("FileError", ["type", "params", "line", "column"])


class ErrorType(enum.Enum):
    incorrect_mpl = enum.auto()
    missing_mpl = enum.auto()
    missing_empty_line = enum.auto()
    politeness_violation = enum.auto()
    trademark_violation = enum.auto()
    unknown_license = enum.auto()
    unexpected_shebang = enum.auto()
    unknown_file_type = enum.auto()

    def __str__(self):
        return str(self.name)


CHECK_REGEX_MAP = {
    ErrorType.politeness_violation: re.compile(r'\b(?P<word>{})\b'.format("|".join([
        'crazy',
        'awful.*?',
        'stolen',
        'shit.*?',
        'stupid.*?',
        'silly',
        'ugly',
        'hack.*?',
        'blya.*?',
        'fuck.*?'])),
        flags=re.IGNORECASE),
    ErrorType.trademark_violation: re.compile(r'\b(?P<word>{})\b'.format("|".join([
        'hanwha',
        'networkoptix',
        'digitalwatchdog',
        'dw',
        'optix'])),
        flags=re.IGNORECASE),
    ErrorType.unknown_license: re.compile(r'\b(?P<word>{})\b'.format("|".join([
        'copyright'
        'license',
        'gpl'])),
        flags=re.IGNORECASE)
}


class OpenSourceFileChecker:
    def __init__(self, file_name: str, file_content: str):
        self._file = Path(file_name)
        self._lines = file_content.splitlines()

    @staticmethod
    def is_check_needed(file_path: str):
        if not file_path.startswith(f"{OPENSOURCE_ROOT}/"):
            return False

        if any(d for d in EXCLUDED_DIRS if file_path.startswith(f"{OPENSOURCE_ROOT}/{d}/")):
            return False

        if any(f for f in EXCLUDED_FILES if file_path == f"{OPENSOURCE_ROOT}/{f}"):
            return False

        return True

    def file_errors(self) -> List[FileError]:
        check_params = self._get_check_params()

        if check_params is None:
            return [FileError(
                type=ErrorType.unknown_file_type,
                params={"file": self._file.name},
                line=0,
                column=0)]

        return list(chain(
            self._check_shebang(),
            self._check_empty_line(**check_params),
            self._check_mpl(**check_params),
            self._check_words(**check_params)))

    def _get_check_params(self) -> dict:
        file = self._file
        if file.name == "CMakeLists.txt" or file.name == "Doxyfile" or file.suffix == ".cmake":
            return {"mpl_line_idx": 0, "mpl_prefix": "## "}

        if file.suffix == ".md":
            return {
                "mpl_line_idx": 2,
                "mpl_prefix": "// ",
                "empty_line_idx": 1,
                "check_license_words": file.name != "readme.md",
            }

        if file.suffix in {'.h', '.cpp', '.c', '.mm', '.ts', '.js', '.txt', '.inc'}:
            return {"mpl_line_idx": 0, "mpl_prefix": "// "}

        if file.suffix == ".sh":
            return {"mpl_line_idx": 2, "mpl_prefix": "## ", "empty_line_idx": 1}

        if file.suffix == ".bat":
            return {"mpl_line_idx": 0, "mpl_prefix": ":: "}

        return None

    def _check_mpl(self, mpl_line_idx, mpl_prefix, **_) -> List[FileError]:
        expected = mpl_prefix + MPL
        if mpl_line_idx >= len(self._lines):
            # File doesn't contain the line with copyright message.
            return[FileError(
                type=ErrorType.missing_mpl,
                params={"expected": expected},
                line=mpl_line_idx+1,
                column=0)]

        line = self._lines[mpl_line_idx]
        if line != expected:
            return [FileError(
                type=ErrorType.incorrect_mpl,
                params={"line": line, "expected": expected},
                line=mpl_line_idx+1,
                column=0)]

        return []

    def _check_words(self, mpl_line_idx, check_license_words=True, **_) -> List[FileError]:
        def _find_errors_in_line(line_idx, error_type):
            line = self._lines[line_idx]
            regex = CHECK_REGEX_MAP[error_type]
            return [FileError(
                type=error_type,
                params={"word": m.group("word"), "line_number": line_idx+1},
                line=line_idx+1,
                column=m.start("word")) for m in regex.finditer(line)]

        errors = []
        for line_idx in range(0, len(self._lines)):
            if line_idx == mpl_line_idx:  # Don't check mpl line.
                continue
            errors.extend(_find_errors_in_line(line_idx, ErrorType.trademark_violation))
            errors.extend(_find_errors_in_line(line_idx, ErrorType.politeness_violation))
            if not check_license_words:
                continue
            errors.extend(_find_errors_in_line(line_idx, ErrorType.unknown_license))

        return errors

    def _check_empty_line(self, empty_line_idx=None, **_) -> List[FileError]:
        if empty_line_idx is None or empty_line_idx >= len(self._lines):
            return []

        line = self._lines[empty_line_idx]
        if line == '':
            return []

        return [FileError(
            type=ErrorType.missing_empty_line,
            params={"line": line},
            line=empty_line_idx+1,
            column=0)]

    def _check_shebang(self) -> List[FileError]:
        shebang = SHEBANG_SUFFICIES_MAP.get(self._file.suffix, None)
        if shebang is None:
            return []

        line = self._lines[0] if self._lines else ""
        if line == shebang:
            return []

        return[FileError(
            type=ErrorType.unexpected_shebang,
            params={"line": line, "shebang": shebang},
            line=1,
            column=0)]
