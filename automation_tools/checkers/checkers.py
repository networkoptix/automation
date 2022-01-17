import logging
import re
from typing import Optional, Set

import gitlab.v4.objects
from gitlab import GitlabGetError

import automation_tools.checkers.config as config
from automation_tools.jira import JiraIssue, JiraIssueStatus
from automation_tools.git import Repo


logger = logging.getLogger(__name__)


class WorkflowPolicyChecker:
    def __init__(self, project_keys: Set[str], repo: Repo = None):
        self._repo = repo
        self._project_keys = project_keys

    def run(self, issue: JiraIssue) -> Optional[str]:
        if not self.is_applicable(issue.project):
            return
        return self._class_specific_check_run(issue)

    def _class_specific_check_run(self):
        return

    def is_applicable(self, project_name_or_key: str) -> bool:
        project_name, *_ = project_name_or_key.partition("-")
        return project_name in self._project_keys


class WrongVersionChecker(WorkflowPolicyChecker):
    def _class_specific_check_run(self, issue: JiraIssue) -> Optional[str]:
        if issue.has_label(config.VERSION_SPECIFIC_LABEL):
            return

        if issue.project not in config.ALLOWED_VERSIONS_SETS:
            return

        version_set = set(issue.versions_to_branches_map.keys())
        if version_set in config.ALLOWED_VERSIONS_SETS[issue.project]:
            return

        return f"Version set {sorted(version_set)!r} is not allowed."


class BranchMissingChecker(WorkflowPolicyChecker):
    def _class_specific_check_run(self, issue: JiraIssue) -> Optional[str]:
        for version, branch in issue.versions_to_branches_map.items():
            # NOTE: Checking only recent commits as an optimization.
            if not self._repo.check_branch_exists(branch):
                return f"Branch {branch} (version: {version}) doesn't exist"
        return


class VersionMissingIssueCommitChecker(WorkflowPolicyChecker):
    def _class_specific_check_run(self, issue: JiraIssue) -> Optional[str]:
        issue_key = str(issue)
        for version, branch in issue.versions_to_branches_map.items():
            if issue.has_label(issue.already_in_version_label(version)):
                continue
            # NOTE: Checking only recent commits as an optimization.
            if len(self._repo.grep_recent_commits(issue_key, branch)) == 0:
                return f"No commits in {version} version (branch: {branch})"
        return


class MasterMissingIssueCommitChecker(WorkflowPolicyChecker):
    def _class_specific_check_run(self, issue: JiraIssue) -> Optional[str]:
        if issue.has_label(config.VERSION_SPECIFIC_LABEL):
            return

        issue_key = str(issue)
        if len(self._repo.grep_recent_commits(issue_key, "master")) == 0:
            return "No commits in master"


class IssueTypeChecker(WorkflowPolicyChecker):
    def _class_specific_check_run(self, issue: JiraIssue) -> Optional[str]:
        if issue.type_name in ["New Feature", "Epic", "Func Spec", "Tech Spec"]:
            return f"issue type [{issue.type_name}]"
        return


class IssueIsFixedChecker(WorkflowPolicyChecker):
    def _class_specific_check_run(self, issue: JiraIssue) -> Optional[str]:
        if issue.resolution in ["Fixed", "Done"]:
            return

        is_issue_done_externally = issue.has_label(config.DONE_EXTERNALLY_LABEL)
        if issue.status == JiraIssueStatus.qa and not is_issue_done_externally:
            return

        return f"issue resolution [{issue.resolution}], issue status [{issue.status}]"


class IssueIgnoreLabelChecker(WorkflowPolicyChecker):
    def _class_specific_check_run(self, issue: JiraIssue) -> Optional[str]:
        if issue.has_label(config.IGNORE_LABEL):
            return f"{config.IGNORE_LABEL} is set"
        return


class IgnoreIrrelevantProjectChecker(WorkflowPolicyChecker):
    def run(self, issue: JiraIssue) -> Optional[str]:
        if not self.is_applicable(issue.project):
            return f"issue project is {issue.project}"


class IgnoreIrrelevantVersionsChecker(WorkflowPolicyChecker):
    def __init__(self, project_keys: Set[str], relevant_versions: Set[str]):
        super().__init__(repo=None, project_keys=project_keys)
        self._relevant_versions = relevant_versions

    def _class_specific_check_run(self, issue: JiraIssue) -> Optional[str]:
        version_set = set(issue.versions_to_branches_map.keys())
        if not version_set.intersection(self._relevant_versions):
            return (
                f"No relevant version ({self._relevant_versions}) in fixVersions ({version_set})")
        return


class RelatedCommitAbsenceChecker(WorkflowPolicyChecker):
    def __init__(self, project_keys: Set[str], related_project: gitlab.v4.objects.Project):
        super().__init__(repo=None, project_keys=project_keys)
        self._related_project = related_project

    def _class_specific_check_run(self, issue: JiraIssue) -> Optional[str]:
        related_project_merged_branches = set()
        mr_ids = issue.get_related_merge_request_ids(
            project_path=self._related_project.path_with_namespace)
        for mr_id in mr_ids:
            try:
                merge_request = self._related_project.mergerequests.get(mr_id)
            except GitlabGetError as error:
                logger.debug(f"Can't get Merge Request {mr_id}: {error}")
                continue
            if merge_request.state != "merged":
                continue
            related_project_merged_branches.add(merge_request.target_branch)

        issue_branches = {b for b in issue.branches(exclude_already_merged=True) if b is not None}
        if not issue_branches.issubset(related_project_merged_branches):
            return (
                f"Must fix branches {issue_branches}; "
                f"merged branches: {related_project_merged_branches}")

        return
