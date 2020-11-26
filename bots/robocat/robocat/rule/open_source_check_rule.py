import logging
from typing import List
from dataclasses import dataclass
from enum import Enum

from robocat.merge_request_manager import MergeRequestManager, ApprovalRequirements
from robocat.rule.base_rule import BaseRule, RuleExecutionResult
from robocat.rule.helpers.open_source_file_checker import OpenSourceFileChecker, FileError
from robocat.award_emoji_manager import AwardEmojiManager
import robocat.comments

logger = logging.getLogger(__name__)


class OpenSourceCheckRuleExecutionResult(RuleExecutionResult, Enum):
    NoCommits = "No commits"
    WorkInProgress = "Work in progress"
    NotApplicable = "No changes in open source files"
    MergeAuthorized = "MR is approved by the authorized approver"
    FilesNotOk = "Open source files are not complied with the requirements"
    NotAuthorized = (
        "Open source rule check didn't find any problems, "
        f"but MR is not approved by the authorized approver")

    def __bool__(self):
        return self in [self.NotApplicable, self.MergeAuthorized]


@dataclass(frozen=True)
class ErrorLocation:
    file: str
    line: int
    column: int

    def __str__(self):
        return f"{self.file}:{self.line}:{self.column}"


class CheckResultsCache:
    def __init__(self):
        self._errors_by_mr = dict()  # Map merge request ids to error set for these merge requests.
        self._is_commit_ok = dict()  # Map commit hashes to check result for these commits.

    def has_mr_ever_been_checked(self, mr_manager: MergeRequestManager) -> bool:
        return mr_manager.mr_id in self._errors_by_mr

    def is_last_mr_commit_checked(self, mr_manager: MergeRequestManager) -> bool:
        return mr_manager.mr_last_commit_id in self._is_commit_ok

    def has_error_at(self, mr_manager: MergeRequestManager, location: ErrorLocation) -> bool:
        mr_results = self._errors_by_mr.get(mr_manager.mr_id, set())
        return str(location) in mr_results

    def add_error_at(self, mr_manager: MergeRequestManager, location: ErrorLocation) -> None:
        self._add_empty_errors_set_if_needed(mr_manager.mr_id)
        self._errors_by_mr[mr_manager.mr_id].add(str(location))
        self._is_commit_ok[mr_manager.mr_last_commit_id] = False

    def _add_empty_errors_set_if_needed(self, mr_id):
        if mr_id not in self._errors_by_mr:
            self._errors_by_mr[mr_id] = set()

    def mark_last_mr_commit_as_ok(self, mr_manager: MergeRequestManager) -> None:
        self._add_empty_errors_set_if_needed(mr_manager.mr_id)
        self._is_commit_ok[mr_manager.mr_last_commit_id] = True

    def is_last_mr_commit_ok(self, mr_manager: MergeRequestManager) -> bool:
        return self._is_commit_ok.get(mr_manager.mr_last_commit_id, None)


class OpenSourceCheckRule(BaseRule):
    def __init__(self, project, approver_username: str, approver_name: str = None):
        # NOTE: Potentially we have memory leak here - cache is never cleaned up.
        # TODO: Add cache cleanup.
        self._file_check_results_cache = CheckResultsCache()
        self._open_source_approver = approver_username
        self._open_source_approver_name = approver_name if approver_name else approver_username
        logger.info(
            "Open source rule created. Authorized approver is "
            f"{self._open_source_approver} ({self._open_source_approver_name})")
        super().__init__(project=project)

    def execute(self, mr_manager: MergeRequestManager) -> OpenSourceCheckRuleExecutionResult:
        logger.debug(f"Executing check open sources rule on {mr_manager}...")

        if not mr_manager.mr_has_commits:
            return OpenSourceCheckRuleExecutionResult.NoCommits

        if mr_manager.mr_work_in_progress:
            return OpenSourceCheckRuleExecutionResult.WorkInProgress

        if not self._changed_opensource_files(mr_manager):
            return OpenSourceCheckRuleExecutionResult.NotApplicable

        approval_requirements = ApprovalRequirements(
            mandatory_approvers=set([self._open_source_approver]))
        if mr_manager.satisfies_approval_requirements(approval_requirements):
            return OpenSourceCheckRuleExecutionResult.MergeAuthorized

        if mr_manager.ensure_assignee(self._open_source_approver):
            logger.debug("Authorized approver assigned to MR.")

        if not self._are_files_ok(mr_manager):
            return OpenSourceCheckRuleExecutionResult.FilesNotOk

        return OpenSourceCheckRuleExecutionResult.NotAuthorized

    def _changed_opensource_files(self, mr_manager) -> List[str]:
        changes = self.get_mr_changes(mr_manager.mr_id, mr_manager.mr_last_commit_id)
        opensource_files = [
            c["new_path"] for c in changes
            if not c["deleted_file"] and OpenSourceFileChecker.is_file_open_source(c["new_path"])]
        return opensource_files

    def _are_files_ok(self, mr_manager: MergeRequestManager) -> bool:
        cache = self._file_check_results_cache
        if cache.is_last_mr_commit_checked(mr_manager):
            return cache.is_last_mr_commit_ok(mr_manager)

        # Check files for the first time OR after a new commit added to the merge request OR
        # the merge request was ammended OR the merge request was rebased.
        has_errors = False
        for file_name in self._changed_opensource_files(mr_manager):
            file_content = self.get_file_content(sha=mr_manager.mr_last_commit_id, file=file_name)
            file_checker = OpenSourceFileChecker(file_name=file_name, file_content=file_content)
            for error in file_checker.file_errors():
                has_errors = True
                error_place = ErrorLocation(file=file_name, line=error.line, column=error.column)
                if cache.has_error_at(mr_manager, location=error_place):
                    # Don't create new discussions for the same error.
                    continue
                cache.add_error_at(mr_manager, location=error_place)
                self._create_open_source_discussion(mr_manager, file_name, error)

        if has_errors:
            return False

        # If no problems were found create discussion only once, during the first merge request
        # check.
        if not cache.has_mr_ever_been_checked(mr_manager):
            mr_manager.create_thread_to_resolve(
                title="Autocheck for open source changes passed",
                message=robocat.comments.has_good_changes_in_open_source.format(
                    approver=self._open_source_approver),
                emoji=AwardEmojiManager.AUTOCHECK_OK_EMOJI)

        cache.mark_last_mr_commit_as_ok(mr_manager)
        return True

    def _create_open_source_discussion(
            self, mr_manager: MergeRequestManager, file: str, error: FileError):
        title = "Autocheck for open source changes failed"
        message = robocat.comments.has_bad_changes_in_open_source.format(
            error_message=robocat.comments.__dict__[str(error.type)].format(**error.params),
            approver=self._open_source_approver)

        discussion_created = mr_manager.create_thread_to_resolve(
            title=title,
            message=message,
            emoji=AwardEmojiManager.AUTOCHECK_FAILED_EMOJI,
            file=file, line=error.line)

        # If the API call failed to create discussion bonded to the file and line number, we are
        # creating the discussion that is not bonded to the concrete position. TODO: Fix this
        # behavior. We must find the way to reliably create discussion, bonded to the file and line
        # number. See also comment in merge_request.py, function create_discussion().
        if not discussion_created:
            mr_manager.create_thread_to_resolve(
                title=title,
                message=f'Problem in file "{file}": {message}',
                emoji=AwardEmojiManager.AUTOCHECK_FAILED_EMOJI)
