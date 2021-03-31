import jira
import graypy

from pathlib import Path
from typing import List, Dict, Tuple, Optional

import time
import datetime
import logging
import argparse
import sys

import automation_tools.utils
from automation_tools.jira import JiraAccessor, JiraError
import automation_tools.git
from police.checkers import *

logger = logging.getLogger(__name__)


class ServiceNameFilter(logging.Filter):
    @staticmethod
    def filter(record):
        record.service_name = "Workflow Police"
        return True


class WorkflowEnforcer:
    def __init__(self, config: Dict):
        self._polling_period_min = config["polling_period_min"]
        self._last_check_file = config["last_check_file"]

        self._jira = JiraAccessor(**config["jira"])
        self._repo = automation_tools.git.Repo(**config["repo"])

        self._workflow_checker = WorkflowViolationChecker()
        self._workflow_checker.register_ignore_checker(check_issue_ignore_label)
        self._workflow_checker.register_ignore_checker(check_issue_type)
        self._workflow_checker.register_ignore_checker(check_issue_not_fixed)

        self._workflow_checker.register_reopen_checker(WrongVersionChecker(self._jira))
        self._workflow_checker.register_reopen_checker(BranchMissingChecker(self._jira, self._repo))
        self._workflow_checker.register_reopen_checker(VersionMissingIssueCommitChecker(self._jira, self._repo))
        self._workflow_checker.register_reopen_checker(MasterMissingIssueCommitChecker(self._repo))

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

    def run(self):
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
                logger.info(f"Checking issue: {issue} ({issue.fields.status}) "
                            f"with versions {[v.name for v in issue.fields.fixVersions]}")
                reason = self._workflow_checker.should_reopen_issue(issue)
                if not reason:
                    continue

            logger.debug(f"All {len(issues)} issues handled")
            self.update_last_check_timestamp()

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
