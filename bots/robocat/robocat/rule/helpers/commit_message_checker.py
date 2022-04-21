from dataclasses import dataclass
from typing import List, Set, Tuple

from robocat.rule.helpers.statefull_checker_helpers import CheckError
import source_file_compliance


@dataclass(frozen=True)
class CommitMessageError(CheckError):
    raw_text: str = ""


FindErrorsResult = Tuple[bool, Set[CommitMessageError]]


def commit_message_errors(commit_message: str) -> List[CheckError]:
    result = []
    for raw_error in source_file_compliance.check_text(commit_message):
        error_type = f"{raw_error.reason}_word"
        error_text = (
            "This commit seems to contain licensing-related or other sensitive functionality: "
            f"commit message contains `{raw_error.word}` (stem `{raw_error.stem}`) at "
            f"line {raw_error.line}:{raw_error.col}. Some of the open-source keepers must "
            "review this commit before it can be merged.")
        result.append(CommitMessageError(type=error_type, raw_text=error_text))

    return result
