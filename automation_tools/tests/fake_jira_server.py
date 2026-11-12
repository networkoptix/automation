## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import copy
import http
import json
import re
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests
from jira import JIRA
from requests.adapters import BaseAdapter

JIRA_URL = "https://jira.example.com"
NOT_FOUND = {  # Jira's answer for a key that it does not have.
    "errorMessages": ["Issue does not exist or you do not have permission to see it."],
    "errors": {},
}


@dataclass(frozen=True)
class Transition:
    """One transition as Jira lists it: its id, its name and the status it leads to."""

    identifier: str  # Jira's REST API sends and expects the id as a string.
    name: str
    status: str

    def as_json(self) -> dict[str, Any]:
        """The transition as Jira's REST API lists it."""
        return {"id": self.identifier, "name": self.name, "to": {"name": self.status}}


NXLIB_ISSUE = {  # NXLIB writes its status names in its own case: "OPEN", "In Progress".
    "id": "857938",
    "key": "NXLIB-434",
    "self": f"{JIRA_URL}/rest/api/2/issue/NXLIB-434",
    "fields": {
        "status": {"name": "OPEN"},
        "project": {"key": "NXLIB"},
        "issuetype": {"name": "Internal"},
        "labels": [],
        "fixVersions": [],
    },
}
NXLIB_START_DEVELOPMENT = Transition("31", "start development", "In Progress")
NXLIB_TRANSITIONS = {  # The transitions of NXLIB-434 as Jira answered them.
    "NXLIB": {
        "OPEN": [
            Transition("11", "OPEN", "OPEN"),
            Transition("21", "Closed (1)", "Closed"),
            NXLIB_START_DEVELOPMENT,
        ],
    },
}


def jira_answer(request: requests.PreparedRequest, status: int, body: Any) -> requests.Response:
    """A Jira HTTP answer: the status and a JSON body (no body for None)."""
    response = requests.Response()
    response.status_code = status
    response.reason = http.HTTPStatus(status).phrase
    response._content = b"" if body is None else json.dumps(body).encode()
    response.headers["Content-Type"] = "application/json"
    response.url = str(request.url)
    response.request = request
    return response


class FakeJiraServer(BaseAdapter):
    """A fake Jira server whose Issues change their status like Jira; the jira library is real."""

    def __init__(
            self,
            issues: list[dict[str, Any]],
            transitions: dict[str, dict[str, list[Transition]]],
            project_versions: dict[str, list[dict[str, Any]]] | None = None):
        """Keep the Issues, the transitions per project and status, and the project versions."""
        super().__init__()
        self.issues = {issue["key"]: copy.deepcopy(issue) for issue in issues}
        self._transitions = transitions
        self._project_versions = project_versions or {}
        self.requests: list[tuple[str, str]] = []
        self.transitions_made: list[Transition] = []
        self.comments: list[tuple[str, str]] = []  # The Issue key and text of each new comment.
        self.failure: Exception | None = None  # Not None: every request raises it (no network).

    def status(self, key: str) -> str:
        """The status of an Issue now."""
        return self.issues[key]["fields"]["status"]["name"]

    def issue_requests(self) -> list[tuple[str, str]]:
        """The requests about Issues (not about project versions)."""
        return [request for request in self.requests if "/issue/" in request[1]]

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        """Answer one request like Jira; fail the test on a request it does not expect."""
        method = str(request.method)
        path = urllib.parse.urlsplit(str(request.url)).path
        self.requests.append((method, path))
        if self.failure is not None:
            raise self.failure
        if method == "GET" and (versions := re.fullmatch(r"/rest/api/2/project/(\w+)/versions",
                                                         path)):
            return jira_answer(request, 200, self._project_versions.get(versions.group(1), []))
        found = re.fullmatch(r"/rest/api/2/issue/([A-Z]+-\d+)(/transitions|/comment)?", path)
        if found is None:
            raise AssertionError(f"Unexpected Jira request: {method} {path}")
        issue = self.issues.get(found.group(1))
        if issue is None:
            return jira_answer(request, 404, NOT_FOUND)
        offered = {item.identifier: item for item in self._transitions.get(
            issue["fields"]["project"]["key"], {}).get(self.status(issue["key"]), [])}
        if method == "GET" and not found.group(2):
            return jira_answer(request, 200, issue)
        if (method, found.group(2)) == ("POST", "/comment"):
            sent = request.body
            assert isinstance(sent, bytes | str), f"Unexpected comment request body: {sent!r}"
            self.comments.append((issue["key"], json.loads(sent)["body"]))
            return jira_answer(request, 201, {"id": str(len(self.comments)),
                                              "body": self.comments[-1][1]})
        if (method, found.group(2)) == ("GET", "/transitions"):
            return jira_answer(
                request, 200, {"transitions": [item.as_json() for item in offered.values()]})
        if (method, found.group(2)) == ("POST", "/transitions"):
            sent = request.body
            assert isinstance(sent, bytes | str), f"Unexpected transition request body: {sent!r}"
            transition_id = json.loads(sent)["transition"]["id"]
            assert transition_id in offered, f"Jira has no transition {transition_id} now"
            issue["fields"]["status"]["name"] = offered[transition_id].status
            self.transitions_made.append(offered[transition_id])
            return jira_answer(request, 204, None)
        raise AssertionError(f"Unexpected Jira request: {method} {path}")

    def close(self):
        """Nothing to close."""


def jira_client_on(server: FakeJiraServer) -> Callable[..., JIRA]:
    """A maker of real jira clients that talk to the fake server, for monkeypatching jira.JIRA."""
    def client_on_fake_server(**options) -> JIRA:
        """The real jira client without the server info request."""
        client = JIRA(**options, get_server_info=False)
        assert client._session is not None  # The client makes its session at once.
        client._session.mount(JIRA_URL, server)
        return client

    return client_on_fake_server
