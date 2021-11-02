
from dataclasses import dataclass, field
from typing import Dict, List, NamedTuple, Optional, Set

from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId, Note


@dataclass(frozen=True)
class CheckError:
    type: str
    raw_text: str
    params: Dict[str, str] = field(compare=False)


class ErrorCheckResult(NamedTuple):
    must_add_comment: bool
    has_errors: bool
    new_errors: Set[CheckError]


class PreviousCheckResults:
    CHECK_ERROR_CLASS = CheckError

    ERROR_MESSAGE_IDS = {}
    OK_MESSAGE_IDS = {}
    UNCHECKABLE_MESSAGE_IDS = {}
    NEEDS_MANUAL_CHECK_MESSAGE_IDS = {}

    def __init__(self, mr_manager: MergeRequestManager):
        checker_message_ids = (
            self.ERROR_MESSAGE_IDS | self.OK_MESSAGE_IDS | self.UNCHECKABLE_MESSAGE_IDS)
        self._current_revision_sha = mr_manager.data.sha
        self._notes = [
            n for n in mr_manager.notes() if n.message_id in checker_message_ids]

    def is_current_revision_checked(self) -> bool:
        return any([n for n in self._notes if n.sha == self._current_revision_sha])

    def is_current_revision_checked(self) -> bool:
        return any([n for n in self._notes if n.sha == self._current_revision_sha])

    def does_latest_revision_have_errors(self) -> Optional[bool]:
        if not self._notes:
            return None
        return self._notes[-1].message_id in self.ERROR_MESSAGE_IDS

    def have_error(self, error: CHECK_ERROR_CLASS) -> bool:
        return any([
            n for n in self._error_notes()
            if error == self.CHECK_ERROR_CLASS(**n.additional_data)])

    def _error_notes(self) -> List[Note]:
        return [n for n in self._notes if n.message_id in self.ERROR_MESSAGE_IDS]

    def does_latest_revision_need_manual_check(self) -> Optional[bool]:
        if not self._notes:
            return None
        return self._notes[-1].message_id in self.NEEDS_MANUAL_CHECK_MESSAGE_IDS
