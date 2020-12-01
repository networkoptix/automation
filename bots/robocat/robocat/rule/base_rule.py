import enum
import logging
from abc import ABCMeta, abstractmethod
from functools import lru_cache
from typing import List, Dict
from enum import Enum

from robocat.merge_request_manager import MergeRequestManager

logger = logging.getLogger(__name__)


class RuleExecutionResult(Enum):
    def __str__(self):
        return str(f"{self.value}. MR can{' ' if self else ' not '}be merged.")


class BaseRule(metaclass=ABCMeta):
    def __init__(self, project):
        self._project = project

    @abstractmethod
    def execute(self, mr_manager: MergeRequestManager) -> None:
        """Checks merge request state and executes necessary actions.

        :param mr: MergeRequest object
        :returns: True if merge request sutisfies the rule described by this class; False otherwise
        """
        return False

    # TODO: The next to methods should be moved to separate class "Project".
    @lru_cache(maxsize=64)  # Long term cache. Use the same data in different bot "handle" calls.
    def get_file_content(self, sha: str, file: str) -> str:
        logger.debug(f"Getting file content: {sha}, {file}")
        file_handler = self._project.files.get(file_path=file, ref=sha)
        return file_handler.decode().decode('utf-8')

    # Returns changes for the last version of the merge request. "sha" argument is used by
    # lru_cache magic.
    @lru_cache(maxsize=512)  # Long term cache. Use the same data in different bot "handle" calls.
    def get_mr_changes(self, mr_id: int, sha: str) -> List[Dict]:  # pylint: disable=unused-argument
        gitlab_mr = self._project.mergerequests.get(mr_id, lazy=True)
        return gitlab_mr.changes()["changes"]
