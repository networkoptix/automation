import jira
import git
import graypy

from pathlib import Path
from typing import List, Dict, Optional

import time
import datetime
import logging
import argparse
import sys

from automation_tools.checkers.checkers import (
    WrongVersionChecker,
    MasterMissingIssueCommitChecker,
    VersionMissingIssueCommitChecker,
    BranchMissingChecker,
    IssueTypeChecker,
    IssueIsFixedChecker,
    IssueIgnoreLabelChecker,
    IgnoreIrrelevantProjectChecker,
    WorkflowPolicyChecker)
from automation_tools.jira import JiraAccessor, JiraError, JiraIssue
from automation_tools.utils import AutomationError, flatten_list, parse_config_file
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
            except JiraError as e:
                logger.error(f"Jira error while processing {issue}: {e}")
            except git.GitError as e:
                logger.error(f"Git error while processing {issue}: {e}")
        return None


class WorkflowEnforcer:
    CLASS_NAME_TO_CONFIG_KEY_MAP = {
        "IssueIgnoreLabelChecker": "ignore_by_label",
        "IssueTypeChecker": "ignore_by_type",
        "IssueIsFixedChecker": "ignore_fixed",
        "IgnoreIrrelevantProjectChecker": "ignore_by_project",
        "WrongVersionChecker": "wrong_version",
        "BranchMissingChecker": "missing_branch",
        "VersionMissingIssueCommitChecker": "missing_issue_commit",
        "MasterMissingIssueCommitChecker": "missing_commit_to_master",
    }

    def __init__(
            self, config: Dict, jira: JiraAccessor = None, repo: automation_tools.git.Repo = None):
        self._polling_period_min = config.get("polling_period_min", 5)
        self._last_check_file = config.get("last_check_file", "/tmp/last_check")

        self._jira = jira if jira else JiraAccessor(**config["jira"])
        self._config = config

        self._workflow_checker = WorkflowViolationChecker()

        self._workflow_checker.ignore_checkers = [
            IgnoreIrrelevantProjectChecker(
                project_keys=self._projects_list_by_class(IgnoreIrrelevantProjectChecker)),
            IssueIgnoreLabelChecker(
                project_keys=self._projects_list_by_class(IssueIgnoreLabelChecker)),
            IssueTypeChecker(project_keys=self._projects_list_by_class(IssueTypeChecker)),
            IssueIsFixedChecker(project_keys=self._projects_list_by_class(IssueIsFixedChecker)),
        ]

        self._repos = {}
        repo_dependent_checkers = [
            BranchMissingChecker,
            VersionMissingIssueCommitChecker,
            MasterMissingIssueCommitChecker,
        ]
        for klass in repo_dependent_checkers:
            self._repos[klass.__name__] = repo if repo else self._repo_by_class(klass)

        self._workflow_checker.reopen_checkers = [
            WrongVersionChecker(project_keys=self._projects_list_by_class(WrongVersionChecker)),
            BranchMissingChecker(
                repo=self._repos[BranchMissingChecker.__name__],
                project_keys=self._projects_list_by_class(BranchMissingChecker)),
            VersionMissingIssueCommitChecker(
                repo=self._repos[VersionMissingIssueCommitChecker.__name__],
                project_keys=self._projects_list_by_class(VersionMissingIssueCommitChecker)),
            MasterMissingIssueCommitChecker(
                repo=self._repos[MasterMissingIssueCommitChecker.__name__],
                project_keys=self._projects_list_by_class(MasterMissingIssueCommitChecker)),
        ]

    def _projects_list_by_class(self, klass: WorkflowPolicyChecker):
        return flatten_list(self._checker_config_by_class(klass)["projects"])

    def _checker_config_by_class(self, klass: WorkflowPolicyChecker):
        return self._config["checkers"][self.CLASS_NAME_TO_CONFIG_KEY_MAP[klass.__name__]]

    def _repo_by_class(self, klass: WorkflowPolicyChecker):
        return flatten_list(self._checker_config_by_class(klass)["repo"])

    def get_recent_issues_interval_min(self):
        try:
            with open(self._last_check_file, "r") as f:
                last_check_timestamp = int(f.read())
                now = int(datetime.datetime.now().timestamp())
                return (now - last_check_timestamp) // 60 + self._polling_period_min
        except FileNotFoundError:
            logger.info(
                f"No previous runs detected, using {self._polling_period_min * 2} min period")
            return self._polling_period_min * 2

    def update_last_check_timestamp(self):
        with open(self._last_check_file, "w") as f:
            f.write(str(int(datetime.datetime.now().timestamp())))

    def run(self, run_once: bool = False):
        while True:
            recent_issues_interval_min = self.get_recent_issues_interval_min()
            logger.debug(f"Verifying issues updated for last {recent_issues_interval_min} minutes")
            issues = self._jira.get_recently_closed_issues(recent_issues_interval_min)
            for repo in self._repos.values():
                repo.update_repository()

            for issue in issues:
                self.handle(issue)

            logger.debug(f"All {len(issues)} issues handled")
            self.update_last_check_timestamp()

            if run_once:
                break

            time.sleep(self._polling_period_min * 60)

    def handle(self, issue: jira.Issue):
        try:
            reason = self._workflow_checker.should_ignore_issue(issue)
            if reason:
                logger.debug(f"Ignoring {issue}: {reason}")
                return
            logger.info(
                f"Checking issue: {issue} ({issue.status}) "
                f"with versions {issue.versions_to_branches_map.keys()}")
            reason = self._workflow_checker.should_reopen_issue(issue)
            if not reason:
                return
            issue.return_issue(reason)

        except AutomationError as e:
            logger.warning(f"Error while processing issue {issue}: {e}")


def main():
    parser = argparse.ArgumentParser(sys.argv[0])
    parser.add_argument('config_file', help="Config file with all options")
    parser.add_argument(
        '--log-level',
        help="Logs level",
        choices=logging._nameToLevel.keys(),
        default=logging.INFO)
    parser.add_argument('--graylog', help="Hostname of Graylog service")
    arguments = parser.parse_args()

    log_handler = None
    if arguments.graylog:
        host, port = arguments.graylog.split(":")
        log_handler = graypy.GELFTCPHandler(host, port, level_names=True)
        log_handler.addFilter(ServiceNameFilter())
    else:
        log_handler = logging.StreamHandler()

    logging.basicConfig(
        level=arguments.log_level,
        handlers=[log_handler],
        format='%(asctime)s %(levelname)s %(name)s\t%(message)s')

    try:
        config = parse_config_file(Path(arguments.config_file))
        enforcer = WorkflowEnforcer(config)
        enforcer.run()
    except Exception as e:
        logger.warning(f'Crashed with exception: {e}', exc_info=1)
        sys.exit(1)
