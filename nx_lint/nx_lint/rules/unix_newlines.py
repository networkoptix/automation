from pathlib import Path
from typing import Iterable

from nx_lint.violation import Violation
from nx_lint.file_cache import FileCache
from nx_lint.utils import is_crlf_file, as_bytes
from nx_lint.constants import CR, LF, CRLF


class UnixNewlinesRule:
    """ Files must use Unix newlines (0x0A aka LF). """
    identifier = "unix_newlines"

    def check_file(self, file_path: Path, cache: FileCache) -> Iterable[Violation]:
        results = []
        if not is_crlf_file(file_path):
            for line_number, line in cache.lines_of(file_path):
                if not line or len(line) < 2:
                    continue

                if line.endswith((CRLF, as_bytes(CR))):
                    results.append(
                        Violation(
                            file_path=file_path,
                            line=line_number,
                            column=len(line) - 1,
                            offset=None,
                            message=f"Non-Unix newline.",
                            lint_id=self.identifier))

        return results

    def can_check(self, file_path: Path) -> bool:
        return True

    def can_fix(self, file_path: Path) -> bool:
        return True

    def fix_file(self, file_path: Path, cache: FileCache) -> None:
        from nx_lint.utils import split_lines
        # Read the file from disk instead of using the cache, because multiple fixes may be
        # applied.
        file_lines = split_lines(file_path.open("rb").read())
        with file_path.open("wb") as file:
            for line in file_lines:
                if line.endswith(CRLF):
                    file.write(line[:-2] + as_bytes(LF))
                elif line.endswith(as_bytes(CR)):
                    file.write(line[:-1] + as_bytes(LF))
                else:
                    file.write(line)
