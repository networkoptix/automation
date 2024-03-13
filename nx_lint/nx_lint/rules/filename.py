## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from pathlib import Path
from typing import Iterable

from nx_lint.violation import Violation
from nx_lint.file_cache import FileCache
from nx_lint.utils import escape_unicode_char

WINDOWS_INCOMPATIBLE_CHARS = r'<>:"/\|?*'
WINDOWS_INCOMPATIBLE_NAMES = (
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{i}" for i in range(10)),
    *(f"lpt{i}" for i in range(10)),
)
# This set of characters was obtained by collecting all filenames at the time of writing. It might
# be amended in the future.
ACCEPTABLE_CHARACTERS = set(
    r"-.0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ@_abcdefghijklmnopqrstuvwxyz{}")


class FileNameRule:
    """ Filenames must not contain non-printable characters, characters that are incompatible with
        Windows, and spaces. """
    identifier = "filename"

    def check_file(self, file_path: Path, cache: FileCache) -> Iterable[Violation]:
        results = []
        if any(c not in ACCEPTABLE_CHARACTERS for c in file_path.stem):
            bad_chars = ", ".join(
                f"'{escape_unicode_char(c)}'"
                for c in sorted(set(file_path.stem) - ACCEPTABLE_CHARACTERS))
            results.append(
                Violation(
                    # TODO: #tszelei We are printing a potentially non-ASCII filename here.
                    # We should consider escaping it. On the other hand, other tools don't do this
                    # and it might be hard to identify the filename if it contains many non-ASCII
                    # characters. If we decide to escape the filename, it should be done in the
                    # Linter class, such that it affects all rules, not just this one.
                    file_path=file_path,
                    line=None,
                    column=None,
                    offset=None,
                    message=f"Prohibited characters in the file name: {bad_chars}.",
                    lint_id=self.identifier))

        if file_path.name.lower() in WINDOWS_INCOMPATIBLE_NAMES:
            results.append(
                Violation(
                    file_path=file_path,
                    line=None,
                    column=None,
                    offset=None,
                    message=f"File name is incompatible with Windows.",
                    lint_id=self.identifier))

        return results

    def can_check(self, file_path: Path) -> bool:
        return True

    def can_fix(self, file_path: Path) -> bool:
        return False

    def fix_file(self, file_path: Path, cache: FileCache) -> None:
        pass
