## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import logging
import re
from typing import List, Set, Tuple
from dataclasses import asdict
from enum import Enum
from automation_tools.jira import JiraAccessor

from robocat.config import Config
from robocat.merge_request_manager import MergeRequestManager
from robocat.project_manager import ProjectManager
from robocat.note import MessageId
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
from robocat.rule.helpers.nx_submodule_checker import NxSubmoduleChecker
from robocat.rule.helpers.stateful_checker_helpers import (
    CheckError,
    CheckChangesMixin,
    ErrorCheckResult,
    StoredCheckResults)
from robocat.award_emoji_manager import AwardEmojiManager
import robocat.comments

logger = logging.getLogger(__name__)


class NxSubmoduleRuleExecutionResultClass(RuleExecutionResultClass, Enum):
    def __bool__(self):
        return self == self.nx_submodule_check_rule_ok


class NxSubmoduleStoredCheckResults(StoredCheckResults):
    MESSAGE_IDS = {
        MessageId.NxSubmoduleCheckHugeDiffUncheckable,
        MessageId.NxSubmoduleCheckPassed,
        MessageId.InconsistentNxSubmoduleChange,
        MessageId.NxSubmoduleConfigDeleted,
        MessageId.NxSubmoduleConfigMalformed,
        MessageId.NxSubmoduleConfigBadGitData,
        MessageId.NxSubmoduleCheckUnknownError,
    }
    OK_MESSAGE_IDS = {
        MessageId.NxSubmoduleCheckPassed,
        MessageId.NxSubmoduleCheckHugeDiffUncheckable,
    }


class NxSubmoduleCheckRule(CheckChangesMixin, BaseRule):
    identifier = "nx_submodule"

    ExecutionResult = NxSubmoduleRuleExecutionResultClass.create(
        "NxSubmoduleRuleExecutionResult", {
            "nx_submodule_check_rule_ok": "Nx Submodule check hasn't find any problems",
            "invalid_changes": "Invalid changes found",
        })

    def __init__(self, config: Config, project_manager: ProjectManager, jira: JiraAccessor):
        super().__init__(config, project_manager, jira)
        self._submodule_dirs = config.nx_submodule_check_rule.nx_submodule_dirs

    def _execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        logger.debug(f"Executing Nx Submodule(s) check on {mr_manager}...")

        mr_data = mr_manager.data
        preliminary_check_result = self.preliminary_check_result(mr_data)
        if preliminary_check_result != self.ExecutionResult.preliminary_check_passed:
            return preliminary_check_result

        error_check_result = self._do_error_check(
            mr_manager=mr_manager, check_results_class=NxSubmoduleStoredCheckResults)

        if error_check_result.current_errors:
            self._ensure_problem_comments(mr_manager, error_check_result)
            return self.ExecutionResult.invalid_changes

        self._ensure_problems_not_found_comment(mr_manager, error_check_result)
        return self.ExecutionResult.nx_submodule_check_rule_ok

    def _find_errors(self, mr_manager: MergeRequestManager) -> Set[CheckError]:
        errors = set()
        mr_sha = mr_manager.data.sha
        with NxSubmoduleChecker(self._submodule_dirs, self.project_manager, mr_sha) as checker:
            for file_changes in mr_manager.get_changes().changes:
                error = checker.find_error(
                    file_name=file_changes["new_path"],
                    is_executable=file_changes["b_mode"] == "100755",  # Git executable file mode
                    is_deleted=file_changes["deleted_file"])
                if error:
                    errors.add(error)
        return errors

    def _ensure_problem_comments(
            self, mr_manager: MergeRequestManager, errors: ErrorCheckResult):
        if not errors.has_changed_since_last_check:
            return

        for error in errors.new_errors:
            self._create_invalid_changes_discussion(mr_manager, error)

    def _create_invalid_changes_discussion(
            self, mr_manager: MergeRequestManager, error: CheckError):
        if error.type == NxSubmoduleChecker.INCONSISTENT_CONTENT:
            error_message = robocat.comments.inconsistent_nx_submodule_change.format(
                **error.params)
            message_id = MessageId.InconsistentNxSubmoduleChange
        elif error.type == NxSubmoduleChecker.CONFIG_DELETED_ERROR:
            error_message = robocat.comments.nx_submodule_config_deleted.format(**error.params)
            message_id = MessageId.NxSubmoduleConfigDeleted
        elif error.type == NxSubmoduleChecker.CONFIG_MALFORMED_ERROR:
            error_message = robocat.comments.nx_submodule_config_malformed.format(**error.params)
            message_id = MessageId.NxSubmoduleConfigMalformed
        elif error.type == NxSubmoduleChecker.CONFIG_BAD_GIT_DATA:
            error_message = robocat.comments.nx_submodule_bad_git_data.format(**error.params)
            message_id = MessageId.NxSubmoduleConfigBadGitData
        else:
            error_message = robocat.comments.unknown_nx_submodule_error
            message_id = MessageId.NxSubmoduleCheckUnknownError

        logger.warning(
            f"{mr_manager}: Invalid changes found (id: {message_id.value}), creating discussion")

        mr_manager.create_thread(
            title="Autocheck for Nx Submodule integrity failed",
            message=robocat.comments.has_invalid_changes.format(error_message=error_message),
            message_id=message_id,
            message_data=asdict(error),
            emoji=AwardEmojiManager.AUTOCHECK_FAILED_EMOJI)

    def _ensure_problems_not_found_comment(
            self, mr_manager: MergeRequestManager, error_check_result: ErrorCheckResult):
        if not error_check_result.has_changed_since_last_check:
            return

        if self._is_diff_complete(mr_manager):
            title = "Autocheck for Nx Submodules integrity passed"
            message = robocat.comments.nx_submodule_autocheck_passed
            message_id = MessageId.NxSubmoduleCheckPassed
            emoji = AwardEmojiManager.AUTOCHECK_OK_EMOJI
            autoresolve = True
        else:
            title = "Impossible to autocheck Nx Submodules integrity"
            message = robocat.comments.nx_submodule_autocheck_impossible
            message_id = MessageId.NxSubmoduleCheckHugeDiffUncheckable
            emoji = AwardEmojiManager.AUTOCHECK_IMPOSSIBLE_EMOJI
            autoresolve = False

        mr_manager.create_thread(
            title=title,
            message=message,
            message_id=message_id,
            emoji=emoji,
            autoresolve=autoresolve)
