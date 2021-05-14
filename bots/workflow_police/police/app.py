import jira
import graypy

from pathlib import Path
from typing import List, Dict, Tuple, Optional

import time
import datetime
import logging
import argparse
import sys

from automation_tools.checkers.checkers import (
    WrongVersionChecker, MasterMissingIssueCommitChecker, VersionMissingIssueCommitChecker,
    BranchMissingChecker, IssueTypeChecker, IssueIsFixedChecker, IssueIgnoreLabelChecker,
    IssueIgnoreProjectChecker)
import automation_tools.utils
from automation_tools.jira import JiraAccessor, JiraError, JiraIssue
import automation_tools.git

logger = logging.getLogger(__name__)


class ServiceNameFilter(logging.Filter):
    @staticmethod
    def filter(record):
        record.service_name = "Workflow Police"
        return True


class WorkflowViolationChecker:
    def __init__(self):
        self.reopen_checkers = []
        self.ignore_checkers = []

    def should_ignore_issue(self, issue: jira.Issue) -> Optional[str]:
        return self._run_checkers(issue, self.ignore_checkers)

    def should_reopen_issue(self, issue: jira.Issue) -> Optional[str]:
        return self._run_checkers(issue, self.reopen_checkers)

    @staticmethod
    def _run_checkers(issue: JiraIssue, checkers: List) -> Optional[str]:
        for checker in checkers:
            try:
                reason = checker.run(issue)
                if reason:
                    return reason
            except gitlab.exceptions.GitlabOperationError as e:
                logger.warning(f"Gitlab error while processing {issue}: {e}")
            except JiraError as e:
                logger.error(f"Jira error while processing {issue}: {e}")
            except git.GitError as e:
                logger.error(f"Git error while processing {issue}: {e}")
        return None


class WorkflowEnforcer:
    def __init__(
            self, config: Dict, jira: JiraAccessor = None, repo: automation_tools.git.Repo = None):
        self._polling_period_min = config.get("polling_period_min", 5)
        self._last_check_file = config.get("last_check_file", "/tmp/last_check")

        self._jira = jira if jira else JiraAccessor(**config["jira"])
        self._repo = repo if repo else automation_tools.git.Repo(**config["repo"])

        self._workflow_checker = WorkflowViolationChecker()
        self._workflow_checker.ignore_checkers = [
            IssueIgnoreLabelChecker(),
            IssueIgnoreProjectChecker(),
            IssueTypeChecker(),
            IssueIsFixedChecker(),
        ]

        self._workflow_checker.reopen_checkers = [
            WrongVersionChecker(),
            BranchMissingChecker(self._repo),
            VersionMissingIssueCommitChecker(self._repo),
            MasterMissingIssueCommitChecker(self._repo),
        ]

    def get_recent_issues_interval_min(self):
        try:
            with open(self._last_check_file, "r") as f:
                last_check_timestamp = int(f.read())
                now = int(datetime.datetime.now().timestamp())
                return (now - last_check_timestamp) // 60 + self._polling_period_min
        except FileNotFoundError:
            logger.info(f"No previous runs detected, using {self._polling_period_min * 2} min period")
            return self._polling_period_min * 2

    def update_last_check_timestamp(self):
        with open(self._last_check_file, "w") as f:
            f.write(str(int(datetime.datetime.now().timestamp())))

    def run(self, run_once: bool = False):
        while True:
            recent_issues_interval_min = self.get_recent_issues_interval_min()
            logger.debug(f"Verifying issues updated for last {recent_issues_interval_min} minutes")
            issues = self._jira.get_recently_closed_issues(recent_issues_interval_min)
            self._repo.update_repository()

            for issue in issues:
                reason = self._workflow_checker.should_ignore_issue(issue)
                if reason:
                    logger.debug(f"Ignoring {issue}: {reason}")
                    continue
                logger.info(f"Checking issue: {issue} ({issue.status}) "
                            f"with versions {issue.versions_to_branches_map.keys()}")
                reason = self._workflow_checker.should_reopen_issue(issue)
                if not reason:
                    continue
                issue.return_issue(reason)

            logger.debug(f"All {len(issues)} issues handled")
            self.update_last_check_timestamp()

            if run_once:
                break

            time.sleep(self._polling_period_min * 60)


def main():
    parser = argparse.ArgumentParser(sys.argv[0])
    parser.add_argument('config_file', help="Config file with all options")
    parser.add_argument('--log-level', help="Logs level", choices=logging._nameToLevel.keys(), default=logging.INFO)
    parser.add_argument('--graylog', help="Hostname of Graylog service")
    arguments = parser.parse_args()

    logging.basicConfig(
        level=arguments.log_level,
        format='%(asctime)s %(levelname)s %(name)s\t%(message)s')
    if arguments.graylog:
        host, port = arguments.graylog.split(":")
        graylog_handler = graypy.GELFTCPHandler(host, port, level_names=True)
        graylog_handler.addFilter(ServiceNameFilter())
        logging.getLogger().addHandler(graylog_handler)
        logger.debug(f"Logging to Graylog at {arguments.graylog}")

    try:
        config = automation_tools.utils.parse_config_file(Path(arguments.config_file))
        enforcer = WorkflowEnforcer(config)
        enforcer.run()
    except Exception as e:
        logger.warning(f'Crashed with exception: {e}', exc_info=1)
        sys.exit(1)
