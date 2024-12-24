## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import dataclasses
import logging
from typing import Set
from dataclasses import asdict
from enum import Enum
from automation_tools.jira import JiraAccessor

from robocat.config import Config
from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId
from robocat.project_manager import ProjectManager
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
import robocat.rule.helpers.approve_rule_helpers as approve_rule_helpers
from robocat.rule.helpers.stateful_checker_helpers import (
    CheckChangesMixin,
    CheckError,
    ErrorCheckResult,
    StoredCheckResults)
from robocat.award_emoji_manager import AwardEmojiManager
import robocat.comments
import source_file_compliance

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class CommitMessageError(CheckError):
    raw_text: str = ""


class CommitMessageCheckRuleExecutionResultClass(RuleExecutionResultClass, Enum):
    def __bool__(self):
        return self in [
            self.not_applicable,
            self.merge_authorized,
            self.merged,
            self.commit_message_is_ok,
            self.filtered_out,
        ]


class CommitMessageStoredCheckResults(StoredCheckResults):
    CheckErrorClass = CommitMessageError

    MESSAGE_IDS = {
        MessageId.CommitMessageIsOk,
        MessageId.BadCommitMessageByKeeper,
        MessageId.BadCommitMessage,
    }
    OK_MESSAGE_IDS = {MessageId.CommitMessageIsOk}


class CommitMessageCheckRule(CheckChangesMixin, BaseRule):
    identifier = "commit_message"

    ExecutionResult = CommitMessageCheckRuleExecutionResultClass.create(
        "CommitMessageCheckRuleExecutionResult", {
            "merge_authorized": "MR is approved by the authorized approver",
            "not_applicable": "No changes in open source files",
            "commit_message_not_ok": "Commit message contains bad words",
            "commit_message_is_ok": "Commit message check didn't find any problems",
        })

    def __init__(self, config: Config, project_manager: ProjectManager, jira: JiraAccessor):
        super().__init__(config, project_manager, jira)
        job_status_check_configuration = config.job_status_check_rule.open_source
        approve_ruleset = job_status_check_configuration.approve_ruleset
        checker = getattr(approve_rule_helpers, approve_ruleset.relevance_checker)
        self._approve_rules = [
            approve_rule_helpers.ApproveRule(
                approvers=rule.approvers,
                patterns=rule.patterns,
                relevance_checker=checker)
            for rule in approve_ruleset.rules]
        logger.info(
            f"Commit message check rule created. Approvers list is {self._approve_rules!r}")

    def _execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        logger.debug(f"Executing check commit message rule on {mr_manager}...")

        mr_data = mr_manager.data
        preliminary_check_result = self.preliminary_check_result(mr_data)
        if preliminary_check_result != self.ExecutionResult.preliminary_check_passed:
            return preliminary_check_result

        if not self._has_changes_in_open_source(mr_manager):
            return self.ExecutionResult.not_applicable

        error_check_result = self._do_error_check(
            mr_manager=mr_manager, check_results_class=CommitMessageStoredCheckResults)

        if error_check_result.current_errors:
            self._ensure_problem_comments(mr_manager, error_check_result)
            approval_requirements = approve_rule_helpers.get_approval_requirements(
                approve_rules=self._approve_rules, mr_manager=mr_manager)
            if mr_manager.satisfies_approval_requirements(approval_requirements):
                return self.ExecutionResult.merge_authorized
            preferred_approvers = approve_rule_helpers.get_keepers(
                approve_rules=self._approve_rules, mr_manager=mr_manager, for_affected_files=True)
            if mr_manager.ensure_authorized_approvers([preferred_approvers]):
                logger.debug(f"{mr_manager}: Preferred approvers assigned to MR.")
            return self.ExecutionResult.commit_message_not_ok

        self._ensure_problems_not_found_comment(mr_manager, error_check_result)
        return self.ExecutionResult.commit_message_is_ok

    def _has_changes_in_open_source(self, mr_manager: MergeRequestManager) -> bool:
        # We rely on the pipeline check here: if the job for open-source check is not created
        # we assume that there are no changes in the open-source part of the project.
        open_source_check_result = mr_manager.last_pipeline_check_job_status("open-source:check")
        return open_source_check_result is not None

    def _find_errors(self, mr_manager: MergeRequestManager) -> Set[CommitMessageError]:
        errors = set()
        for raw_error in source_file_compliance.check_text(mr_manager.last_commit_message()):
            error_type = f"{raw_error.reason}_word"
            error_text = (
                "This commit seems to contain licensing-related or other sensitive functionality: "
                f"commit message contains `{raw_error.word}` (stem `{raw_error.stem}`) at "
                f"line {raw_error.line}:{raw_error.col}. Some of the open-source keepers must "
                "review this commit before it can be merged.")
            errors.add(CommitMessageError(type=error_type, raw_text=error_text))
        return errors

    def _ensure_problem_comments(
            self, mr_manager: MergeRequestManager, errors: ErrorCheckResult):
        if not errors.has_changed_since_last_check:
            return

        for error in errors.new_errors:
            self._create_commit_message_discussion(mr_manager, error)

    def _create_commit_message_discussion(
            self, mr_manager: MergeRequestManager, error: CommitMessageError):
        title = "Commit message auto-check failed"

        if approve_rule_helpers.is_mr_author_keeper(self._approve_rules, mr_manager):
            message = robocat.comments.bad_commit_message_from_authorized_approver.format(
                error_message=error.raw_text)
            message_id = MessageId.BadCommitMessageByKeeper
        else:
            keepers = approve_rule_helpers.get_keepers(
                approve_rules=self._approve_rules, mr_manager=mr_manager, for_affected_files=True)
            message = robocat.comments.bad_commit_message.format(
                error_message=error.raw_text,
                approvers=", @".join(keepers))
            message_id = MessageId.BadCommitMessage

        mr_manager.create_thread(
            title=title,
            message=message,
            message_id=message_id,
            message_data=asdict(error),
            emoji=AwardEmojiManager.AUTOCHECK_FAILED_EMOJI)

    def _ensure_problems_not_found_comment(
            self, mr_manager: MergeRequestManager, errors: ErrorCheckResult):
        if errors.current_errors or not errors.has_changed_since_last_check:
            return

        mr_manager.create_thread(
            title="Commit auto-check passed",
            message=robocat.comments.commit_message_is_ok,
            message_id=MessageId.CommitMessageIsOk,
            emoji=AwardEmojiManager.AUTOCHECK_OK_EMOJI,
            autoresolve=True)
