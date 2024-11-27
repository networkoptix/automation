## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from enum import Enum
import logging
import re

from robocat.config import Config, RelatedMergeRequestRuleConfig
from robocat.merge_request_manager import MergeRequestManager
from robocat.project_manager import ProjectManager
from robocat.rule.base_rule import BaseRule, RuleExecutionResultClass
from automation_tools.jira import JiraAccessor
from automation_tools.utils import AutomationError

logger = logging.getLogger(__name__)


class PostprocessingRuleError(AutomationError):
    pass


class PostprocessingRule:
    _ISSUE_PATTERN_RE = re.compile(r"\b([A-Z][A-Z0-9_]+-\d+)\b")

    def __init__(self, config: RelatedMergeRequestRuleConfig):
        self._trigger_title_pattern = re.compile(config.trigger_title_pattern)
        self._issue_keys_pattern = re.compile(config.issue_keys_pattern)
        self._related_project_keys = config.related_projects
        self._action = config.action

    def is_applicable(self, mr_manager: MergeRequestManager) -> bool:
        return bool(self._trigger_title_pattern.match(mr_manager.data.title))

    def execute(self, jira: JiraAccessor, mr_manager: MergeRequestManager) -> bool:
        result = True

        issue_keys_match = self._issue_keys_pattern.match(mr_manager.data.description)
        issue_keys = list(self._ISSUE_PATTERN_RE.findall(issue_keys_match["issue_keys"]))
        for issue_key in issue_keys:
            project_key, *_ = issue_key.partition("-")
            if project_key not in self._related_project_keys:
                continue
            issue = jira.get_issue(issue_key)

            if self._action == "finalize":
                result &= issue.try_finalize()
            else:
                raise PostprocessingRuleError(f"Bad postprocessing action: {self._action}")

        return result


class ProcessRelatedProjectIssuesRuleExecutionResultClass(RuleExecutionResultClass, Enum):
    def __bool__(self):
        return self == self.rule_execution_successful or self == self.no_applicable_rules

    def __str__(self):
        return str(self.value)


class ProcessRelatedProjectIssuesRule(BaseRule):
    identifier = "process_related"

    ExecutionResult = ProcessRelatedProjectIssuesRuleExecutionResultClass.create(
        "ProcessRelatedProjectIssuesRuleExecutionResult", {
            "rule_execution_successful": "All operations completed successfully",
            "not_eligible": "The Merge Request is not eligible for postprocessing",
            "no_applicable_rules": "No postprocessing rules can be applied",
            "rule_execution_failed": "Some of the operations failed",
        })

    def __init__(self, config: Config, project_manager: ProjectManager, jira: JiraAccessor):
        super().__init__(config, project_manager, jira)
        rules = config.process_related_merge_requests_rule.rules
        self._postprocessing_rules = [PostprocessingRule(pr) for pr in rules]

    def _execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        logger.debug(
            "Executing the rule of processing issues for the related projects with "
            f"{mr_manager}...")

        mr_data = mr_manager.data
        if not mr_data.is_merged:
            logger.info(
                f"{mr_manager}: Merge Request isn't merged. Will not close the Issues in the "
                "related Projects.")
            return self.ExecutionResult.not_eligible

        has_applicable_rules = False
        rule_executions_result = True
        for rule in self._postprocessing_rules:
            if rule.is_applicable(mr_manager):
                has_applicable_rules = True
                rule_executions_result &= rule.execute(jira=self.jira, mr_manager=mr_manager)

        if not has_applicable_rules:
            return self.ExecutionResult.no_applicable_rules

        if not rule_executions_result:
            return self.ExecutionResult.rule_execution_failed

        return self.ExecutionResult.rule_execution_successful
