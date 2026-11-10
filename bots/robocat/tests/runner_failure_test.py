## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import urllib.parse
from typing import Any, cast

import automation_tools.git
import git
import gitlab
import pytest
import requests
from automation_tools.jira import JiraAccessor
from automation_tools.tests.gitlab_constants import BOT_USERNAME
from robocat.gitlab_events import GitlabJobEventData
from robocat.pipeline import Job
from robocat.project_manager import ProjectManager
from robocat.rule.job_status_check_rule import JobStatusCheckRule

from tests import network_error_test
from tests.fixtures import bot_config
from tests.merge_request_test import (
    GITLAB_URL,
    MERGE_REQUEST_PATH,
    FakeGitLabServer,
    merge_request_manager,
    mock_gitlab_response,
    posted_comments,
)

PROJECT_PATH = network_error_test.PROJECT_PATH
PIPELINE_PATH = f"{PROJECT_PATH}/pipelines/900"
NEW_OPEN_SOURCE_FILES_CHECK = "new-open-source-files:check"
MERGE_REQUEST = {  # The open MR of the network error tests, with the fields the rule reads.
    **network_error_test.MERGE_REQUEST,
    "web_url": f"{GITLAB_URL}/dev/nx/-/merge_requests/5",
    "has_conflicts": False,
    "work_in_progress": False,
    "blocking_discussions_resolved": True,
    "source_branch": "vaapi",
    "target_branch": "master",
    "source_project_id": 1,
    "target_project_id": 1,
    "squash": False,
}
SHA = MERGE_REQUEST["sha"]
PIPELINE = {  # The MR pipeline, as GitLab lists it (nx!41534 pipeline 505671).
    "id": 900,
    "project_id": 1,
    "status": "failed",
    "sha": SHA,
    "ref": "refs/merge-requests/5/head",
    "created_at": "2026-11-09T13:48:35.139+03:00",
}
UNPLAYABLE_JOB = (400, {"message": "400 Bad request - Unplayable Job"})  # GitLab: a failed job.


def check_jobs(failure_reason: str) -> list[dict[str, Any]]:
    """The check jobs of the pipeline: the open-source checks failed for this reason."""
    return [{
        "id": job_id,
        "name": name,
        "stage": "check",
        "status": "failed",
        "failure_reason": failure_reason,  # GitLab sends the field for failed jobs only.
        "allow_failure": allow_failure,
        "pipeline": {"id": PIPELINE["id"], "status": PIPELINE["status"]},
    } for job_id, name, allow_failure in [
        (11236142, "open-source:check", False),
        (11236143, NEW_OPEN_SOURCE_FILES_CHECK, True),
    ]]


class CheckJobsServer(FakeGitLabServer):
    """The fake GitLab of the MR tests, with an MR pipeline whose check jobs failed."""

    def __init__(self, failure_reason: str):
        """GitLab with one MR whose last pipeline has check jobs that failed for this reason."""
        self.jobs = check_jobs(failure_reason)
        super().__init__({
            ("GET", PROJECT_PATH): (200, network_error_test.PROJECT),
            ("GET", f"{MERGE_REQUEST_PATH}/pipelines"): (200, [PIPELINE]),
            ("GET", PIPELINE_PATH): (200, PIPELINE),
            **{("POST", f"{PROJECT_PATH}/jobs/{job['id']}/play"): UNPLAYABLE_JOB
               for job in self.jobs},
        })
        self.award_emoji = []  # No merge has started.

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        """Answer the job pages; the fake of the MR tests answers the rest."""
        url = urllib.parse.urlsplit(str(request.url))
        path = url.path.removeprefix("/api/v4")
        if (request.method, path) == ("GET", f"{PIPELINE_PATH}/jobs"):
            first_page = urllib.parse.parse_qs(url.query).get("page") == ["1"]
            return mock_gitlab_response(request, 200, self.jobs if first_page else [])
        return super().send(request, stream, timeout, verify, cert, proxies)


def job_event(status: str, failure_reason: str | None) -> GitlabJobEventData:
    """The Job webhook data of a check job, as Robocat reads it (nx!41534, job 11236458)."""
    return GitlabJobEventData(
        job_id="11236458", pipeline_id=str(PIPELINE["id"]), project_id="1", name="rdep:check",
        status=status, stage="check", allow_failure=False, failure_reason=failure_reason)


class TestJobWithoutResult:
    """A check job that the runner broke has no check result (AUT-289, nx!41534)."""

    @pytest.mark.parametrize(("status", "failure_reason", "without_result"), [
        ("failed", "runner_system_failure", True),  # nx!41534, 15 times in 30 days.
        ("failed", "no_updates_running", True),  # 7 times in 30 days.
        ("failed", "script_failure", False),  # The check ran and found a problem.
        ("failed", None, False),  # An older GitLab sends no reason.
        ("success", None, False),
    ])
    def test_failed_without_result(self, status, failure_reason, without_result):
        """Only a failure reason other than a failed script means "no check result"."""
        assert Job(job_event(status, failure_reason)).failed_without_result is without_result


@pytest.fixture
def job_status_rule(bot_config, tmp_path) -> JobStatusCheckRule:
    """The real job status rule, with the open-source keepers of the Robocat config template."""
    session = requests.Session()
    session.mount(GITLAB_URL, CheckJobsServer("script_failure"))
    raw_gitlab = gitlab.Gitlab(GITLAB_URL, private_token="token", session=session)
    git.Repo.init(tmp_path)  # A real, local git repository: no clone, no network.
    repo = automation_tools.git.Repo(tmp_path, url="unused")
    project_manager = ProjectManager(raw_gitlab.projects.get(1), BOT_USERNAME, repo=repo)
    return JobStatusCheckRule(bot_config, project_manager, cast(JiraAccessor, None))  # No Jira.


class TestCheckJobBrokenByRunner:
    """The runner breaks the check jobs (AUT-289, nx!41534): no check result, no keepers."""

    def test_runner_failure_does_not_call_the_keepers(self, job_status_rule):
        """Robocat waits for the job to run again: no comment, no keepers, no extra approval."""
        server = CheckJobsServer("runner_system_failure")

        result = job_status_rule.execute(merge_request_manager(server, MERGE_REQUEST))

        assert result == JobStatusCheckRule.ExecutionResult.in_progress
        assert posted_comments(server) == []
        assert ("PUT", MERGE_REQUEST_PATH) not in server.calls  # The keepers are not assigned.
        assert ("POST", f"{MERGE_REQUEST_PATH}/approvals") not in server.calls
