from abc import ABCMeta, abstractmethod
from enum import Enum
import logging
from typing import Dict

from robocat.merge_request_manager import MergeRequestManager, MergeRequestData

logger = logging.getLogger(__name__)


# Emulate subclassing of non-empty Enum class
class RuleExecutionResultClass(Enum):
    @staticmethod
    def _common_values():
        return {
            "rule_not_implemented": "Rule is not implemented",
            "merged": "MR is already merged",
            "no_commits": "No commits",
            "work_in_progress": "Work in progress",
            "preliminary_check_passed": "Preliminary check passed"
        }

    def __bool__(self):
        return False

    def __str__(self):
        return str(f"{self.value}. MR can{' ' if self else ' not '}be merged.")

    @classmethod
    def create(cls, class_name: str, values: Dict[str, str]):
        class_values = dict(**values, **cls._common_values())
        return cls(class_name, class_values)


class BaseRule(metaclass=ABCMeta):
    EXECUTION_RESULT = RuleExecutionResultClass.create("RuleExecutionResult", {})

    def __init__(self):
        pass

    @abstractmethod
    def execute(self, mr_manager: MergeRequestManager) -> EXECUTION_RESULT:
        """Checks merge request state and executes necessary actions.

        :param mr: MergeRequest object
        :returns: True if merge request satisfies the rule described by this class; False otherwise
        """
        return self.EXECUTION_RESULT.rule_not_implemented

    def preliminary_check_result(self, mr_data: MergeRequestData) -> EXECUTION_RESULT:
        if mr_data.is_merged:
            return self.EXECUTION_RESULT.merged

        if not mr_data.has_commits:
            return self.EXECUTION_RESULT.no_commits

        if mr_data.work_in_progress:
            return self.EXECUTION_RESULT.work_in_progress

        return self.EXECUTION_RESULT.preliminary_check_passed
