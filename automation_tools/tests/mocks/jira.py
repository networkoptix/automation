## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import os
import re
from typing import Optional

import jira.exceptions

from automation_tools.tests.gitlab_constants import DEFAULT_USER
from automation_tools.tests.mocks.issue import JiraIssue
from automation_tools.tests.mocks.resources import (
    Version, RemoteLink, Status, IssueType, Comment, Resolution, User)


class Jira:
    def __init__(self, **_):
        self._issues = {}

    def issue(self, key):
        try:
            return self._issues[key]
        except KeyError:
            raise jira.exceptions.JIRAError

    def enhanced_search_issues(self, issue_filter, **__):
        issues = []
        match = re.match(
            r"project (?:in \(|\= \")(?P<projects_string>.+?)(?:\)|\")", issue_filter)
        for key, issue in self._issues.items():
            project, _, __ = key.partition("-")
            if project in [p.strip('" ') for p in match.group('projects_string').split(',')]:
                issues.append(issue)
        return issues

    def add_mock_issue(
            self,
            key: str,
            state: str = "Open",
            typ: str = "Internal",
            branches: list[str] = None,
            merge_requests: list[int] = None,
            labels: list[str] = None,
            comments_list: list[str] = None,
            resolution: Optional[str] = None,
            assignee: Optional[str] = DEFAULT_USER["name"]):
        project, _, __ = key.partition("-")
        fixVersions = []
        for branch in branches:
            if branch:
                versions = [
                    v for v in self.project_versions(project)
                    if v.description.startswith(f"<{branch}>")]
            else:
                versions = [Version("Unknown version", "unknown")]
            if versions:
                fixVersions.append(versions[0])

        gitlab_host_url = os.getenv("CI_SERVER_URL", "https://gitlab.example.com")
        remoteLinks = [
            RemoteLink(f"{gitlab_host_url}/dev/someproject/-/merge_requests/{mr_id}")
            for mr_id in (merge_requests or [])]
        comments = [Comment(body=c) for c in (comments_list or [])]
        status = Status(state)
        issuetype = IssueType(typ)

        self._issues[key] = JiraIssue(
            key=key,
            comments=comments,
            fields={
                "fixVersions": fixVersions,
                "remoteLinks": remoteLinks,
                "resolution": Resolution(resolution),
                "status": status,
                "labels": labels if labels is not None else [],
                "issuetype": issuetype,
            },
            assignee=assignee)

    @staticmethod
    def project_versions(project: str):
        return {
            "VMS": [
                Version("5.0", "<vms_5.0> 5.0 Release"),
                Version("5.0_patch", "<vms_5.0_patch> 5.0 Monthly patches"),
                Version("5.1", "<vms_5.1> 5.1 Release"),
                Version("5.1_patch", "<vms_5.1_patch> 5.1 Monthly patches"),
                Version("4.2", "<vms_4.2> 4.2 Release"),
                Version("master", "<master> Major release with a lot of tech debt"),
            ],
            "NXLIB": [
                Version("4.2", "<vms_4.2>"),
                Version("4.2_patch", "<vms_4.2_patch>"),
                Version("5.0", "<vms_5.0>"),
                Version("5.0_patch", "<vms_5.0_patch> 5.0 Monthly patches"),
                Version("5.1", "<vms_5.1>"),
                Version("master", "<master>"),
            ],
            "MOBILE": [
                Version("20.3", "<mobile_20.3>"),
                Version("20.4", "<mobile_20.4>"),
                Version("21.1", "<mobile_21.1>"),
                Version("22.1", "<mobile_22.1>"),
                Version("22.3", "<mobile_22.3>"),
                Version("22.4", "<mobile_22.4>"),
                Version("22.5", "<mobile_22.5>"),
                Version("23.1", "<mobile_23.1>"),
                Version("master", "<master> Ongoing development"),
            ],
            "CB": [
                Version("20.1", "<cloud_backend_20.1>"),
                Version("master", "<master>"),
            ],
            "CLOUD": [
                Version("21.1", ""),
                Version("master", "<master>"),
                Version("master", "<nx:master>"),
                Version("develop", "<cloud_portal:develop>"),
                Version("5.0", "<vms_5.0>"),
                Version("5.0_patch", "<vms_5.0_patch> 5.0 Monthly patches"),
                Version("5.1", "<vms_5.1>"),
            ],
        }.get(project, {})

    @staticmethod
    def transitions(issue: JiraIssue = None):
        if issue.fields.project.key == "NXLIB":
            if issue.fields.status.name == "To Do":
                return [
                    {"name": "start development", "to": {"name": "IN PROGRESS"}},
                    {"name": "DONE", "to": {"name": "DONE"}},
                ]

            if issue.fields.status.name == "IN PROGRESS":
                return [
                    {"name": "To Do", "to": {"name": "To Do"}},
                    {"name": "Review", "to": {"name": "IN REVIEW"}},
                    {"name": "DONE", "to": {"name": "DONE"}},
                ]

            if issue.fields.status.name == "IN REVIEW":
                return [
                    {"name": "To Do", "to": {"name": "To Do"}},
                    {"name": "back to development", "to": {"name": "IN PROGRESS"}},
                    {"name": "DONE", "to": {"name": "DONE"}},
                ]

            if issue.fields.status.name == "DONE":
                return [{"name": "To Do", "to": {"name": "To Do"}}]

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
            if issue.fields.issuetype.name == "Security Issue":
                return [
                    {"name": "Ready for verification", "to": {"name": "Pending Verification"}}]
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

    @staticmethod
    def comments(issue: jira.Issue) -> list[jira.resources.Comment]:
        return issue.fields.comment.comments

    def myself(self):
        return {
            "displayName": DEFAULT_USER["name"],
            "emailAddress": DEFAULT_USER["email"],
            "accountId": DEFAULT_USER["id"],
        }
