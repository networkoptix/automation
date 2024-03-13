## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from pathlib import Path
from typing import Iterable

from nx_lint.violation import Violation
from nx_lint.file_cache import FileCache
from nx_lint.utils import is_crlf_file, is_tab_or_space, as_bytes
from nx_lint.constants import LF, CRLF


def _has_trailing_whitespace(line: bytes) -> bool:
    if line.endswith(as_bytes(LF)):
        return is_tab_or_space(line[-2])
    elif line.endswith(CRLF):
        return is_tab_or_space(line[-3])
    return is_tab_or_space(line[-1])


class TrailingWhitespaceRule:
    """ Lines must not have trailing whitespace. """
    identifier = "trailing_whitespace"

    def check_file(self, file_path: Path, cache: FileCache) -> Iterable[Violation]:
        results = []
        for line_number, line in cache.lines_of(file_path):
            if not line or len(line) < 2:
                continue

            if _has_trailing_whitespace(line):
                results.append(
                    Violation(
                        file_path=file_path,
                        line=line_number,
                        column=len(line) - 2,
                        offset=None,
                        message=f"Trailing whitespace.",
                        lint_id=self.identifier))

        return results

    def can_check(self, file_path: Path) -> bool:
        return True

    def can_fix(self, file_path: Path) -> bool:
        return True

    def fix_file(self, file_path: Path, cache: FileCache) -> None:
        from nx_lint.utils import split_lines
        newline = CRLF if is_crlf_file(file_path) else as_bytes(LF)
        skip = False
        # Read the file from disk instead of using the cache, because multiple fixes may be
        # applied.
        file_lines = split_lines(file_path.open("rb").read())
        with file_path.open("wb") as file:
            for line in file_lines:
                # TODO: #tszelei Consider removing the ability to skip lines.
                if b"nx_lint: off" in line:
                    skip = True
                if skip:
                    file.write(line)
                    if b"nx_lint: on" in line:
                        skip = False
                    continue
                stripped = line.rstrip()
                if line.endswith((as_bytes(LF), CRLF)):
                    file.write(stripped + newline)
                else:
                    file.write(stripped)
