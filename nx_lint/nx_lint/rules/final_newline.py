from pathlib import Path
from typing import Iterable

from nx_lint.violation import Violation
from nx_lint.file_cache import FileCache
from nx_lint.utils import is_text_file, is_crlf_file, as_bytes
from nx_lint.constants import LF, CRLF


class FinalNewLineRule:
    """ Files must end with a newline. """
    identifier = "final_newline"

    def check_file(self, file_path: Path, cache: FileCache) -> Iterable[Violation]:
        if not is_text_file(file_path):
            return []

        lines = cache.cached_contents_of(file_path)

        if not lines or not lines[-1]:
            return []

        # This works with both LF and CRLF because LF is always the last.
        if lines[-1][-1] != LF:
            return [
                Violation(
                    file_path=file_path,
                    line=len(lines),
                    column=len(lines[-1]) - 1,
                    offset=None,
                    message=f"The file does not end with a newline.",
                    lint_id=self.identifier)]
        return []

    def can_check(self, file_path: Path) -> bool:
        return True

    def can_fix(self, file_path: Path) -> bool:
        return True

    def fix_file(self, file_path: Path, cache: FileCache) -> None:
        newline = CRLF if is_crlf_file(file_path) else as_bytes(LF)
        with file_path.open("ab") as file:
            file.write(newline)
