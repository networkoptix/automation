from pathlib import Path
from typing import Iterable

from nx_lint.violation import Violation
from nx_lint.file_cache import FileCache


class UnicodeCharactersRule:
    """ Unicode characters must not be used in source code. """
    identifier = "unicode_chars"

    def check_file(self, file_path: Path, cache: FileCache) -> Iterable[Violation]:
        results = []
        for line_number, line in cache.lines_of(file_path):
            if not line or len(line) < 2:
                continue

            for column, c in enumerate(line):
                if 0x80 <= c <= 0xFF:
                    results.append(
                        Violation(
                            file_path=file_path,
                            line=line_number,
                            column=column,
                            offset=None,
                            message=f"Non-ASCII character 0x{c:X}.",
                            lint_id=self.identifier))
        return results

    def can_check(self, file_path: Path) -> bool:
        return True

    def can_fix(self, file_path: Path) -> bool:
        return True

    def fix_file(self, file_path: Path, cache: FileCache) -> None:
        pass
