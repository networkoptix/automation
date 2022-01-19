import datetime
from typing import Set, Dict, List, Optional
import logging
import re
from enum import Enum
from functools import lru_cache
import jira
import jira.exceptions

import automation_tools.utils
import automation_tools.jira_comments as jira_messages
import automation_tools.bot_info

logger = logging.getLogger(__name__)


class JiraError(automation_tools.utils.AutomationError):
    def __init__(self, message: str, jira_error: jira.exceptions.JIRAError = None):
        super().__init__(message + (': ' + str(jira_error) if jira_error else ""))


class JiraIssueStatus(Enum):
    review = "In Review"
    progress = "In progress"
    closed = "Closed"
    qa = "Waiting for QA"
    open = "Open"
    inqa = "In QA"

    def __str__(self):
        return str(self.value)


class JiraIssueTransition(Enum):
    Reopen = "Reopen"
    BackToDevelopment = "Back to Development"
    WorkflowFailure = "Workflow failure"

    def __str__(self):
        return str(self.value)


class JiraIssue:
    # Links to Merge Requests mentioning the Issues have a form
    # "<gitlab_url>/<path_to_project>/-/merge_requests/<mr_id>"
    # where
    # "gitlab_url" is a base url of the gitlab server (like "https://gitlab.lab.hdw.mx")
    # "path_to_project" has the format "<part1>/<part2>/.../<partN>"
    # "mr_id" is a numeric identifier of the Merge Request.
    _MERGE_REQUEST_LINK_RE = re.compile(
        r"//[\w\.]+?/(?P<repo_path>[\w\/]+)/\-/merge_requests/(?P<id>\d+)$")

    def __init__(
            self, jira_handler: jira.JIRA, issue: jira.Issue, branch_mapping: Dict[str, str]):
        self._raw_issue = issue
        self._jira = jira_handler
        self._version_to_branch_mapping = branch_mapping

    def __eq__(self, other):
        return self._raw_issue.key == other._raw_issue.key

    def __hash__(self):
        return hash(self._raw_issue.key)

    @staticmethod
    def already_in_version_label(version):
        return f"already_in_{version}"

    def _add_comment(self, message: str):
        bot_name, bot_revision = (
            automation_tools.bot_info.name(), automation_tools.bot_info.revision())

        if bot_name == "Robocat":
            template = jira_messages.template_robocat
        elif bot_name == "Police":
            template = jira_messages.template_police
        else:
            assert False, f"Unknown bot name: {bot_name}"

        self._jira.add_comment(
            self._raw_issue, template.format(message=message, revision=bot_revision))

    def __str__(self):
        return self._raw_issue.key

    @classmethod
    def closed_issues_filter(cls, period_min: int) -> str:
        return (
            f'(status = {JiraIssueStatus.closed} AND resolved >= -{period_min}m OR '
            f'status = "{JiraIssueStatus.qa}" AND updated >= -{period_min}m)')

    def get_related_merge_request_ids(self, project_path: str = None) -> Set[int]:
        issue = self._raw_issue
        logger.debug(f"Obtaining branches with merge requests for issue {self}")

        mr_ids = set()
        try:
            for link in self._jira.remote_links(issue):
                logger.debug(f"Remote link for {self} found: {link}")
                gitlab_mr_id = self._extract_mr_id_from_link(link, project_path)
                if gitlab_mr_id is None:
                    continue
                mr_ids.add(gitlab_mr_id)

        except jira.exceptions.JIRAError as error:
            raise JiraError(
                "Unable to get branches with merge requests for issue "
                f"{issue.key}: {error}") from error

        return mr_ids

    def _extract_mr_id_from_link(
            self, link: jira.resources.RemoteLink, project_path: str = None) -> int:
        link_match = self._MERGE_REQUEST_LINK_RE.search(link.object.url)
        if not link_match:
            return None
        if project_path and link_match["repo_path"] != project_path:
            return None
        return int(link_match["id"])

    def branches(self, exclude_already_merged: bool = False) -> Set[str]:
        if not self._raw_issue.fields.fixVersions:
            return []

        mapping = self._version_to_branch_mapping
        issue = self._raw_issue
        labels = issue.fields.labels
        return {
            mapping.get(v.name, None) for v in issue.fields.fixVersions
            if not exclude_already_merged or self.already_in_version_label(v.name) not in labels}

    @property
    def versions_to_branches_map(self) -> Dict[str, str]:
        if not self._raw_issue.fields.fixVersions:
            return {}

        mapping = self._version_to_branch_mapping
        issue = self._raw_issue
        return {v.name: mapping.get(v.name, None) for v in issue.fields.fixVersions}

    @property
    def status(self) -> JiraIssueStatus:
        for status in JiraIssueStatus:
            if str(status) == self._raw_issue.fields.status.name:
                return status
        return None

    @property
    def resolution(self) -> Optional[str]:
        raw_issue = self._raw_issue
        return str(raw_issue.fields.resolution.name) if raw_issue.fields.resolution else None

    @property
    def fixVersions(self) -> List[str]:
        if not self._raw_issue.fields.fixVersions:
            return []
        return [v.name for v in self._raw_issue.fields.fixVersions]

    @property
    def type_name(self) -> str:
        return self._raw_issue.fields.issuetype.name

    @property
    def project(self) -> str:
        return self._raw_issue.fields.project.key

    def try_finalize(self):
        logger.info(f"Trying to close issue {self}")

        if self.status in [JiraIssueStatus.closed, JiraIssueStatus.qa]:
            logger.info(f'Nothing to do: issue {self} already has status {self.status}.')
            return

        if self.status not in [JiraIssueStatus.progress, JiraIssueStatus.review]:
            raise JiraError(
                f"Cannot automatically move to QA or close Issue {self} because of the wrong "
                f'status "{self._raw_issue.fields.status.name}".')

        if self.status == JiraIssueStatus.progress:
            self._set_status(JiraIssueStatus.review)

        if self._set_status(JiraIssueStatus.qa, no_throw=True):
            self._add_comment(jira_messages.issue_moved_to_qa.format(
                branches="\n* ".join(self.branches())))
            logger.info(f'Status "Waiting for QA" is set for issue {self}.')
            return

        self._set_status(JiraIssueStatus.closed)
        self._add_comment(
            jira_messages.issue_closed.format(branches="\n* ".join(self.branches())))
        logger.info(f'Status "Closed" is set for issue {self}.')

    def _set_status(self, target_status: JiraIssueStatus, no_throw=False) -> bool:
        review_transition_name = self._get_transition_name(target_status)
        if review_transition_name is None:
            if no_throw:
                return False

            raise JiraError(
                f'Unable to find a transition to move issue {self} of type "{self.type_name}" '
                f'from status "{self.status}" to status "{target_status}"')

        self._jira.transition_issue(self._raw_issue, review_transition_name)
        return True

    def _get_transition_name(self, target_status: JiraIssueStatus) -> str:
        transitions = [
            t for t in self._jira.transitions(self._raw_issue)
            if t["to"]["name"] == str(target_status)]
        return transitions[0]["name"] if transitions else None

    def return_issue(self, reason: str):
        issue = self._raw_issue
        try:
            logger.info(f'Reopening issue {issue.key}: {reason}')

            assert self.status in [JiraIssueStatus.qa, JiraIssueStatus.closed], (
                f"Unexpected issue {issue.key} status {issue.fields.status}")

            self._jira.transition_issue(issue, str(JiraIssueTransition.WorkflowFailure))

            self._add_comment(jira_messages.reopen_issue.format(
                reason=reason,
                resolution=issue.fields.resolution))

        except jira.exceptions.JIRAError as error:
            self._add_comment(f'Unable to reopen issue {issue.key}: {error}. Forcing state "Open"')
            self._set_status(JiraIssueStatus.open)

    def add_followups_created_comment(self, branches: Set[str]):
        self._add_comment(
            jira_messages.followup_mrs_created.format(branches="\n* ".join(branches)))

    def add_followup_error_comment(self, error: Exception, mr_url: str):
        self._add_comment(
            jira_messages.followup_error.format(error=str(error), mr_url=mr_url))

    def has_label(self, label: str) -> bool:
        return label in self._raw_issue.fields.labels

    def add_already_in_version_label(self, branch: str):
        version = next(v for v, b in self.versions_to_branches_map.items() if b == branch)
        self._add_label(self.already_in_version_label(version))

    def _add_label(self, label: str):
        self._raw_issue.fields.labels.append(label)
        self._raw_issue.update(fields={"labels": self._raw_issue.fields.labels})


class JiraAccessor:
    def __init__(
            self,
            url: str,
            login: str,
            password: str,
            timeout: int,
            retries: int,
            project_keys: Set[str]):
        try:
            self._jira = jira.JIRA(
                server=url, basic_auth=(login, password), max_retries=retries, timeout=timeout)
            self.project_keys = project_keys

        except jira.exceptions.JIRAError as error:
            raise JiraError(f"Unable to connect to {url} with {login}", error) from error

    def get_recently_closed_issues(self, period_min: int) -> List[JiraIssue]:
        closed_issues_filter = JiraIssue.closed_issues_filter(period_min)
        projects_string = '"' + '", "'.join(self.project_keys) + '"'
        project_closed_issues_filter = f"project in ({projects_string}) AND {closed_issues_filter}"
        logger.debug(f'Searching issues with filter [{project_closed_issues_filter}]')

        issues = []
        branch_mappings = self.version_to_branch_mappings()
        for raw_issue in self._jira.search_issues(project_closed_issues_filter, maxResults=None):
            project = raw_issue.fields.project.key
            assert project in branch_mappings, (
                f"Internal logic error: project {project!r} is not in branch mappings.")
            issues.append(JiraIssue(
                jira_handler=self._jira, issue=raw_issue, branch_mapping=branch_mappings[project]))

        return issues

    @lru_cache(maxsize=40)
    def get_issue(self, key: str) -> JiraIssue:
        try:
            raw_issue = self._jira.issue(key)
            project = raw_issue.fields.project.key
            branch_mapping = self.version_to_branch_mappings().get(project, {})
            return JiraIssue(
                jira_handler=self._jira, issue=raw_issue, branch_mapping=branch_mapping)

        except jira.exceptions.JIRAError as error:
            raise JiraError(f"Unable to obtain issue {key}", error) from error

    def get_issues(self, keys: Set[str]) -> Set[JiraIssue]:
        return {self.get_issue(k) for k in keys}

    @automation_tools.utils.cached(datetime.timedelta(minutes=10))
    def version_to_branch_mappings(self) -> Dict[str, Dict[str, str]]:
        return {p: self._version_to_branch_mapping(p) for p in self.project_keys}

    def _version_to_branch_mapping(self, project: str) -> Dict[str, str]:
        try:
            mapping = {}
            for v in self._jira.project_versions(project):
                if v.archived:
                    continue
                branch = branch_from_release(v)
                if not branch:
                    logger.warning(f"Version {v.name} doesn't have branch in description")
                else:
                    mapping[v.name] = branch

            mapping = {k: mapping[k] for k in sorted(mapping, reverse=True)}
            logger.debug(f"For project {project} got mapping from jira releases: {mapping}")
            return mapping

        except jira.exceptions.JIRAError as error:
            raise JiraError("Unable to get release versions", error) from error


def branch_from_release(version: jira.resources.Version):
    if not hasattr(version, "description"):
        return None
    match = re.search(r"<(.+)>", version.description)
    if not match:
        return None
    return match.group(1)
