## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/


from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field

from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId


@dataclass(frozen=True)
class CheckError:
    type: str = "generic"
    params: dict[str, str] = field(hash=False, compare=True, default_factory=dict)


class ErrorCheckResult:
    def __init__(
            self,
            current_errors: set[CheckError],
            old_errors: set[CheckError],
            is_first_check: bool = False):
        self.current_errors = current_errors
        self.old_errors = old_errors
        self.new_errors = current_errors - old_errors
        self.is_first_check = is_first_check

    def has_error_of_type(self, error_type: str) -> bool:
        return any(e for e in self.current_errors if e.type == error_type)

    @property
    def has_changed_since_last_check(self) -> bool:
        return self.is_first_check or (self.current_errors != self.old_errors)


class StoredCheckResults:
    CheckErrorClass = CheckError

    MESSAGE_IDS = set()
    OK_MESSAGE_IDS = set()

    def __init__(self, mr_manager: MergeRequestManager):
        self._current_revision_sha = mr_manager.data.sha
        self._issue_notes = []
        self._last_checked_revision_sha = None
        for n in mr_manager.notes():
            if n.message_id not in self.MESSAGE_IDS:
                continue
            if n.message_id in self.OK_MESSAGE_IDS:
                self._issue_notes = []
            else:
                self._issue_notes.append(n)
            self._last_checked_revision_sha = n.sha

    def is_current_revision_checked(self) -> bool:
        return self._current_revision_sha == self._last_checked_revision_sha

    def get_errors(self) -> dict[MessageId, set[CheckErrorClass]]:
        result = {}
        for n in self._issue_notes:
            result.setdefault(n.message_id, set()).add(self.CheckErrorClass(**n.additional_data))
        return result

    def has_errors(self) -> bool:
        return bool(self._issue_notes)

    def was_never_checked(self) -> bool:
        return self._last_checked_revision_sha is None


class CheckChangesMixin(metaclass=ABCMeta):
    def _do_error_check(
            self,
            mr_manager: MergeRequestManager,
            check_results_class: StoredCheckResults) -> ErrorCheckResult:
        old_errors_info = check_results_class(mr_manager)
        old_errors = set()
        for errors in old_errors_info.get_errors().values():
            old_errors.update(errors)

        if old_errors_info.is_current_revision_checked():
            return ErrorCheckResult(old_errors=old_errors, current_errors=old_errors)

        current_errors = self._find_errors(mr_manager=mr_manager)

        if old_errors_info.was_never_checked():
            return ErrorCheckResult(
                is_first_check=True, old_errors=set(), current_errors=current_errors)

        return ErrorCheckResult(old_errors=old_errors, current_errors=current_errors)

    @abstractmethod
    def _find_errors(
            self,
            old_errors_info: StoredCheckResults,
            mr_manager: MergeRequestManager) -> tuple[bool, set[CheckError]]:
        return (False, {})

    @staticmethod
    def _is_diff_complete(mr_manager) -> bool:
        return not mr_manager.get_changes().overflow
