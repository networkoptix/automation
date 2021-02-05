from typing import Set, Dict
import logging
import datetime
import re
from enum import Enum
from functools import lru_cache
import jira
import jira.exceptions

import automation_tools.utils
import automation_tools.jira_comments as jira_messages
from automation_tools import bot_versions

logger = logging.getLogger(__name__)


class JiraError(automation_tools.utils.Error):
    def __init__(self, message: str, jira_error: jira.exceptions.JIRAError = None):
        super().__init__(message + (': ' + str(jira_error) if jira_error else ""))


class JiraIssueStatus(Enum):
    review = "In Review"
    progress = "In progress"
    closed = "Closed"
    qa = "Waiting for QA"

    def __str__(self):
        return str(self.value)


class JiraIssueTransition(Enum):
    Reopen = "Reopen"
    BackToDevelopment = "Back to Development"

    def __str__(self):
        return str(self.value)


class JiraIssue:
    _MERGE_REQUEST_LINK_RE = re.compile(r"/merge_requests/(?P<id>\d+)$")

    def __init__(
            self, jira_handler: jira.JIRA, issue: jira.Issue,
            branch_mapping: Dict[str, str], dry_run: bool = False):
        self._raw_issue = issue
        self._jira = jira_handler
        self._dry_run = dry_run
        self._version_to_branch_mapping = branch_mapping

    def __eq__(self, other):
        return self._raw_issue.key == other._raw_issue.key

    def __hash__(self):
        return hash(self._raw_issue.key)

    def _add_robocat_comment(self, message: str):
        self._jira.add_comment(
            self._raw_issue,
            jira_messages.template_robocat.format(
                message=message,
                version=automation_tools.bot_versions.RobocatVersion))

    def _add_police_comment(self, message: str):
        self._jira.add_comment(
            self._raw_issue,
            jira_messages.template_police.format(
                message=message,
                version=automation_tools.bot_versions.PoliceVersion))

    def __str__(self):
        return self._raw_issue.key

    @classmethod
    def closed_issues_filter(cls, period_min: int) -> str:
        return (
            f'(status = {JiraIssueStatus.closed} AND resolved >= -{period_min}m OR '
            f'status = "{JiraIssueStatus.qa}" AND updated >= -{period_min}m)')

    def get_related_merge_request_ids(self) -> Set[int]:
        issue = self._raw_issue
        logger.debug(f"Obtaining branches with merge requests for issue {self}")

        mr_ids = set()
        try:
            for link in self._jira.remote_links(issue):
                logger.debug(f"Remote link for {self} found: {link}")
                gitlab_mr_id = self._extract_mr_id_from_link(link)
                if gitlab_mr_id is None:
                    continue
                mr_ids.add(gitlab_mr_id)

        except jira.exceptions.JIRAError as error:
            raise JiraError(
                "Unable to get branches with merge requests for issue "
                f"{issue.key}: {error}") from error

        return mr_ids

    def _extract_mr_id_from_link(self, link: jira.resources.RemoteLink) -> int:
        link_match = self._MERGE_REQUEST_LINK_RE.search(link.object.url)
        if link_match:
            return int(link_match["id"])
        return None

    @property
    def branches(self) -> Set[str]:
        mapping = self._version_to_branch_mapping
        issue = self._raw_issue
        return {mapping[automation_tools.utils.Version(v.name)] for v in issue.fields.fixVersions}

    @property
    def status(self) -> JiraIssueStatus:
        for status in JiraIssueStatus:
            if str(status) == self._raw_issue.fields.status.name:
                return status
        return None

    @property
    def type_name(self) -> str:
        return self._raw_issue.fields.issuetype.name

    def try_finalize(self):
        logger.info(f"Trying to close issue {self}")
        if self._dry_run:
            return

        if self.status in [JiraIssueStatus.closed, JiraIssueStatus.qa]:
            logger.info(f'Nothing to do: issue {self} already has status {self.status}.')
            return

        if self.status not in [JiraIssueStatus.progress, JiraIssueStatus.review]:
            raise JiraError(
                f"Cannot automatically move to QA or close Issue {self} because of the wrong status "
                f'"{self._raw_issue.fields.status.name}".')

        if self.status == JiraIssueStatus.progress:
            self._set_status(JiraIssueStatus.review)

        if self._set_status(JiraIssueStatus.qa, no_throw=True):
            self._add_robocat_comment(jira_messages.issue_moved_to_qa.format(
                branches="\n* ".join(self.branches)))
            logger.info(f'Status "Waiting for QA" is set for issue {self}.')
            return

        self._set_status(JiraIssueStatus.closed)
        self._add_robocat_comment(
            jira_messages.issue_closed.format(branches="\n* ".join(self.branches)))
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
            if self._dry_run:
                return

            if self.status == JiraIssueStatus.closed:
                self._jira.transition_issue(issue, str(JiraIssueTransition.Reopen))
            elif self.status == JiraIssueStatus.qa:
                self._jira.transition_issue(issue, str(JiraIssueTransition.BackToDevelopment))
            else:
                assert False, f"Unexpected issue {issue.key} status {issue.fields.status}"

            self._add_police_comment(jira_messages.reopen_issue.format(
                reason=reason,
                resolution=issue.fields.resolution))

        except jira.exceptions.JIRAError as error:
            raise JiraError(f"Unable to reopen issue {issue.key}: {error}") from error

    def add_followups_created_comment(self, branches: Set[str]):
        self._add_robocat_comment(
            jira_messages.followup_mrs_created.format(branches="\n* ".join(branches)))

    def add_followup_error_comment(self, error: Exception, mr_url: str):
        self._add_robocat_comment(
            jira_messages.followup_error.format(error=str(error), mr_url=mr_url))


class JiraAccessor:
    project = "VMS"

    def __init__(
            self, url: str, login: str, password: str,
            timeout: int, retries: int, dry_run: bool = False):
        try:
            self._jira = jira.JIRA(
                server=url, basic_auth=(login, password), max_retries=retries, timeout=timeout)
            self._dry_run = dry_run

        except jira.exceptions.JIRAError as error:
            raise JiraError(f"Unable to connect to {url} with {login}", error) from error

    def get_recently_closed_issues(self, period_min: int):
        closed_issues_filter = JiraIssue.closed_issues_filter(period_min)
        project_closed_issues_filter = f"project = {self.project} AND {closed_issues_filter}"
        logger.debug(f'Searching issues with filter [{project_closed_issues_filter}]')
        return self._jira.search_issues(project_closed_issues_filter, maxResults=None)

    @lru_cache(maxsize=8)
    def get_issue(self, key: str) -> JiraIssue:
        try:
            return JiraIssue(
                jira_handler=self._jira, issue=self._jira.issue(key),
                branch_mapping=self.version_to_branch_mapping(), dry_run=self._dry_run)

        except jira.exceptions.JIRAError as error:
            raise JiraError(f"Unable to obtain issue {key}", error) from error

    def get_issues(self, keys: Set[str]) -> Set[JiraIssue]:
        return {self.get_issue(k) for k in keys}

    # TODO: Refactor workflow-police bot for working with JiraIssue object instead of raw
    # jira.Issue.
    def return_issue(self, issue: jira.Issue, reason: str, dry_run: bool):
        jira_issue = JiraIssue(
            jira_handler=self._jira, issue=issue,
            branch_mapping=self.version_to_branch_mapping(), dry_run=dry_run)
        return jira_issue.return_issue(reason)

    @automation_tools.utils.cached(datetime.timedelta(minutes=10))
    def version_to_branch_mapping(self):
        try:
            mapping = {}
            for v in self._jira.project_versions(self.project):
                if v.archived:
                    continue
                branch = branch_from_release(v)
                if not branch:
                    logger.warning(f"Version {v.name} doesn't have branch in description")
                else:
                    mapping[automation_tools.utils.Version(v.name)] = branch

            mapping = {k: mapping[k] for k in sorted(mapping, reverse=True)}
            logger.debug(f"Got mapping from jira releases: {mapping}")
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
