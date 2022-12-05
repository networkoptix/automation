import datetime
from typing import Set, Dict, List, Optional
import logging
import re
from functools import lru_cache
import jira
import jira.exceptions

import automation_tools.utils
import automation_tools.jira_comments as jira_messages
import automation_tools.bot_info
from automation_tools.jira_helpers import (
    JiraError,
    JiraProjectConfig,
    JIRA_STATUS_REVIEW,
    JIRA_STATUS_PROGRESS,
    JIRA_STATUS_CLOSED,
    JIRA_STATUS_QA,
    JIRA_STATUS_READY_TO_MERGE,
    JIRA_STATUS_OPEN,
    JIRA_STATUS_INQA,
    JIRA_TRANSITION_WORKFLOW_FAILURE
)

logger = logging.getLogger(__name__)


class JiraIssue:
    UNKNOWN_BRANCH_NAME = "<unknown>"

    # Links to Merge Requests mentioning the Issues have a form
    # "<gitlab_url>/<path_to_project>/-/merge_requests/<mr_id>"
    # where
    # "gitlab_url" is a base url of the gitlab server (like "https://gitlab.lab.hdw.mx")
    # "path_to_project" has the format "<part1>/<part2>/.../<partN>"
    # "mr_id" is a numeric identifier of the Merge Request.
    _MERGE_REQUEST_LINK_RE = re.compile(
        r"//[\w\.]+?/(?P<repo_path>[\w\/]+)/\-/merge_requests/(?P<id>\d+)$")

    # Project-specific config which is redefined in subclasses.
    _project_config: JiraProjectConfig = {
        "statuses": {
            JIRA_STATUS_REVIEW: "In Review",
            JIRA_STATUS_PROGRESS: "In progress",
            JIRA_STATUS_CLOSED: "Closed",
            JIRA_STATUS_QA: "Waiting for QA",
            JIRA_STATUS_READY_TO_MERGE: "Ready to Merge",
            JIRA_STATUS_OPEN: "Open",
            JIRA_STATUS_INQA: "In QA",
        },
        "transitions": {
            JIRA_TRANSITION_WORKFLOW_FAILURE: "Workflow failure",
        }
    }

    @classmethod
    def _project_status_name(cls, key: str) -> Optional[str]:
        return cls._project_config["statuses"].get(key)

    @classmethod
    def _project_transition_name(cls, key: str) -> Optional[str]:
        return cls._project_config["transitions"].get(key)

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
        filter_expressions = []
        if closed_status := cls._project_status_name(JIRA_STATUS_CLOSED):
            filter_expressions.append(f'status = "{closed_status}" AND resolved >= -{period_min}m')
        if qa_status := cls._project_status_name(JIRA_STATUS_QA):
            filter_expressions.append(f'status = "{qa_status}" AND updated >= -{period_min}m')

        return f"({' OR '.join(filter_expressions)})" if filter_expressions else ''

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
            return set()

        mapping = self._version_to_branch_mapping
        issue = self._raw_issue
        labels = issue.fields.labels
        # Return branch names corresponding to the Release names specified in the `fixVersions`
        # field. A pre-defined string is returned instead of the branch name if the corresponding
        # branch name cannot be found for the Release.
        return {
            mapping.get(v.name, self.UNKNOWN_BRANCH_NAME) for v in issue.fields.fixVersions
            if not exclude_already_merged or self.already_in_version_label(v.name) not in labels}

    @property
    def versions_to_branches_map(self) -> Dict[str, str]:
        if not self._raw_issue.fields.fixVersions:
            return {}

        mapping = self._version_to_branch_mapping
        issue = self._raw_issue
        return {v.name: mapping.get(v.name, None) for v in issue.fields.fixVersions}

    @property
    def status(self) -> Optional[str]:
        return next(
            (
                standard_name
                for standard_name, project_status_name in self._project_config["statuses"].items()
                if project_status_name == self._raw_issue.fields.status.name
            ),
            None)

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

    def try_finalize(self) -> bool:
        logger.info(f"Trying to close issue {self}")

        if self.status in [JIRA_STATUS_CLOSED, JIRA_STATUS_QA]:
            self._add_comment(jira_messages.issue_already_finalized.format(status=self.status))
            logger.warning(f'Nothing to do: the Issue {self} already has status "{self.status}".')
            return True

        allowed_statuses = {JIRA_STATUS_PROGRESS, JIRA_STATUS_REVIEW, JIRA_STATUS_READY_TO_MERGE}
        if self.status not in allowed_statuses:
            raise JiraError(
                f"Cannot automatically move to QA or close the Issue {self} because of the wrong "
                f'status "{self._raw_issue.fields.status.name}".')

        if self.status == JIRA_STATUS_PROGRESS:
            logger.info(
              f'The Issue {self} is in "{self._project_status_name(JIRA_STATUS_PROGRESS)}" status '
              "- leaving it as is.")
            return False

        if self._set_status(JIRA_STATUS_QA, no_throw=True):
            self._add_comment(jira_messages.issue_moved_to_qa.format(
                branches="\n* ".join(self.branches())))
            logger.info(
                f'Status "{self._project_status_name(JIRA_STATUS_QA)}" is set for the Issue '
                f"{self}.")
            return True

        self._set_status(JIRA_STATUS_CLOSED)
        self._add_comment(
            jira_messages.issue_closed.format(branches="\n* ".join(self.branches())))
        logger.info(
            f'Status "{self._project_status_name(JIRA_STATUS_CLOSED)}" is set for the Issue '
            f'{self}.')

        return True

    def _set_status(self, target_status: str, no_throw=False) -> bool:
        review_transition_name = self._get_transition_name(target_status)
        if review_transition_name is None:
            if no_throw:
                return False

            raise JiraError(
                f'Unable to find a transition to move the Issue {self} of type "{self.type_name}" '
                f'from status "{self.status}" to status "{target_status}"')

        self._jira.transition_issue(self._raw_issue, review_transition_name)
        return True

    def _get_transition_name(self, target_status: str) -> str:
        transitions = [
            t for t in self._jira.transitions(self._raw_issue)
            if t["to"]["name"] == self._project_status_name(target_status)]
        return transitions[0]["name"] if transitions else None

    def return_issue(self, reason: str):
        issue = self._raw_issue
        try:
            logger.info(f'Reopening issue {issue.key}: {reason}')

            assert self.status in [JIRA_STATUS_QA, JIRA_STATUS_CLOSED], (
                f"Unexpected issue {issue.key} status {issue.fields.status}")

            self._jira.transition_issue(
                issue, self._project_transition_name(JIRA_TRANSITION_WORKFLOW_FAILURE))

            self._add_comment(jira_messages.reopen_issue.format(
                reason=reason,
                resolution=issue.fields.resolution))

        except jira.exceptions.JIRAError as error:
            self._add_comment(
                f'Unable to reopen issue {issue.key}: {error}. Forcing status '
                f'"{self._project_status_name(JIRA_STATUS_OPEN)}".')
            self._set_status(JIRA_STATUS_OPEN)

    def add_follow_ups_created_comment(self, branches: Set[str]):
        self._add_comment(
            jira_messages.follow_up_mrs_created.format(branches="\n* ".join(branches)))

    def add_follow_up_error_comment(self, error: Exception, mr_url: str):
        self._add_comment(
            jira_messages.follow_up_error.format(error=str(error), mr_url=mr_url))

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
            project_keys: Set[str],
            custom_project_configs: Dict[str, dict] = None):
        try:
            self._jira = jira.JIRA(
                server=url, basic_auth=(login, password), max_retries=retries, timeout=timeout)
            self.project_keys = set(project_keys)
            # Create classes for the Issues belonging to the Projects with non-default
            # configuration (custom statuses, transitions, etc.).
            if custom_project_configs:
                self._custom_issue_classes = {
                    key: type(f"JiraIssue{key}", (JiraIssue,), {'_project_config': config})
                    for key, config in custom_project_configs.items()}
            else:
                self._custom_issue_classes = dict()

        except jira.exceptions.JIRAError as error:
            raise JiraError(f"Unable to connect to {url} with {login}", error) from error

    def get_recently_closed_issues(self, period_min: int) -> List[JiraIssue]:
        issues = []

        standard_project_keys = self.project_keys - set(self._custom_issue_classes.keys())
        project_keys = '"' + '", "'.join(standard_project_keys) + '"'
        if closed_issues_filter := JiraIssue.closed_issues_filter(period_min):
            issues = self._get_issues_by_filter(
                f"project in ({project_keys}) AND {closed_issues_filter}")

        for project_key, issue_class in self._custom_issue_classes.items():
            if closed_issues_filter := issue_class.closed_issues_filter(period_min):
                issues += self._get_issues_by_filter(
                    f'project = "{project_key}" AND {closed_issues_filter}')

        return issues

    def _get_issues_by_filter(self, issues_filter: str):
        logger.debug(f'Searching issues with filter [{issues_filter}]')
        issues = []
        branch_mappings = self.version_to_branch_mappings()
        for raw_issue in self._jira.search_issues(issues_filter, maxResults=None):
            project = raw_issue.fields.project.key
            assert project in branch_mappings, (
                f"Internal logic error: project {project!r} is not in branch mappings.")
            issue_class = self._custom_issue_classes.get(project, JiraIssue)
            issues.append(issue_class(
                jira_handler=self._jira, issue=raw_issue, branch_mapping=branch_mappings[project]))

        return issues

    @lru_cache(maxsize=40)
    def get_issue(self, key: str) -> JiraIssue:
        try:
            raw_issue = self._jira.issue(key)
            project = raw_issue.fields.project.key
            branch_mapping = self.version_to_branch_mappings().get(project, {})
            issue_class = self._custom_issue_classes.get(project, JiraIssue)
            return issue_class(
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
