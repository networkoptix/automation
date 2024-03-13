## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from pathlib import Path
from typing import Iterable

from nx_lint.violation import Violation
from nx_lint.file_cache import FileCache


class UnderscoreSeparatorRule:
    """ Filenames must use underscores for word separators. """
    identifier = "underscore_separator"

    def check_file(self, file_path: Path, cache: FileCache) -> Iterable[Violation]:
        results = []
        if '-' in file_path.name:
            results.append(
                Violation(
                    file_path,
                    line=None,
                    column=None,
                    offset=None,
                    message="File name contains '-' as word separator instead of '_'.",
                    lint_id=self.identifier))
        return results

    def can_check(self, file_path: Path) -> bool:
        return True

    def can_fix(self, file_path: Path) -> bool:
        return False

    def fix_file(self, file_path: Path, cache: FileCache) -> None:
        pass
