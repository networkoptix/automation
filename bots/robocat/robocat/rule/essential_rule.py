import logging
from enum import Enum

from robocat.merge_request_manager import MergeRequestManager, ApprovalRequirements
from robocat.rule.base_rule import BaseRule, RuleExecutionResult
from robocat.action_reasons import WaitReason, ReturnToDevelopmentReason
from robocat.pipeline import PipelineStatus

logger = logging.getLogger(__name__)


class EssentialRuleExecutionResult(RuleExecutionResult, Enum):
    EssentialRuleOk = "Essential rule check hasn't found any problems"
    NoCommits = "No commits"
    WorkInProgress = "Work in progress"
    HasConflicts = "Has conflicts"
    NotApproved = "Not approved"
    PipelineStarted = "Pipeline is (re)started"
    PipelineRunning = "Pipeline is running"
    PipelineFailed = "Pipeline failed"
    UnresolvedThreads = "Unresolved threads found"

    def __bool__(self):
        return self == self.EssentialRuleOk


class EssentialRule(BaseRule):
    def __init__(self, project):
        super().__init__(project=project)

    def execute(self, mr_manager: MergeRequestManager) -> EssentialRuleExecutionResult:
        logger.debug(f"Executing essential rule with {mr_manager}...")

        if not mr_manager.mr_has_commits:
            mr_manager.ensure_wait_state(WaitReason.no_commits)
            return EssentialRuleExecutionResult.NoCommits

        mr_manager.ensure_watching()
        mr_manager.ensure_user_requeseted_pipeline_run()

        if mr_manager.mr_work_in_progress:
            mr_manager.unset_wait_state()
            return EssentialRuleExecutionResult.WorkInProgress

        if mr_manager.mr_has_conflicts:
            mr_manager.return_to_development(ReturnToDevelopmentReason.conflicts)
            return EssentialRuleExecutionResult.HasConflicts

        first_pipeline_started = mr_manager.ensure_first_pipeline_run()

        approval_requirements = ApprovalRequirements(approvals_left=0)
        if not mr_manager.satisfies_approval_requirements(approval_requirements):
            mr_manager.ensure_wait_state(WaitReason.not_approved)
            return EssentialRuleExecutionResult.NotApproved

        if first_pipeline_started or mr_manager.ensure_pipeline_rerun():
            return EssentialRuleExecutionResult.PipelineStarted

        last_pipeline_status = mr_manager.mr_last_pipeline_status
        if last_pipeline_status == PipelineStatus.running:
            mr_manager.ensure_wait_state(WaitReason.pipeline_running)
            return EssentialRuleExecutionResult.PipelineRunning

        if mr_manager.mr_has_unresolved_threads:
            mr_manager.return_to_development(ReturnToDevelopmentReason.unresolved_threads)
            return EssentialRuleExecutionResult.UnresolvedThreads

        if last_pipeline_status == PipelineStatus.failed:
            mr_manager.return_to_development(ReturnToDevelopmentReason.failed_pipeline)
            return EssentialRuleExecutionResult.PipelineFailed

        assert last_pipeline_status == PipelineStatus.succeded, "Unexpected pipeline status"

        return EssentialRuleExecutionResult.EssentialRuleOk
