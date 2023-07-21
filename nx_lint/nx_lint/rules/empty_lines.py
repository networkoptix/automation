from pathlib import Path
from typing import Iterable

from nx_lint.violation import Violation
from nx_lint.file_cache import FileCache
from nx_lint.constants import TAB, SPACE, CR, LF


def _is_empty(line: bytes) -> bool:
    return not line or all(c in (TAB, SPACE, CR, LF) for c in line)


def _leading_empty_lines(file_path: Path, cache: FileCache) -> int:
    count = 0
    for _, line in cache.lines_of(file_path):
        if not _is_empty(line):
            break
        count += 1
    return count


def _trailing_empty_lines(file_path: Path, cache: FileCache) -> int:
    count = 0
    all_lines = list(cache.lines_of(file_path))
    for _, line in reversed(all_lines):
        if not _is_empty(line):
            break
        count += 1
    return count


class EmptyLinesRule:
    """ Files must not have leading or trailing empty lines. """
    identifier = "empty_lines"

    def check_file(self, file_path: Path, cache: FileCache) -> Iterable[Violation]:
        results = []

        count = _leading_empty_lines(file_path, cache)
        if count > 0:
            results.append(
                Violation(
                    file_path=file_path,
                    line=1,
                    column=0,
                    offset=None,
                    message=f"Leading empty line(s) in file.",
                    lint_id=self.identifier))

        count = _trailing_empty_lines(file_path, cache)
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
        leading = _leading_empty_lines(file_path, cache)
        trailing = _trailing_empty_lines(file_path, cache)
        with file_path.open("wb") as file:
            file.writelines(lines[leading:len(lines) - trailing])
