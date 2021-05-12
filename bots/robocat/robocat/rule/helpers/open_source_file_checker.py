import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional

import source_file_compliance

# Paths configuration.
OPENSOURCE_ROOTS = ("open", "open_candidate")
EXCLUDED_DIRS = {
    "open/artifacts/nx_kit/src/json11",
    "open/licenses",
    "open_candidate/artifacts",
}
EXCLUDED_FILE_PATHS = {"open/readme.md"}
# go.mod and go.sum are auto-generated, so they do not need to be checked.
EXCLUDED_FILE_NAME_PATTERNS = {
    "go.mod", "go.sum", "*.json", "*.pyc", "*.bmp", "*.gif", "*.mkv", "*.avi", "*.png", "*.jpg",
    "*.jpeg", "*.svg", "*.ui", "*.ts"
}


@dataclass(frozen=True)
class FileError:
    type: str
    raw_text: str
    file: str
    params: Dict[str, str] = field(compare=False)
    line: Optional[int] = None


class OpenSourceFileChecker:
    def __init__(self, file_name: str, file_content: str):
        self._file_path = Path(file_name)
        self._file_content = file_content

    @staticmethod
    def is_check_needed(file_path: str, consider_directory_context: bool = True):
        if consider_directory_context:
            if not any(file_path.startswith(f"{d}/") for d in OPENSOURCE_ROOTS):
                return False

            if any(d for d in EXCLUDED_DIRS if file_path.startswith(f"{d}/")):
                return False

            if file_path in EXCLUDED_FILE_PATHS:
                return False

        file_path_object = Path(file_path)
        for pattern in EXCLUDED_FILE_NAME_PATTERNS:
            if file_path_object.match(pattern):
                return False

        return True

    def file_errors(self) -> List[FileError]:
        result = []
        raw_errors = source_file_compliance.check_file_content(self._file_path, self._file_content)
        for raw_error in raw_errors:
            raw_error_type = type(raw_error)
            if raw_error_type == source_file_compliance.WordError:
                error_type = f"{raw_error.reason}_word"
                error_params = {
                    "word": raw_error.word,
                    "position": f"{raw_error.path!s}:{raw_error.line}",
                }
            elif raw_error_type == source_file_compliance.LineError:
                error_type = "line"
                actual_line = raw_error.actual if str(raw_error.actual) else "<empty line>"
                expected_line = raw_error.expected if str(raw_error.expected) else "<empty line>"
                error_params = {
                    "actual": actual_line,
                    "expected": expected_line,
                    "position": f"{raw_error.path!s}:{raw_error.line}",
                }
            elif raw_error_type == source_file_compliance.FileError:
                error_type = "file_type"
                error_params = {"file": str(raw_error.path)}
            else:
                assert False, f"Bad raw error type: {raw_error_type!r}"

            error_line = raw_error.line if hasattr(raw_error, 'line') else None
            result.append(FileError(
                type=error_type, params=error_params,
                line=error_line, file=str(raw_error.path), raw_text=repr(raw_error)))

        return result
