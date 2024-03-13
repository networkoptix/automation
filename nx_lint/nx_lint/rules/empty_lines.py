## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from pathlib import Path
from typing import Iterable

from nx_lint.violation import Violation
from nx_lint.file_cache import FileCache
from nx_lint.utils import is_empty


def _leading_empty_lines(file_path: Path, lines: list[bytes]) -> int:
    count = 0
    for line in lines:
        if not is_empty(line):
            break
        count += 1
    return count


def _trailing_empty_lines(file_path: Path, lines: list[bytes]) -> int:
    count = 0
    for line in reversed(lines):
        if not is_empty(line):
            break
        count += 1
    return count


class EmptyLinesRule:
    """ Files must not have leading or trailing empty lines. """
    identifier = "empty_lines"

    def check_file(self, file_path: Path, cache: FileCache) -> Iterable[Violation]:
        results = []

        lines = [line for _, line in cache.lines_of(file_path)]
        count = _leading_empty_lines(file_path, lines)
        if count > 0:
            results.append(
                Violation(
                    file_path=file_path,
                    line=1,
                    column=0,
                    offset=None,
                    message=f"Leading empty line(s) in file.",
                    lint_id=self.identifier))

        count = _trailing_empty_lines(file_path, lines)
        if count > 0:
            results.append(
                Violation(
                    file_path=file_path,
                    line=len(cache.cached_contents_of(file_path)),
                    column=0,
                    offset=None,
                    message=f"Trailing empty line(s) in file.",
                    lint_id=self.identifier))

        return results

    def can_check(self, file_path: Path) -> bool:
        return True

    def can_fix(self, file_path: Path) -> bool:
        return True

    def fix_file(self, file_path: Path, cache: FileCache) -> None:
        from nx_lint.utils import split_lines
        lines = list(split_lines(file_path.open("rb").read()))
        leading = _leading_empty_lines(file_path, lines)
        trailing = _trailing_empty_lines(file_path, lines)
        with file_path.open("wb") as file:
            file.writelines(lines[leading:len(lines) - trailing])
