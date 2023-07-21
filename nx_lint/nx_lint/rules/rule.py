from pathlib import Path
from typing import Protocol, Iterable

from nx_lint.file_cache import FileCache
from nx_lint.violation import Violation


class Rule(Protocol):
    # A unique identifier for this rule.
    identifier: str

    def check_file(self, file_path: Path, cache: FileCache) -> Iterable[Violation]:
        ...

    def can_check(self, file_path: Path) -> bool:
        ...

    def can_fix(self, file_path: Path) -> bool:
        ...

    def fix_file(self, file_path: Path, cache: FileCache) -> None:
        ...
