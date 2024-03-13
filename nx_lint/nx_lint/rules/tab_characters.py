## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from pathlib import Path
from typing import Iterable

from nx_lint.violation import Violation
from nx_lint.file_cache import FileCache
from nx_lint.constants import TAB


class TabCharactersRule:
    """ Tab characters must not be used in source code. """
    identifier = "tab_chars"

    def check_file(self, file_path: Path, cache: FileCache) -> Iterable[Violation]:
        results = []
        for line_number, line in cache.lines_of(file_path):
            if not line or len(line) < 2:
                continue

            for column, c in enumerate(line):
                if c == TAB:
                    results.append(
                        Violation(
                            file_path=file_path,
                            line=line_number,
                            column=column,
                            offset=None,
                            message=f"Tab character.",
                            lint_id=self.identifier))

        return results

    def can_check(self, file_path: Path) -> bool:
        return True

    def can_fix(self, file_path: Path) -> bool:
        return False

    def fix_file(self, file_path: Path, cache: FileCache) -> None:
        pass
