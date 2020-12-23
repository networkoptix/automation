import logging
from enum import Enum
from abc import ABCMeta, abstractmethod

from robocat.merge_request_manager import MergeRequestManager

logger = logging.getLogger(__name__)


class RuleExecutionResult(Enum):
    def __str__(self):
        return str(f"{self.value}. MR can{' ' if self else ' not '}be merged.")


class BaseRule(metaclass=ABCMeta):
    def __init__(self):
        pass

    @abstractmethod
    def execute(self, mr_manager: MergeRequestManager) -> None:
        """Checks merge request state and executes necessary actions.

        :param mr: MergeRequest object
        :returns: True if merge request sutisfies the rule described by this class; False otherwise
        """
        return False
