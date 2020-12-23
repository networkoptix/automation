import logging
from enum import Enum

from robocat.merge_request_manager import MergeRequestManager, ApprovalRequirements
from robocat.rule.base_rule import BaseRule, RuleExecutionResult
from robocat.action_reasons import WaitReason, ReturnToDevelopmentReason
from robocat.pipeline import PipelineStatus

logger = logging.getLogger(__name__)


class EssentialRuleExecutionResult(RuleExecutionResult, Enum):
    merged = "MR is already merged"
    essential_rule_ok = "Essential rule check hasn't found any problems"
    no_commits = "No commits"
    work_in_progress = "Work in progress"
    has_conflicts = "Has conflicts"
    not_approved = "Not approved"
    pipeline_started = "Pipeline is (re)started"
    pipeline_running = "Pipeline is running"
    pipeline_failed = "Pipeline failed"
    unresolved_threads = "Unresolved threads found"

    def __bool__(self):
        return self in [self.essential_rule_ok, self.merged]


class EssentialRule(BaseRule):
    def execute(self, mr_manager: MergeRequestManager) -> EssentialRuleExecutionResult:
        logger.debug(f"Executing essential rule with {mr_manager}...")

        if mr_manager.is_merged:
            return EssentialRuleExecutionResult.merged

        if not mr_manager.mr_has_commits:
            mr_manager.ensure_wait_state(WaitReason.no_commits)
            return EssentialRuleExecutionResult.no_commits

        mr_manager.ensure_watching()
        mr_manager.ensure_user_requeseted_pipeline_run()

        if mr_manager.mr_work_in_progress:
            mr_manager.unset_wait_state()
            return EssentialRuleExecutionResult.work_in_progress

        if mr_manager.mr_has_conflicts:
            mr_manager.return_to_development(ReturnToDevelopmentReason.conflicts)
            return EssentialRuleExecutionResult.has_conflicts

        first_pipeline_started = mr_manager.ensure_first_pipeline_run()

        approval_requirements = ApprovalRequirements(approvals_left=0)
        if not mr_manager.satisfies_approval_requirements(approval_requirements):
            mr_manager.ensure_wait_state(WaitReason.not_approved)
            return EssentialRuleExecutionResult.not_approved

        if first_pipeline_started or mr_manager.ensure_pipeline_rerun():
            return EssentialRuleExecutionResult.pipeline_started

        last_pipeline_status = mr_manager.mr_last_pipeline_status
        if last_pipeline_status == PipelineStatus.running:
            mr_manager.ensure_wait_state(WaitReason.pipeline_running)
            return EssentialRuleExecutionResult.pipeline_running

        if mr_manager.mr_has_unresolved_threads:
            mr_manager.return_to_development(ReturnToDevelopmentReason.unresolved_threads)
            return EssentialRuleExecutionResult.unresolved_threads

        if last_pipeline_status == PipelineStatus.failed:
            mr_manager.return_to_development(ReturnToDevelopmentReason.failed_pipeline)
            return EssentialRuleExecutionResult.pipeline_failed

        assert last_pipeline_status == PipelineStatus.succeded, "Unexpected pipeline status"

        return EssentialRuleExecutionResult.essential_rule_ok
