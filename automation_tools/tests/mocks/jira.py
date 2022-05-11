import os
import re
from typing import List, Optional

import jira.exceptions

from automation_tools.tests.mocks.issue import JiraIssue
from automation_tools.tests.mocks.resources import (
    Version, RemoteLink, Status, IssueType, Comment, Resolution)


class Jira:
    def __init__(self, **_):
        self._issues = {}

    def issue(self, key):
        try:
            return self._issues[key]
        except KeyError:
            raise jira.exceptions.JIRAError

    def search_issues(self, issue_filter, **__):
        issues = []
        match = re.match(r"project in \((?P<projects_string>.+?)\)", issue_filter)
        for key, issue in self._issues.items():
            project, _, __ = key.partition("-")
            if project in [p.strip('" ') for p in match.group('projects_string').split(',')]:
                issues.append(issue)
        return issues

    def add_mock_issue(
            self, key: str, state: str = "Open", typ: str = "Internal",
            branches: List[str] = None,
            merge_requests: List[int] = None,
            labels: List[str] = None,
            comments_list: List[str] = None,
            resolution: Optional[str] = None):
        project, _, __ = key.partition("-")
        fixVersions = []
        for branch in branches:
            versions = [
                v for v in self.project_versions(project)
                if v.description.startswith(f"<{branch}>")]
            if versions:
                fixVersions.append(versions[0])

        gitlab_host_url = os.getenv("CI_SERVER_URL", "https://gitlab.nxvms.dev")
        remoteLinks = [
            RemoteLink(f"{gitlab_host_url}/dev/nx/-/merge_requests/{mr_id}")
            for mr_id in (merge_requests or [])]
        comments = [Comment(body=c) for c in (comments_list or [])]
        status = Status(state)
        issuetype = IssueType(typ)

        self._issues[key] = JiraIssue(key=key, comments=comments, fields={
                "fixVersions": fixVersions,
                "remoteLinks": remoteLinks,
                "resolution": Resolution(resolution),
                "status": status,
                "labels": labels if labels is not None else [],
                "issuetype": issuetype})

    @staticmethod
    def project_versions(project: str):
        return {
            "VMS": [
                Version("4.2", "<vms_4.2> Major release with plugins"),
                Version("4.2_patch", "<vms_4.2_patch> 4.2 Monthly patches"),
                Version("5.0", "<vms_5.0> 5.0 Release"),
                Version("5.0_patch", "<vms_5.0_patch> 5.2 Monthly patches"),
                Version("master", "<master> Major release with a lot of tech debt")
            ],
            "MOBILE": [
                Version("20.3", "<mobile_20.3>"),
                Version("20.4", "<mobile_20.4>"),
                Version("21.1", "<mobile_21.1>"),
                Version("22.1", "<mobile_22.1>"),
                Version("master", "<master> Ongoing development"),
            ],
            "CB": [
                Version("20.1", "<cloud_backend_20.1>"),
                Version("master", "<master>"),
            ],
            "CLOUD": [
                Version("21.1", ""),
                Version("master", "<master>"),
                Version("5.0", "<vms_5.0>"),
                Version("5.0_patch", "<vms_5.0_patch>"),
            ],
        }.get(project, {})

    @staticmethod
    def transitions(issue: JiraIssue = None):
        if issue.fields.status.name == "Closed":
            return [
                {"name": "Reopen", "to": {"name": "Open"}},
                {"name": "Workflow failure", "to": {"name": "In Review"}},
                {"name": "Update Resolution", "to": {"name": "Closed"}}]

        if issue.fields.status.name == "In Review":
            if issue.fields.issuetype.name == "Internal":
                return [
                    {"name": "Back to development", "to": {"name": "In progress"}},
                    {"name": "Close", "to": {"name": "Closed"}}]
            return [
                {"name": "Merged", "to": {"name": "Waiting for QA"}},
                {"name": "Review Failed", "to": {"name": "In progress"}}]

        if issue.fields.status.name == "Ready to Merge":
            if issue.fields.issuetype.name == "Internal":
                assert False, (
                    'Bad test condition: "Internal" Issues do not have "Ready to Merge" state.')
            return [
                {"name": "Merged", "to": {"name": "Waiting for QA"}},
                {"name": "Review Failed", "to": {"name": "In progress"}}]

        if issue.fields.status.name == "In progress":
            return [
                {"name": "Stop development", "to": {"name": "Open"}},
                {"name": "Review", "to": {"name": "In Review"}}]

        if issue.fields.status.name == "Open":
            return [
                {"name": "Start development", "to": {"name": "In progress"}},
                {"name": "Close", "to": {"name": "Closed"}}]

        if issue.fields.status.name == "Waiting for QA":
            return [
                {"name": "Reject", "to": {"name": "Closed"}},
                {"name": "Back to Development", "to": {"name": "In progress"}},
                {"name": "Workflow failure", "to": {"name": "In Review"}},
                {"name": "I'll test it", "to": {"name": "In QA"}}]

        return []

    @staticmethod
    def remote_links(issue: JiraIssue):
        return issue.fields.remoteLinks

    def transition_issue(self, issue: JiraIssue, transition: str):
        transition_dict = next(t for t in self.transitions(issue) if t["name"] == transition)
        issue.fields.status.name = transition_dict["to"]["name"]

    @staticmethod
    def add_comment(issue: JiraIssue, comment: str):
        issue.fields.comment.comments.append(Comment(body=comment))
