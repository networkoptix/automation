from typing import List, Optional

from automation_tools.tests.mocks.issue import JiraIssue
from automation_tools.tests.mocks.resources import (
    Version, RemoteLink, Status, IssueType, Comment, Resolution)


class Jira:
    def __init__(self, **_):
        self._issues = {}

    def issue(self, key):
        return self._issues[key]

    def search_issues(self, *_, **__):
        return self._issues.values()

    def add_mock_issue(
            self, key: str, state: str = "Open", typ: str = "Internal",
            branches: List[str] = None,
            merge_requests: List[int] = None,
            labels: List[str] = None,
            comments_list: List[str] = None,
            resolution: Optional[str] = None):
        fixVersions = [
            next(v for v in self.project_versions() if v.description.startswith(f"<{b}>"))
            for b in branches]
        remoteLinks = [
            RemoteLink(f"https://gitlab.lan.hdw.mx/-/dev/nx/merge_requests/{mr_id}")
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
    def project_versions(_=None):
        return [
            Version("4.0", "<vms_4.0_release>"),
            Version("4.0_patch", "<vms_4.0> 4.0 Monthly patches"),
            Version("4.1", "<vms_4.1_release> Minor release with Health Monitoring"),
            Version("4.1_patch", "<vms_4.1> 4.1 Monthly patches"),
            Version("4.2", "<vms_4.2> Major release with plugins"),
            Version("4.2_patch", "<vms_4.2_patch> 4.2 Monthly patches"),
            Version("master", "<master> Major release with a lot of tech debt")
        ]

    @staticmethod
    def transitions(issue: JiraIssue = None):
        if issue.fields.status.name == "Closed":
            return [
                {"name": "Reopen", "to": {"name": "Open"}},
                {"name": "Update Resolution", "to": {"name": "Closed"}}]

        if issue.fields.status.name == "In Review":
            if issue.fields.issuetype.name == "Internal":
                return [
                    {"name": "Back to development", "to": {"name": "In progress"}},
                    {"name": "Close", "to": {"name": "Closed"}}]
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
