from pathlib import Path
from typing import Iterable

from nx_lint.violation import Violation
from nx_lint.file_cache import FileCache
from nx_lint.constants import SPACE, TAB, LF, DEL, CR
from nx_lint.utils import escape_char, is_crlf_file


class ControlCharactersRule:
    """ ASCII control characters must not be used in source code. CR, LF and TAB are not checked
        by this rule.
    """
    identifier = "control_chars"

    def check_file(self, file_path: Path, cache: FileCache) -> Iterable[Violation]:
        results = []
        for line_number, line in cache.lines_of(file_path):
            if not line or len(line) < 2:
                continue

            for column, c in enumerate(line):
                if ((0 <= c < SPACE) or c == DEL) and c not in (LF, TAB):
                    # If we find a CR character, we need to check if it is followed by an LF
                    # because we don't want to report CR as a control character if the file is
                    # using CRLF line endings.
                    if is_crlf_file(file_path):
                        if c == CR and column + 1 < len(line) and line[column + 1] == LF:
                            continue
                    escaped = escape_char(chr(c))
                    results.append(
                        Violation(
                            file_path=file_path,
                            line=line_number,
                            column=column,
                            offset=None,
                            message=f"Control character {escaped}.",
                            lint_id=self.identifier))

        return results

    def can_check(self, file_path: Path) -> bool:
        return True

    def can_fix(self, file_path: Path) -> bool:
        return False

    def fix_file(self, file_path: Path, cache: FileCache) -> None:
        pass
