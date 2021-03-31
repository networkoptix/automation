import jira

from typing import List, Dict, Tuple, Optional
import logging

import automation_tools.utils
from automation_tools.jira import JiraAccessor, JiraError, JiraIssue
import automation_tools.git


logger = logging.getLogger(__name__)


class WorkflowViolationChecker:
    def __init__(self):
        self.reopen_checkers = []
        self.ignore_checkers = []

    def register_reopen_checker(self, checker):
        self.reopen_checkers.append(checker)

    def register_ignore_checker(self, checker):
        self.ignore_checkers.append(checker)

    def should_ignore_issue(self, issue: jira.Issue) -> Optional[str]:
        return self._run_checkers(issue, self.ignore_checkers)

    def should_reopen_issue(self, issue: jira.Issue) -> Optional[str]:
        return self._run_checkers(issue, self.reopen_checkers)

    @staticmethod
    def _run_checkers(issue: jira.Issue, checkers: List) -> Optional[str]:
        for checker in checkers:
            try:
                reason = checker(issue)
                if reason:
                    return reason
            except Exception as error:
                logger.error(f"Checker for {issue.name} failed with error: {error}")
        return None


# TODO: Move these classes to common part (automation_tools).
class WrongVersionChecker:
    def __init__(self, jira_accessor: JiraAccessor):
        self._jira = jira_accessor

    def __call__(self, issue: jira.Issue) -> Optional[str]:
        return self._jira.get_issue(issue.key).version_set_error_string()


class BranchMissingChecker:
    def __init__(self, jira_accessor: JiraAccessor, repo: automation_tools.git.Repo):
        self._jira = jira_accessor
        self._repo = repo

    def __call__(self, issue: jira.Issue) -> Optional[str]:
        for version in issue.fields.fixVersions:
            # NOTE: checking only recent commits as an optimization
            branch = self._jira.version_to_branch_mapping()[automation_tools.utils.Version(version.name)]
            if not self._repo.check_branch_exists(branch):
                return f"Branch {branch} (version: {version}) doesn't exist"
        return


class VersionMissingIssueCommitChecker:
    def __init__(self, jira_accessor: JiraAccessor, repo: automation_tools.git.Repo):
        self._jira = jira_accessor
        self._repo = repo

    def __call__(self, issue: jira.Issue) -> Optional[str]:
        for version in issue.fields.fixVersions:
            # NOTE: checking only recent commits as an optimization
            branch = self._jira.version_to_branch_mapping()[automation_tools.utils.Version(version.name)]
            if len(self._repo.grep_recent_commits(issue.key, branch)) == 0:
                return f"No commits in {version.name} version (branch: {branch})"
        return


class MasterMissingIssueCommitChecker:
    def __init__(self, repo: automation_tools.git.Repo):
        self._repo = repo

    def __call__(self, issue: jira.Issue) -> Optional[str]:
        if JiraIssue.VERSION_SPECIFIC_LABEL in issue.fields.labels:
            return
        if len(self._repo.grep_recent_commits(issue.key, "master")) == 0:
            return "No commits in master"


def check_issue_type(issue: jira.Issue) -> Optional[str]:
    if issue.fields.issuetype.name in ["New Feature", "Epic", "Func Spec", "Tech Spec"]:
        return f"issue type [{issue.fields.issuetype}]"
    return


def check_issue_not_fixed(issue: jira.Issue) -> Optional[str]:
    if str(issue.fields.resolution) in ["Fixed", "Done"]:
        return

    is_issue_done_externally = JiraIssue.DONE_EXTERNALLY_LABEL in issue.fields.labels
    if issue.fields.status.name == "Waiting for QA" and not is_issue_done_externally:
        return

    return f"issue resolution [{issue.fields.resolution}], issue status [{issue.fields.status}]"


def check_issue_ignore_label(issue: jira.Issue) -> Optional[str]:
    if JiraIssue.IGNORE_LABEL not in issue.fields.labels:
        return None
    return f"{JiraIssue.IGNORE_LABEL} is set"
