## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import http
import json
import queue
import urllib.parse
from typing import Any, cast

import automation_tools.git
import git
import gitlab
import pytest
import requests
from automation_tools.tests.gitlab_constants import BOT_USERNAME
from requests.adapters import BaseAdapter
from robocat.bot import Bot, GitlabEventData, GitlabEventType, GitlabMrEventData
from robocat.project_manager import ProjectManager

from tests.fixtures import bot_config

GITLAB_URL = "https://gitlab.example.com"
PROJECT_PATH = "/projects/1"
MERGE_REQUEST_PATH = f"{PROJECT_PATH}/merge_requests/5"
PROJECT = {  # The fields of the project that Robocat reads.
    "id": 1,
    "name": "nx",
    "path": "nx",
    "path_with_namespace": "dev/nx",
    "namespace": {"full_path": "dev"},
    "ssh_url_to_repo": "git@gitlab.example.com:dev/nx.git",
}
MERGE_REQUEST = {  # An open MR that Robocat looks after.
    "id": 105,
    "iid": 5,
    "project_id": 1,
    "title": "VMS-1: Fix the bug",
    "description": "",
    "state": "opened",
    "sha": "0123456789abcdef0123456789abcdef01234567",
    "author": {"username": "developer", "name": "Developer"},
    "assignees": [{"username": BOT_USERNAME}],
}
TIMEOUT = (requests.exceptions.ReadTimeout, "Read timed out. (read timeout=20)")
BROKEN_ANSWER = (requests.exceptions.ChunkedEncodingError, "Response ended prematurely")


def gitlab_answer(request: requests.PreparedRequest, status: int, body: Any) -> requests.Response:
    """A GitLab HTTP answer: the status and a JSON body."""
    response = requests.Response()
    response.status_code = status
    response.reason = http.HTTPStatus(status).phrase
    response._content = json.dumps(body).encode()
    response.headers["Content-Type"] = "application/json"
    response.url = str(request.url)
    response.request = request
    return response


class GitLabServer(BaseAdapter):
    """A fake GitLab server under a real requests session: python-gitlab and Robocat stay real."""

    def __init__(self, answers: dict[tuple[str, str], Any], failure: tuple[type, str]):
        """Answer these requests; every other request fails as requests fails (slow or broken)."""
        super().__init__()
        self.answers = answers
        self.failure = failure
        self.calls: list[tuple[str, str]] = []
        self.notes: list[str] = []

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        """Answer one request like GitLab, or fail it."""
        method = str(request.method)
        path = urllib.parse.urlsplit(str(request.url)).path.removeprefix("/api/v4")
        self.calls.append((method, path))
        if (method, path) == ("POST", f"{MERGE_REQUEST_PATH}/notes"):
            sent = request.body
            assert isinstance(sent, bytes | str), f"Unexpected note request body: {sent!r}"
            body = json.loads(sent)["body"]
            self.notes.append(body)
            return gitlab_answer(request, 201, {"id": len(self.notes), "body": body})
        if (method, path) in self.answers:
            return gitlab_answer(request, 200, self.answers[(method, path)])
        error_type, message = self.failure
        raise error_type(message)

    def close(self):
        """Nothing to close."""


def answers(merge_request: dict[str, Any] | None = None) -> dict[tuple[str, str], Any]:
    """The project, and the MR with no threads if given; nothing else."""
    result: dict[tuple[str, str], Any] = {("GET", PROJECT_PATH): PROJECT}
    if merge_request is not None:
        result[("GET", MERGE_REQUEST_PATH)] = merge_request
        result[("GET", f"{MERGE_REQUEST_PATH}/discussions")] = []
    return result


@pytest.fixture
def make_bot(monkeypatch, tmp_path, bot_config):
    """A function that makes a Robocat of the real classes on a fake GitLab server."""
    def make(server: GitLabServer) -> Bot:
        """The real Robocat that talks to this server; retries come at once."""
        session = requests.Session()
        session.mount(GITLAB_URL, server)
        raw_gitlab = gitlab.Gitlab(GITLAB_URL, private_token="token", session=session, timeout=20)
        git.Repo.init(tmp_path)  # A real, local git repository: no network.
        repo = automation_tools.git.Repo(tmp_path, url="unused")
        project_manager = ProjectManager(raw_gitlab.projects.get(1), BOT_USERNAME, repo=repo)

        def bot_init(bot: Bot):
            """Only what processing an event needs (the real __init__ reads the GitLab login)."""
            bot._username = BOT_USERNAME
            bot._repo = repo
            bot._project_manager = project_manager
            bot._rules = {}
            bot._polling = False
            bot._mr_queue = queue.PriorityQueue()
            bot.config = bot_config

        monkeypatch.setattr(Bot, "__init__", bot_init)
        monkeypatch.setattr(Bot, "NETWORK_ERROR_RETRY_S", 0)
        return cast(Any, Bot)()  # Like the bot fixture: __init__ takes no arguments here.

    return make


def mr_event() -> GitlabEventData:
    """The event of the changed MR, as GitLab sends it."""
    return GitlabEventData(
        payload=GitlabMrEventData(mr_id=5, mr_state="opened"),
        event_type=GitlabEventType.merge_request)


class TestGitLabTooSlow:
    """GitLab does not answer in time (AUT-283): no comment, the event runs again later."""

    def test_python_gitlab_passes_the_timeout_on(self):
        """The real python-gitlab, set up like Robocat's, raises the Timeout of requests."""
        session = requests.Session()
        session.mount(GITLAB_URL, GitLabServer(answers={}, failure=TIMEOUT))
        raw_gitlab = gitlab.Gitlab(GITLAB_URL, private_token="token", session=session, timeout=20)

        with pytest.raises(requests.exceptions.Timeout):
            raw_gitlab.projects.get(1, lazy=True).mergerequests.get(5)

    def test_five_retries_and_no_comment(self, make_bot):
        """The MR cannot be read: Robocat tries again 5 times, then stops; it posts nothing."""
        server = GitLabServer(answers(), failure=TIMEOUT)
        bot = make_bot(server)

        event = mr_event()
        for retry_number in range(1, Bot.NETWORK_ERROR_RETRIES + 1):
            bot.process_event(event)
            event = bot._mr_queue.get(timeout=5)
            assert event.network_retries == retry_number
        bot.process_event(event)  # The 5th retry fails too.

        with pytest.raises(queue.Empty):
            bot._mr_queue.get(timeout=0.5)
        assert server.calls.count(("GET", MERGE_REQUEST_PATH)) == 1 + Bot.NETWORK_ERROR_RETRIES
        assert server.notes == []

    def test_retries_stop_when_gitlab_answers(self, make_bot):
        """GitLab answers the retry: Robocat handles the event and does not try again."""
        server = GitLabServer(answers(), failure=TIMEOUT)
        bot = make_bot(server)
        bot.process_event(mr_event())

        server.answers = answers({**MERGE_REQUEST, "assignees": []})  # Not Robocat's: done.
        bot.process_event(bot._mr_queue.get(timeout=5))

        assert ("GET", MERGE_REQUEST_PATH) in server.calls
        with pytest.raises(queue.Empty):
            bot._mr_queue.get(timeout=0.5)
        assert server.notes == []

    def test_broken_answer_keeps_its_comment(self, make_bot):
        """A broken answer is not a slow one: the MR still gets the comment (AUT-282)."""
        server = GitLabServer(answers(MERGE_REQUEST), failure=BROKEN_ANSWER)
        bot = make_bot(server)

        bot.process_event(mr_event())

        assert len(server.notes) == 1
        assert "Robocat failed to process this Merge Request" in server.notes[0]
        assert bot._mr_queue.empty()

    def test_poll_mode_logs_a_timeout_as_connection_error(self, make_bot, caplog):
        """Poll mode logs a timeout like a connection error, not as an unknown error."""
        server = GitLabServer(answers(MERGE_REQUEST), failure=TIMEOUT)
        bot = make_bot(server)

        bot.run_poller(mr_id=5)

        assert "Connection error: Read timed out" in caplog.text
        assert "Unknown error" not in caplog.text
        assert server.notes == []
