
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, NamedTuple, Set, Tuple

from robocat.merge_request_manager import MergeRequestManager
from robocat.note import Note, MessageId


@dataclass(frozen=True)
class CheckError:
    type: str = "generic"
    params: Dict[str, str] = field(hash=False, compare=True, default_factory=dict)


class ErrorCheckResult(NamedTuple):
    must_add_comment: bool
    has_errors: bool
    new_errors: Set[CheckError]


class StoredCheckResults:
    CheckErrorClass = CheckError

    ERROR_MESSAGE_IDS = set()
    OK_MESSAGE_IDS = set()
    UNCHECKABLE_MESSAGE_IDS = set()
    NEEDS_MANUAL_CHECK_MESSAGE_IDS = set()

    def __init__(self, mr_manager: MergeRequestManager):
        checker_message_ids = (
            self.ERROR_MESSAGE_IDS | self.OK_MESSAGE_IDS | self.UNCHECKABLE_MESSAGE_IDS)
        self._current_revision_sha = mr_manager.data.sha
        self._notes = [
            n for n in mr_manager.notes() if n.message_id in checker_message_ids]

    def is_current_revision_checked(self) -> bool:
        return any([n for n in self._notes if n.sha == self._current_revision_sha])

    def does_latest_revision_have_errors(self) -> bool:
        return self._notes and self._notes[-1].message_id in self.ERROR_MESSAGE_IDS

    def have_error(self, error: CheckErrorClass) -> bool:
        return any([
            n for n in self._error_notes()
            if error == self.CheckErrorClass(**n.additional_data)])

    def is_error_actual(self, error: CheckErrorClass) -> bool:
        last_notes_index = len(self._notes) - 1
        ok_note_index = next((
            last_notes_index - i for i, n in enumerate(reversed(self._notes))
            if n.message_id in self.OK_MESSAGE_IDS),
            -1)
        return any([
            n for n in self._error_notes(start_index=ok_note_index + 1)
            if error == self.CheckErrorClass(**n.additional_data)])

    def get_errors(self) -> Dict[MessageId, Set[CheckErrorClass]]:
        result = {}
        for n in self._notes:
            result.setdefault(n.message_id, set()).add(self.CheckErrorClass(**n.additional_data))
        return result

    def _error_notes(self, start_index: int = 0) -> List[Note]:
        return [n for n in self._notes[start_index:] if n.message_id in self.ERROR_MESSAGE_IDS]

    def does_latest_revision_need_manual_check(self) -> bool:
        return self._notes[-1].message_id in self.NEEDS_MANUAL_CHECK_MESSAGE_IDS

    def was_never_checked(self) -> bool:
        return not bool(self._notes)


class CheckChangesMixin(metaclass=ABCMeta):
    def _do_error_check(
            self,
            mr_manager: MergeRequestManager,
            check_results_class: StoredCheckResults) -> ErrorCheckResult:
        old_errors_info = check_results_class(mr_manager)
        if old_errors_info.is_current_revision_checked():
            return ErrorCheckResult(
                must_add_comment=False,
                has_errors=old_errors_info.does_latest_revision_have_errors(),
                new_errors=set())

        has_errors, new_errors = self._find_errors(
            mr_manager=mr_manager, old_errors_info=old_errors_info)

        if old_errors_info.was_never_checked():
            return ErrorCheckResult(
                must_add_comment=True, has_errors=has_errors, new_errors=new_errors)

        had_errors = old_errors_info.does_latest_revision_have_errors()
        if had_errors != has_errors:
            return ErrorCheckResult(
                must_add_comment=True, has_errors=has_errors, new_errors=new_errors)

        needed_manual_check = old_errors_info.does_latest_revision_need_manual_check()
        needs_manual_check = self._is_manual_check_required(mr_manager)
        if needs_manual_check != needed_manual_check:
            return ErrorCheckResult(
                must_add_comment=True, has_errors=has_errors, new_errors=new_errors)

        return ErrorCheckResult(
            must_add_comment=bool(new_errors), has_errors=has_errors, new_errors=new_errors)

    @abstractmethod
    def _find_errors(
            self,
            old_errors_info: StoredCheckResults,
            mr_manager: MergeRequestManager) -> Tuple[bool, Set[CheckError]]:
        return (False, {})

    def _is_manual_check_required(self, mr_manager: MergeRequestManager) -> bool:
        return False

    @staticmethod
    def _is_diff_complete(mr_manager) -> bool:
        return not mr_manager.get_changes().overflow
