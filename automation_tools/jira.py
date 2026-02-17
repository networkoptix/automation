## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional
import datetime
import logging
import re

import jira
import jira.exceptions
import jira.resources

from automation_tools.jira_comments import (
    JiraComment, JiraCommentDataKey, JiraCommentError, JiraMessageId)
from automation_tools.jira_helpers import (
    JiraError,
    JiraStatusChangeError,
    JiraProjectConfig,
    JIRA_STATUS_REVIEW,
    JIRA_STATUS_PROGRESS,
    JIRA_STATUS_CLOSED,
    JIRA_STATUS_QA,
    JIRA_STATUS_READY_TO_MERGE,
    JIRA_STATUS_OPEN,
    JIRA_STATUS_INQA,
    JIRA_STATUS_VERIFICATION,
    JIRA_TRANSITION_WORKFLOW_FAILURE)
import automation_tools.bot_info
import automation_tools.utils
import automation_tools.jira_comments as jira_messages

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitlabBranchDescriptor:
    branch_name: Optional[str]
    project_path: Optional[str] = None

    def __str__(self):
        project_prefix = f"{self.project_path}:" if self.project_path else ""
        return f"{project_prefix}{self.branch_name}"

    def __bool__(self):
        return self.branch_name is not None

    def __eq__(self, other):
        return self.branch_name == other.branch_name and self.project_path == other.project_path

    @classmethod
    def from_string(cls, branch_str: str) -> "GitlabBranchDescriptor":
        try:
            path, branch = branch_str.split(":")
            return cls(project_path=path, branch_name=branch)
        except ValueError:
            return cls(branch_name=branch_str)

    @classmethod
    def unknown(cls) -> "GitlabBranchDescriptor":
        return cls(branch_name=None)


VersionToBranchesMapping = dict[str, list[GitlabBranchDescriptor]]


class JiraIssue:
    # Links to Merge Requests mentioning the Issues have a form
    # "<gitlab_url>/<path_to_project>/-/merge_requests/<mr_id>"
    # where
    # "gitlab_url" is a base url of the gitlab server (like "https://gitlab.example.com")
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
            JIRA_STATUS_VERIFICATION: "Pending Verification",
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
            self,
            jira_handler: jira.JIRA,
            issue: jira.Issue,
            branch_mapping: VersionToBranchesMapping):
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

    def add_comment(self, comment: JiraComment):
        self._jira.add_comment(self._raw_issue, str(comment))

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

    def get_related_merge_request_ids(self, project_path: str = None) -> set[int]:
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
            self, link: jira.resources.RemoteLink, project_path: Optional[str] = None) -> int:
        link_match = self._MERGE_REQUEST_LINK_RE.search(link.object.url)
        if not link_match:
            return None
        if project_path and link_match["repo_path"] != project_path:
            return None
        return int(link_match["id"])

    def branches(self, exclude_already_merged: bool = False) -> set[GitlabBranchDescriptor]:
        mapping = self._version_to_branch_mapping
        issue = self._raw_issue
        labels = issue.fields.labels
        # Return branch names corresponding to the Release names specified in the `fixVersions`
        # field.
        result = set()
        for v in (issue.fields.fixVersions or []):
            if exclude_already_merged and self.already_in_version_label(v.name) in labels:
                continue
            result.update(mapping.get(v.name, []))

        return result

    def declared_merged_branches(self) -> dict[GitlabBranchDescriptor, set[int]]:
        result = {}
        for comment in self.bot_comments(message_ids=[JiraMessageId.MrMergedToBranch]):
            assert comment.data
            if not (raw_branch_name := str(comment.data.get(JiraCommentDataKey.MrBranch.name))):
                logger.error(f"Malformed '{JiraMessageId.MrMergedToBranch}' comment: {comment!r}")
                continue

            branch = GitlabBranchDescriptor.from_string(raw_branch_name)
            if (original_mr_id := comment.data.get(JiraCommentDataKey.OriginalMrId.name)):
                result.setdefault(branch, set()).add(int(original_mr_id))
            elif branch not in result:
                result[branch] = set()

        return result

    def bot_comments(self, message_ids: Optional[Iterable] = None) -> list[JiraComment]:
        result = []
        current_user = get_current_jira_user(self._jira)
        current_user_comment_texts = (
            c.body
            for c in self._jira.comments(self._raw_issue)
            if c.author.emailAddress == current_user.email)
        for comment_text in current_user_comment_texts:
            try:
                comment = JiraComment.from_string(comment_text)
            except JiraCommentError as e:
                logger.warning(f"Failed to parse comment: {e}")
                continue
            if comment and (not message_ids or comment.message_id in message_ids):
                result.append(comment)
        return result

    def has_bot_comment(
            self, message_id: JiraMessageId, params: dict[JiraCommentDataKey, str] = None) -> bool:
        for comment in self.bot_comments(message_ids=[message_id]):
            if not params or all(comment.data.get(k.name) == v for k, v in params.items()):
                return True
        return False

    @property
    def versions_to_branches_map(self) -> VersionToBranchesMapping:
        mapping = self._version_to_branch_mapping
        issue = self._raw_issue
        return {v.name: mapping.get(v.name, []) for v in (issue.fields.fixVersions or [])}

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
    def raw_status(self) -> str:
        return self._raw_issue.fields.status.name

    @property
    def resolution(self) -> Optional[str]:
        raw_issue = self._raw_issue
        return str(raw_issue.fields.resolution.name) if raw_issue.fields.resolution else None

    @property
    def fixVersions(self) -> list[str]:
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

        if self.status in [JIRA_STATUS_CLOSED, JIRA_STATUS_QA, JIRA_STATUS_VERIFICATION]:
            # Check if the Issue was moved to this state by the bot. No warning if it was.
            # TODO: Consider removing adding the comment because even if the Issue was closed by
            # the bot, the situation still can be a workflow violation; on the other hand, it is
            # not a big deal, so the value of this warning is questionable.
            is_closed_by_bot = (
                self.status == JIRA_STATUS_CLOSED
                and self.has_bot_comment(message_id=JiraMessageId.IssueClosed))
            is_moved_to_qa_by_bot = (
                self.status == JIRA_STATUS_QA
                and self.has_bot_comment(message_id=JiraMessageId.IssueMovedToQa))
            is_set_for_verification = (
                self.status == JIRA_STATUS_VERIFICATION
                and self.has_bot_comment(message_id=JiraMessageId.IssueReadyToVerify))
            if is_closed_by_bot or is_moved_to_qa_by_bot or is_set_for_verification:
                return True
            self.add_comment(JiraComment(
                JiraMessageId.IssueAlreadyFinalized, {"status": self.status}))
            logger.warning(f'Nothing to do: the Issue {self} already has status "{self.status}".')
            return True

        allowed_statuses = {JIRA_STATUS_PROGRESS, JIRA_STATUS_REVIEW, JIRA_STATUS_READY_TO_MERGE}
        if self.status not in allowed_statuses:
            raise JiraStatusChangeError(
                f"Cannot automatically move to QA or close the Issue {self} because of the wrong "
                f'status "{self._raw_issue.fields.status.name}".')

        if self.status == JIRA_STATUS_PROGRESS:
            logger.info(
                f'The Issue {self} is in "{self._project_status_name(JIRA_STATUS_PROGRESS)}"'
                " status - leaving it as is.")
            return False

        if self._set_status(JIRA_STATUS_QA, no_throw=True):
            self.add_comment(JiraComment(
                message_id=JiraMessageId.IssueMovedToQa,
                params={"branches": "\n* ".join((str(b) for b in self.branches()))}))
            logger.info(
                f'Status "{self._project_status_name(JIRA_STATUS_QA)}" is set for the Issue '
                f"{self}.")
            return True

        if self._set_status(JIRA_STATUS_VERIFICATION, no_throw=True):
            self.add_comment(JiraComment(message_id=JiraMessageId.IssueReadyToVerify, params={}))
            logger.info(
                f'Status "{self._project_status_name(JIRA_STATUS_VERIFICATION)}" is set for the '
                f"Issue {self}.")
            return True

        self._set_status(JIRA_STATUS_CLOSED)
        self.add_comment(JiraComment(
            message_id=JiraMessageId.IssueClosed,
            params={"branches": "\n* ".join((str(b) for b in self.branches()))}))
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

            self.add_comment(JiraComment(
                message_id=JiraMessageId.ReopenIssue,
                params={"reason": reason, "resolution": str(issue.fields.resolution)}))

        except jira.exceptions.JIRAError as error:
            self.add_comment(JiraComment(
                message_id=JiraMessageId.UnableToReopenIssue,
                params={
                    "issue": issue.key,
                    "error": str(error),
                    "status": str(self._project_status_name(JIRA_STATUS_OPEN)),
                }))
            self._set_status(JIRA_STATUS_OPEN)

    def has_label(self, label: str) -> bool:
        return label in self._raw_issue.fields.labels

    def add_already_in_version_label(self, branch_name: str, project_path: str):
        branch_to_add = GitlabBranchDescriptor(project_path=project_path, branch_name=branch_name)
        for version, branches in self.versions_to_branches_map.items():
            if any(b == branch_to_add for b in branches):
                self._add_label(self.already_in_version_label(version))
                return

    def _add_label(self, label: str):
        self._raw_issue.fields.labels.append(label)
        self._raw_issue.update(fields={"labels": self._raw_issue.fields.labels})

    @property
    def assignee(self) -> Optional[automation_tools.utils.User]:
        assignee = self._raw_issue.fields.assignee
        if assignee is None:
            return None
        return automation_tools.utils.User(
            name=assignee.displayName, email=assignee.emailAddress, username=assignee.accountId)


class JiraAccessor:
    def __init__(
            self,
            url: str,
            login: str,
            password: str,
            timeout: int,
            retries: int,
            project_keys: set[str],
            custom_project_configs: dict[str, dict] = None):
        try:
            self._jira = jira.JIRA(
                server=url, basic_auth=(login, password), max_retries=retries, timeout=timeout)
            self.project_keys = set(project_keys)
            # Create classes for the Issues belonging to the Projects with non-default
            # configuration (custom statuses, transitions, etc.).
            # TODO: Check, why we need _custom_issue_classes field - it is not used anywhere.
            if custom_project_configs:
                self._custom_issue_classes = {
                    key: type(f"JiraIssue{key}", (JiraIssue,), {'_project_config': config})
                    for key, config in custom_project_configs.items()}
            else:
                self._custom_issue_classes = dict()

        except jira.exceptions.JIRAError as error:
            raise JiraError(f"Unable to connect to {url} with {login}", error) from error

    def get_recently_closed_issues(self, period_min: int) -> list[JiraIssue]:
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
        for raw_issue in self._jira.enhanced_search_issues(issues_filter, maxResults=0):
            project = raw_issue.fields.project.key
            assert project in branch_mappings, (
                f"Internal logic error: project {project!r} is not in branch mappings.")
            issue_class = self._custom_issue_classes.get(project, JiraIssue)
            issues.append(issue_class(
                jira_handler=self._jira, issue=raw_issue, branch_mapping=branch_mappings[project]))

        return issues

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

    def get_issues(self, keys: set[str]) -> list[JiraIssue]:
        return {self.get_issue(k) for k in keys}

    @automation_tools.utils.cached(datetime.timedelta(minutes=10))
    def version_to_branch_mappings(self) -> dict[str, VersionToBranchesMapping]:
        return {p: self._version_to_branch_mapping(p) for p in self.project_keys}

    def _version_to_branch_mapping(self, project: str) -> VersionToBranchesMapping:
        try:
            mapping = {}
            for v in self._jira.project_versions(project):
                if v.archived:
                    continue
                branches = branches_from_release(v)
                if not branches:
                    logger.debug(f"Version {v.name} doesn't have branches in description")
                else:
                    mapping[v.name] = branches

            mapping = {k: mapping[k] for k in sorted(mapping, reverse=True)}
            logger.debug(f"For project {project} got mapping from jira releases: {mapping}")
            return mapping

        except jira.exceptions.JIRAError as error:
            raise JiraError("Unable to get release versions", error) from error


def branches_from_release(version: jira.resources.Version) -> list[GitlabBranchDescriptor]:
    if not hasattr(version, "description"):
        return None
    matches = re.findall(r"<(.+?)>", version.description)
    if not matches:
        return []
    return [GitlabBranchDescriptor.from_string(m) for m in matches]


@lru_cache
def get_current_jira_user(jira_object: jira.JIRA) -> automation_tools.utils.User:
    user_info = jira_object.myself()
    return automation_tools.utils.User(
        name=user_info["displayName"],
        email=user_info["emailAddress"],
        username=user_info["accountId"])
