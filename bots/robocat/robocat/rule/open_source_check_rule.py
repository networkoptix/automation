import logging
from typing import List, Dict
from dataclasses import dataclass
from enum import Enum

from robocat.merge_request_manager import MergeRequestManager, ApprovalRequirements
from robocat.rule.base_rule import BaseRule, RuleExecutionResult
from robocat.rule.helpers.open_source_file_checker import OpenSourceFileChecker, FileError
from robocat.award_emoji_manager import AwardEmojiManager
import robocat.comments

logger = logging.getLogger(__name__)


class OpenSourceCheckRuleExecutionResult(RuleExecutionResult, Enum):
    merged = "MR is already merged"
    merge_authorized = "MR is approved by the authorized approver"
    no_commits = "No commits"
    work_in_progress = "Work in progress"
    not_applicable = "No changes in open source files"
    files_not_ok = (
        "Open source files do not comply to the requirements, or change list is too large")
    manual_check_required = (
        "Open source rule check didn't find any problems; manual check is required")
    no_manual_check_required = (
        "Open source rule check didn't find any problems; no manual check is required")

    def __bool__(self):
        return self in [
            self.not_applicable, self.merge_authorized, self.merged, self.no_manual_check_required]


@dataclass(frozen=True)
class ErrorLocation:
    file: str
    line: int
    column: int


class CheckResultsCache:
    def __init__(self):
        self._errors_by_mr = dict()  # Map merge request ids to error set for these merge requests.
        self._does_commit_have_errors = dict()
        self._does_commit_need_manual_check = dict()

        # Comments are added only if the last check revealed new errors OR it is the first check
        # and there are no errors. This variable must be set to False (via setter must_add_comment)
        # after adding the related comments to the merge request.
        self._must_add_comment = False
        self._new_errors = dict()

    def is_last_mr_commit_checked(self, mr_manager: MergeRequestManager) -> bool:
        return mr_manager.data.sha in self._does_commit_have_errors

    def ensure_error(self, mr_manager: MergeRequestManager, file: str, error: FileError) -> None:
        error_location = ErrorLocation(file=file, line=error.line, column=error.column)
        if self._has_error_at(mr_manager, error_location):  # Don't add the same error twice.
            return

        self._new_errors[error_location] = error
        self._does_commit_have_errors[mr_manager.data.sha] = True
        self._does_commit_need_manual_check[mr_manager.data.sha] = True
        self._must_add_comment = True
        self._update_mr_errors(mr_manager.data.id, error_location)

    def _has_error_at(self, mr_manager: MergeRequestManager, location: ErrorLocation) -> bool:
        mr_results = self._errors_by_mr.get(mr_manager.data.id, set())
        return location in mr_results

    def _update_mr_errors(self, mr_id: int, error_location: ErrorLocation = None):
        if mr_id not in self._errors_by_mr:
            self._errors_by_mr[mr_id] = set()
        if error_location is not None:
            self._errors_by_mr[mr_id].add(error_location)

    def ensure_no_errors(
            self, mr_manager: MergeRequestManager, needs_manual_check: bool = True) -> None:
        self._does_commit_have_errors[mr_manager.data.sha] = False
        self._does_commit_need_manual_check[mr_manager.data.sha] = needs_manual_check
        if not self._has_mr_ever_been_checked(mr_manager):
            self._must_add_comment = True
        self._update_mr_errors(mr_manager.data.id)

    def _has_mr_ever_been_checked(self, mr_manager: MergeRequestManager) -> bool:
        return mr_manager.data.id in self._errors_by_mr

    def does_last_mr_commit_have_errors(self, mr_manager: MergeRequestManager) -> bool:
        return self._does_commit_have_errors.get(mr_manager.data.sha, None)

    def does_last_mr_commit_require_manual_check(self, mr_manager: MergeRequestManager) -> bool:
        return self._does_commit_need_manual_check.get(mr_manager.data.sha, None)

    def get_new_errors(self) -> Dict[ErrorLocation, FileError]:
        return self._new_errors

    @property
    def must_add_comment(self):
        return self._must_add_comment

    @must_add_comment.setter
    def must_add_comment(self, value):
        if not value:
            self._new_errors = dict()
        self._must_add_comment = value


class OpenSourceCheckRule(BaseRule):
    def __init__(self, project_manager, approver_username: str, approver_name: str = None):
        # NOTE: Potentially we have memory leak here - cache is never cleaned up.
        # TODO: Add cache cleanup.
        self._file_check_results_cache = CheckResultsCache()
        self._open_source_approver = approver_username
        self._open_source_approver_name = approver_name if approver_name else approver_username
        logger.info(
            "Open source rule created. Authorized approver is "
            f"{self._open_source_approver} ({self._open_source_approver_name})")
        self._project_manager = project_manager
        super().__init__()

    def execute(self, mr_manager: MergeRequestManager) -> OpenSourceCheckRuleExecutionResult:
        logger.debug(f"Executing check open sources rule on {mr_manager}...")

        mr_data = mr_manager.data
        if mr_data.is_merged:
            return OpenSourceCheckRuleExecutionResult.merged

        if not mr_data.has_commits:
            return OpenSourceCheckRuleExecutionResult.no_commits

        if mr_data.work_in_progress:
            return OpenSourceCheckRuleExecutionResult.work_in_progress

        if self._is_diff_complete(mr_manager) and not self._changed_open_source_files(mr_manager):
            return OpenSourceCheckRuleExecutionResult.not_applicable

        self._update_file_check_results_cache(mr_manager)

        if not self._is_manual_check_required(mr_manager):
            self._ensure_no_manual_check_required_comment(mr_manager)
            return OpenSourceCheckRuleExecutionResult.no_manual_check_required

        approval_requirements = ApprovalRequirements(
            mandatory_approvers=set([self._open_source_approver]))
        if mr_manager.satisfies_approval_requirements(approval_requirements):
            return OpenSourceCheckRuleExecutionResult.merge_authorized

        if mr_manager.ensure_assignee(
                self._open_source_approver, increase_needed_approvals_count=True):
            logger.debug("Authorized approver assigned to MR.")

        if self._are_problems_found(mr_manager):
            self._ensure_problems_are_found_comment(mr_manager)
            return OpenSourceCheckRuleExecutionResult.files_not_ok

        self._ensure_manual_check_required_comment(mr_manager)
        return OpenSourceCheckRuleExecutionResult.manual_check_required

    @staticmethod
    def _is_diff_complete(mr_manager) -> bool:
        return not mr_manager.get_changes().overflow

    @staticmethod
    def _changed_open_source_files(mr_manager) -> List[str]:
        changes = mr_manager.get_changes()
        open_source_files = [
            c["new_path"] for c in changes.changes
            if not c["deleted_file"] and OpenSourceFileChecker.is_check_needed(c["new_path"])]
        return open_source_files

    def _update_file_check_results_cache(self, mr_manager: MergeRequestManager):
        cache = self._file_check_results_cache
        if cache.is_last_mr_commit_checked(mr_manager):
            return

        # Check files for the first time OR after a new commit added to the merge request OR
        # the merge request was ammended OR the merge request was rebased.
        has_errors = False
        for file_name in self._changed_open_source_files(mr_manager):
            # TODO: Before reading file, check what is it. No need to read files that we are not
            # intended to check (i.e. *.png files).
            file_content = self._project_manager.file_get_content(
                sha=mr_manager.data.sha, file=file_name)
            file_checker = OpenSourceFileChecker(file_name=file_name, file_content=file_content)
            for error in file_checker.file_errors():
                has_errors = True
                cache.ensure_error(mr_manager, file=file_name, error=error)

        if not has_errors:
            cache.ensure_no_errors(mr_manager, self._has_new_open_source_files(mr_manager))

    @staticmethod
    def _has_new_open_source_files(mr_manager) -> bool:
        changes = mr_manager.get_changes()
        new_paths = [c["new_path"] for c in changes.changes if c["new_file"] or c["renamed_file"]]
        return any(p for p in new_paths if OpenSourceFileChecker.is_check_needed(p))

    def _is_manual_check_required(self, mr_manager: MergeRequestManager) -> bool:
        if not self._is_diff_complete(mr_manager):
            return True

        cache = self._file_check_results_cache
        return cache.does_last_mr_commit_require_manual_check(mr_manager)

    def _ensure_no_manual_check_required_comment(self, mr_manager: MergeRequestManager):
        if not self._file_check_results_cache.must_add_comment:
            return

        mr_manager.create_thread(
            title="Auto-check for open source changes passed",
            message=robocat.comments.has_unimportant_changes_in_open_source,
            emoji=AwardEmojiManager.AUTOCHECK_OK_EMOJI,
            autoresolve=True)
        self._file_check_results_cache.must_add_comment = False

    def _are_problems_found(self, mr_manager: MergeRequestManager) -> bool:
        if not self._is_diff_complete(mr_manager):
            return True

        cache = self._file_check_results_cache
        return cache.does_last_mr_commit_have_errors(mr_manager)

    def _ensure_problems_are_found_comment(self, mr_manager: MergeRequestManager):
        if not self._file_check_results_cache.must_add_comment:
            return

        if not self._is_diff_complete(mr_manager):
            mr_manager.create_thread(
                title="Can't auto-check open source changes",
                message=robocat.comments.may_have_changes_in_open_source.format(
                    approver=self._open_source_approver),
                emoji=AwardEmojiManager.AUTOCHECK_IMPOSSIBLE_EMOJI)
            self._file_check_results_cache.must_add_comment = False
            return

        cache = self._file_check_results_cache
        for error_location, error in cache.get_new_errors().items():
            self._create_open_source_discussion(mr_manager, error_location.file, error)
        self._file_check_results_cache.must_add_comment = False

    def _ensure_manual_check_required_comment(self, mr_manager: MergeRequestManager):
        if not self._file_check_results_cache.must_add_comment:
            return

        mr_manager.create_thread(
            title="Auto-check for open source changes passed",
            message=robocat.comments.has_good_changes_in_open_source.format(
                approver=self._open_source_approver),
            emoji=AwardEmojiManager.AUTOCHECK_OK_EMOJI)
        self._file_check_results_cache.must_add_comment = False

    def _create_open_source_discussion(
            self, mr_manager: MergeRequestManager, file: str, error: FileError):
        title = "Autocheck for open source changes failed"
        message = robocat.comments.has_bad_changes_in_open_source.format(
            error_message=robocat.comments.__dict__[str(error.type)].format(**error.params),
            approver=self._open_source_approver)

        discussion_created = mr_manager.create_thread(
            title=title,
            message=message,
            emoji=AwardEmojiManager.AUTOCHECK_FAILED_EMOJI,
            file=file, line=error.line)

        # If the API call failed to create discussion bonded to the file and line number, we are
        # creating the discussion that is not bonded to the concrete position. TODO: Fix this
        # behavior. We must find the way to reliably create discussion, bonded to the file and line
        # number. See also comment in merge_request.py, function create_discussion().
        if not discussion_created:
            mr_manager.create_thread(
                title=title,
                message=f'Problem in file "{file}": {message}',
                emoji=AwardEmojiManager.AUTOCHECK_FAILED_EMOJI)
