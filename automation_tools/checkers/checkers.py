## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from abc import ABC, abstractmethod
from typing import Optional, Dict
import logging

from automation_tools.jira import JiraIssue
from automation_tools.checkers.config import DONE_EXTERNALLY_LABEL, IGNORE_LABEL


logger = logging.getLogger(__name__)


class WorkflowPolicyChecker(ABC):
    """ All the subclasses of this class are expected to return `None` if the check is successful
    and the string containing information about the reason why the check failed otherwise. Check
    considered as successful if this check is not applicable to the Issue."""

    @abstractmethod
    def run(self, issue: JiraIssue) -> Optional[str]:
        """Validate the provided issue. Return `None` in case of success, error message otherwise.
"""
        return None


class VersionMissingIssueCommitChecker(WorkflowPolicyChecker):
    """Checks if the commit with the Issue key in the commit message exists in all the branches
    specified by the "fixVersions" field. Do not check branches marked using the label
    "already_in_<branch_name". Skip this check if the label "done_externally" presents."""

    def __init__(self, repos: Dict, repo_by_project: Dict):
        self._repos = repos
        self._repo_by_project = repo_by_project

    def run(self, issue: JiraIssue) -> Optional[str]:
        if issue.has_label(DONE_EXTERNALLY_LABEL):
            return None

        issue_key = str(issue)
        for version, branches in issue.versions_to_branches_map.items():
            if issue.has_label(issue.already_in_version_label(version)):
                continue

            if not branches:
                return f'''Branches are not set for version: {version}.
Most probably that means commits for this branch are not allowed. If that is not the case, set
branch for this version in the Project Settings.
'''
            for branch in branches:
                repo_key = (branch.project_path
                            if branch.project_path
                            else self._repo_by_project.get(issue.project))
                repo = self._repos.get(repo_key)
                if not repo_key or not repo:
                    return f'''Repo is not defined for branch {branch} (version: {version}).
This can mean script configuration error (missing project {issue.project}). Also you can define the
repo manually by updating the branch link in the Project Settings using form `<repo:branch>`, e.g
`<cloud_portal:master>`.
'''
                # This is a perfectly valid situation: the branch is closed already.
                if not repo.check_branch_exists(branch.branch_name):
                    return None

                # NOTE: Checking only recent commits as an optimization.
                if len(repo.grep_recent_commits(issue_key, branch.branch_name)) == 0:
                    return f"No commits in {version} version (branch: {branch}) in repo {repo_key}"
        return None


class IssueTypeChecker(WorkflowPolicyChecker):
    """Checks if the Type of the Issue is supported; ignore all other issue types."""

    def __init__(self, allowed_types: list[str]):
        self.allowed_types = allowed_types

    def run(self, issue: JiraIssue) -> Optional[str]:
        if issue.type_name not in self.allowed_types:
            return f"Issue type [{issue.type_name}]"
        return None


class IssueIsFixedChecker(WorkflowPolicyChecker):
    """Checks if the issue was closed with a Resolution which must be validated."""

    def __init__(self, allowed_resolutions: list[str]):
        self.allowed_resolutions = allowed_resolutions

    def run(self, issue: JiraIssue) -> Optional[str]:
        if issue.resolution not in self.allowed_resolutions:
            return f"issue resolution [{issue.resolution}], issue status [{issue.status}]"
        return None


class IssueIgnoreLabelChecker(WorkflowPolicyChecker):
    """Checks if the Issue does not have the label "hide_from_police"."""

    def run(self, issue: JiraIssue) -> Optional[str]:
        if issue.has_label(IGNORE_LABEL):
            return f"{IGNORE_LABEL} is set"
        return None


class IgnoreIrrelevantProjectChecker(WorkflowPolicyChecker):
    """Checks if the Issue belongs to the supported Project; ignore all other projects."""

    def __init__(self, project_keys: set[str]):
        self.project_keys = project_keys

    def run(self, issue: JiraIssue) -> Optional[str]:
        if issue.project not in self.project_keys:
            return f"Issue project is {issue.project}"
        return None
