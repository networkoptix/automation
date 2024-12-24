## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import datetime
import logging
import re
import time
from abc import ABCMeta, abstractmethod
from enum import Enum

from automation_tools.jira import JiraAccessor
from robocat.config import Config
from robocat.merge_request_manager import MergeRequestManager, MergeRequestData
from robocat.project_manager import ProjectManager

logger = logging.getLogger(__name__)


# Emulate subclassing of non-empty Enum class.
class RuleExecutionResultClass(Enum):
    @staticmethod
    def _common_values():
        return {
            "rule_not_implemented": "Rule is not implemented",
            "merged": "MR is already merged",
            "no_commits": "No commits",
            "work_in_progress": "Work in progress",
            "preliminary_check_passed": "Preliminary check passed",
            "filtered_out": "Rule execution was filtered out due to configuration",
        }

    def __bool__(self):
        return False

    def __str__(self):
        return str(f"{self.value}. MR can{' ' if self else ' not '}be merged.")

    @classmethod
    def create(cls, class_name: str, values: dict[str, str]):
        class_values = dict(**values, **cls._common_values())
        return cls(class_name, class_values)


class BaseRule(metaclass=ABCMeta):
    LONG_PROCESSING_THRESHOLD_S = 3
    ExecutionResult = RuleExecutionResultClass.create("RuleExecutionResult", {})

    def __init__(self, config: Config, project_manager: ProjectManager, jira: JiraAccessor):
        self.config = config
        self.project_manager = project_manager
        self.jira = jira

    def execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        time_before_s = time.time()

        # TODO: Get rid of ambiguity in the names of the config parameters. All should look like
        # "{self.identifier}_rule". This will require changing the config files, identifier names
        # and all related code.
        if ((rule_config := getattr(self.config, f"{self.identifier}_rule", None)) is not None
                or (rule_config := getattr(
                    self.config, f"{self.identifier}_check_rule", None)) is not None):
            if rule_config.excluded_issue_title_patterns:
                mr_data = mr_manager.data
                logger.debug(
                    f"Checking the Issue title filters against the title {mr_data.title!r}")
                for regexp in rule_config.excluded_issue_title_patterns:
                    if re.match(pattern=regexp, string=mr_data.title):
                        logger.info(
                            f"{mr_manager}: Skipping {self.identifier!r} rule because the Issue "
                            f"title matched the pattern {regexp!r}.")
                        return self.ExecutionResult.filtered_out

        result = self._execute(mr_manager)

        processing_time_s = time.time() - time_before_s
        processing_time_message = (
            f"Rule '{self.__class__.__name__}' processing time: "
            f"{datetime.timedelta(seconds=processing_time_s)}")

        log_level = (
            logging.INFO if processing_time_s > self.LONG_PROCESSING_THRESHOLD_S
            else logging.DEBUG)
        logger.log(level=log_level, msg=processing_time_message)

        return result

    @abstractmethod
    def _execute(self, mr_manager: MergeRequestManager) -> ExecutionResult:
        """Checks merge request state and executes necessary actions.

        :param mr: MergeRequest object
        :returns: True if merge request satisfies the rule described by this class; False otherwise
        """
        return self.ExecutionResult.rule_not_implemented

    def preliminary_check_result(self, mr_data: MergeRequestData) -> ExecutionResult:
        if mr_data.is_merged:
            return self.ExecutionResult.merged

        if not mr_data.has_commits:
            return self.ExecutionResult.no_commits

        if mr_data.work_in_progress:
            return self.ExecutionResult.work_in_progress

        return self.ExecutionResult.preliminary_check_passed
