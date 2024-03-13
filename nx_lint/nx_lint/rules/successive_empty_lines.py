## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from pathlib import Path
from typing import Iterable

from nx_lint.violation import Violation
from nx_lint.file_cache import FileCache
from nx_lint.utils import is_empty


class SuccessiveEmptyLinesRule:
    """ No two or more successive empty lines in the file contents. """
    identifier = "successive_empty_lines"

    def check_file(self, file_path: Path, cache: FileCache) -> Iterable[Violation]:
        results = []

        empty_count = 0
        for line_number, line in cache.lines_of(file_path):
            if is_empty(line):
                empty_count += 1
            elif empty_count > 1:
                results.append(
                    Violation(
                        file_path=file_path,
                        line=line_number - empty_count,
                        column=0,
                        offset=None,
                        message=f"Two or more successive empty lines in the file.",
                        lint_id=self.identifier))
                empty_count = 0
            else:
                empty_count = 0

        return results

    def can_check(self, file_path: Path) -> bool:
        return True

    def can_fix(self, file_path: Path) -> bool:
        return False

    def fix_file(self, file_path: Path, cache: FileCache) -> None:
        pass
