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
            f'Error at {raw_error.line}:{raw_error.col}: {raw_error.reason} '
            f'word "{raw_error.word}"')
        result.append(CommitMessageError(type=error_type, raw_text=error_text))

    return result
