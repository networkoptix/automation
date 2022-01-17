import logging
from enum import Enum
from typing import Set

from automation_tools.checkers.checkers import WorkflowPolicyChecker
from robocat.merge_request_manager import MergeRequestManager, ApprovalRequirements
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
from robocat.action_reasons import WaitReason, ReturnToDevelopmentReason
from robocat.pipeline import PipelineStatus

logger = logging.getLogger(__name__)


class EssentialRuleExecutionResultClass(RuleExecutionResultClass, Enum):
    def __bool__(self):
        return self in [self.essential_rule_ok, self.merged]


class EssentialRule(BaseRule):
    ExecutionResult = EssentialRuleExecutionResultClass.create(
        "EssentialRuleExecutionResult", {
            "bad_project_list": "Merge Request does not belong to any supported Jira Project",
            "essential_rule_ok": "Essential rule check hasn't found any problems",
            "has_conflicts": "Has conflicts",
            "not_approved": "Not approved",
            "pipeline_started": "Pipeline is (re)started",
            "pipeline_running": "Pipeline is running",
            "pipeline_failed": "Pipeline failed",
            "rebase_in_progress": "Rebase in progress",
            "unresolved_threads": "Unresolved threads found",
        })

    def __init__(self, project_keys: Set[str]):
        self._project_keys = project_keys
        super().__init__()

    def execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        logger.debug(f"Executing essential rule with {mr_manager}...")

        mr_data = mr_manager.data
        preliminary_check_result = self.preliminary_check_result(mr_data)

        if preliminary_check_result == self.ExecutionResult.merged:
            return preliminary_check_result

        if preliminary_check_result == self.ExecutionResult.no_commits:
            mr_manager.ensure_wait_state(WaitReason.no_commits)
            return preliminary_check_result

        if preliminary_check_result == self.ExecutionResult.work_in_progress:
            mr_manager.unset_wait_state()
            return preliminary_check_result

        belongs_to_supported_projects = any([
            True for k in mr_manager.data.issue_keys
            if WorkflowPolicyChecker(project_keys=self._project_keys).is_applicable(k)])
        if not belongs_to_supported_projects:
            mr_manager.return_to_development(
                ReturnToDevelopmentReason.bad_project_list, self._project_keys)
            return self.ExecutionResult.bad_project_list

        mr_manager.ensure_watching()
        mr_manager.ensure_user_requested_pipeline_run()

        if mr_data.has_conflicts:
            mr_manager.return_to_development(ReturnToDevelopmentReason.conflicts)
            return self.ExecutionResult.has_conflicts

        first_pipeline_started = mr_manager.ensure_first_pipeline_run()
        first_pipeline_started = False

        approval_requirements = ApprovalRequirements(approvals_left=0)
        if not mr_manager.satisfies_approval_requirements(approval_requirements):
            mr_manager.ensure_wait_state(WaitReason.not_approved)
            return self.ExecutionResult.not_approved

        if first_pipeline_started or mr_manager.ensure_pipeline_rerun():
            return self.ExecutionResult.pipeline_started

        if mr_manager.rebase_in_progress:
            return self.ExecutionResult.rebase_in_progress

        last_pipeline_status = mr_manager.get_last_pipeline_status()
        if last_pipeline_status == PipelineStatus.running:
            mr_manager.ensure_wait_state(WaitReason.pipeline_running)
            return self.ExecutionResult.pipeline_running

        if not mr_data.blocking_discussions_resolved:
            mr_manager.return_to_development(ReturnToDevelopmentReason.unresolved_threads)
            return self.ExecutionResult.unresolved_threads

        if last_pipeline_status == PipelineStatus.failed:
            mr_manager.return_to_development(ReturnToDevelopmentReason.failed_pipeline)
            return self.ExecutionResult.pipeline_failed

        assert last_pipeline_status == PipelineStatus.succeded, "Unexpected pipeline status"

        return self.ExecutionResult.essential_rule_ok
