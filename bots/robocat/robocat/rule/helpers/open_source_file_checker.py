from pathlib import Path
from dataclasses import dataclass
from typing import Generator, List, Optional, Set

import source_file_compliance
from robocat.merge_request_manager import MergeRequestManager
from robocat.rule.helpers.statefull_checker_helpers import CheckError


@dataclass(frozen=True)
class FileError(CheckError):
    file: str = ""
    raw_text: str = ""
    line: Optional[int] = None


FileErrors = Set[FileError]


def file_errors(file_name: str, file_content: str) -> List[FileError]:
    result = []
    raw_errors = source_file_compliance.check_file_content(Path(file_name), file_content)
    for raw_error in raw_errors:
        raw_error_type = type(raw_error)
        if raw_error_type == source_file_compliance.WordError:
            error_type = f"{raw_error.reason}_word"
            error_params = {
                "word": raw_error.word,
                "stem": raw_error.stem,
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


def is_check_needed(file_path: str):
    return source_file_compliance.is_check_needed(
        path=file_path,
        repo_config=source_file_compliance.repo_configurations["vms"])


def changed_open_source_files(mr_manager: MergeRequestManager) -> Generator[str, None, None]:
    changes = mr_manager.get_changes()
    return (
        c["new_path"] for c in changes.changes
        if not c["deleted_file"] and is_check_needed(c["new_path"]))


def affected_open_source_files(mr_manager: MergeRequestManager) -> Generator[str, None, None]:
    changes = mr_manager.get_changes()
    # Include deleted/moved files.
    return (c["new_path"] for c in changes.changes if is_check_needed(c["new_path"]))
