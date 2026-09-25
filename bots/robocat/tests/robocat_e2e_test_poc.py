"""Robocat E2E POC: a real MR flow, end to end against the test GitLab instance.

The test only spawns a local Robocat instance as a real process ("poll" mode, the same CLI entry
point as in production) with its own config.yaml and python-gitlab.cfg, and lets it do its usual
work. Everything else is done by hand in the GitLab UI, as an end user would do it:
    1. Open an MR from TEST_SOURCE_BRANCH and assign it to yourself (Robocat acts as the owner of
       TEST_GITLAB_INSTANCE_TOKEN and only handles MRs assigned to that user).
    2. Watch Robocat pick it up, run the pipeline and wait for the approval.
    3. Approve the MR; Robocat checks everything and merges it.
The test passes once Robocat has merged an MR from TEST_SOURCE_BRANCH, or fails after
ROBOCAT_TIMEOUT_S.

Test uses my private tokens for this POC evaluation (see the constants below).

Run from the repository root (-s shows Robocat's log while it runs):
    source open/.venv/bin/activate
    PYTHONPATH=open:open/bots/robocat:bots/robocat \
        pytest -s open/bots/robocat/tests/robocat_e2e_test_poc.py
"""

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Generator
from urllib.parse import urlparse

import gitlab
import pytest
import yaml

### Test uses my private token for this POC evaluation
TEST_PROJECT_JIRA_LOGIN = "dpopov@networkoptix.com"
TEST_PROJECT_JIRA_TOKEN = (
    "ATATT3xFfGF06cewp3Ddog808S1--jZisHb8VnM0Gg7uY1eNDeefsMgYZC5zRbybAG8zDwVqzYtdW7H_yG6rfATtMOs"
    "UXTD_HrVFsQlxWCfYU9anau7RIwGg1pfkIL82cog7fx-5oKMDOs_4VeH_AQvVIDynw7Q7snLz0DsxvHTDlSV0xEe10WU"
    "=B8ABC36C")
TEST_GITLAB_INSTANCE_TOKEN = "glpat-avamfHbhVx27GM-ax1rde286MQp1OmZoCA.01.0y0wdl8yl"

TEST_GITLAB_URL = "https://gitlab.networkoptix.dev"
TEST_GITLAB_PROJECT_PATH = "dpopov/robocat-test"
# Created manually in the test project, with one commit on top of the default branch.
TEST_SOURCE_BRANCH = "robocat-e2e"
TEST_JIRA_URL = "https://networkoptix.atlassian.net"
TEST_JIRA_PROJECT_KEY = "TEST"

# Hosts the test is allowed to touch. Anything else is refused before any API call is made.
ALLOWED_GITLAB_HOSTS: set[str] = {"gitlab.networkoptix.dev"}
ALLOWED_JIRA_PROJECT_KEYS: set[str] = {"TEST"}

REPO_ROOT: Path = Path(__file__).resolve().parents[4]
ROBOCAT_TIMEOUT_S = 30 * 60
MR_CHECK_INTERVAL_S = 10


def is_test_instance() -> None:
    """Check if instances are test ones"""
    gitlab_host: str | None = urlparse(url=TEST_GITLAB_URL).hostname

    assert gitlab_host in ALLOWED_GITLAB_HOSTS, (
        f"Refusing to run against GitLab host {gitlab_host!r}: not a test instance")

    assert TEST_JIRA_PROJECT_KEY in ALLOWED_JIRA_PROJECT_KEYS, (
        f"Refusing to run against Jira project {TEST_JIRA_PROJECT_KEY!r}: not a test project")

@pytest.fixture(scope="module")
def gitlab_client() -> Any:
    is_test_instance()
    client: Any = gitlab.Gitlab(TEST_GITLAB_URL, private_token=TEST_GITLAB_INSTANCE_TOKEN)
    client.auth()
    return client


@pytest.fixture(scope="module")
def project(gitlab_client) -> Any:
    return gitlab_client.projects.get(TEST_GITLAB_PROJECT_PATH)


@pytest.fixture()
def robocat_workdir() -> Generator[Path, Any, None]:
    """Config files for the local Robocat instance, and the place it clones the repo to."""
    gitlab_host: str | None = urlparse(url=TEST_GITLAB_URL).hostname
    with TemporaryDirectory[str](prefix="robocat-e2e-") as tmp_directory:
        workdir: Path = Path(tmp_directory)
        # Robocat reads the [nx_gitlab] section; PYTHON_GITLAB_CFG points python-gitlab here
        # instead of ~/.python-gitlab.cfg, so the real one is left untouched.
        (workdir / "python-gitlab.cfg").write_text(
            "[global]\n"
            "default = nx_gitlab\n"
            "ssl_verify = true\n"
            "timeout = 20\n"
            "\n"
            "[nx_gitlab]\n"
            f"url = {TEST_GITLAB_URL}\n"
            f"private_token = {TEST_GITLAB_INSTANCE_TOKEN}\n"
            "api_version = 4\n")
        (workdir / "config.yaml").write_text(data=yaml.safe_dump({
            "jira": {
                "url": TEST_JIRA_URL,
                "login": TEST_PROJECT_JIRA_LOGIN,
                "password": TEST_PROJECT_JIRA_TOKEN,
                "project_keys": [TEST_JIRA_PROJECT_KEY],
            },
            "repo": {
                # Must not exist yet: Robocat clones the repository there.
                "path": str(workdir / "repo"),
                "url": (
                    f"https://oauth2:{TEST_GITLAB_INSTANCE_TOKEN}@{gitlab_host}/"
                    f"{TEST_GITLAB_PROJECT_PATH}.git"),
            },
            # Must match the stage name in the test project's .gitlab-ci.yml.
            "pipeline": {"autorun_stage": "check"},
            # Only the essential rule: approvals, pipeline and merging.
            "enabled_rules": ["essential"],
        }))
        yield workdir


def start_robocat(workdir: Path, project_id: int) -> subprocess.Popen[bytes]:
    """Spawn a local Robocat instance in "poll" mode; its log goes to the test's output."""
    env: dict[str, str] = dict[str, str](os.environ)

    env["PYTHON_GITLAB_CFG"] = str(workdir / "python-gitlab.cfg")
    env["PYTHONPATH"] = os.pathsep.join(
        str(REPO_ROOT / p) for p in ("open", "open/bots/robocat", "bots/robocat"))

    return subprocess.Popen(
        [
            sys.executable, "-m", "robocat.app",
            "-c", str(workdir / "config.yaml"),
            "-p", str(project_id),
            "--mode", "poll",
            "--log-level", "DEBUG",
        ],
        cwd=REPO_ROOT,
        env=env)


def test_robocat_merges_approved_mr(gitlab_client, project, robocat_workdir) -> None:
    bot_username = gitlab_client.user.username
    started_at = datetime.now(timezone.utc)
    robocat = start_robocat(workdir=robocat_workdir, project_id=project.id)
    try:
        deadline = time.monotonic() + ROBOCAT_TIMEOUT_S
        merged_mr = None
        while merged_mr is None:
            assert robocat.poll() is None, f"Robocat exited with code {robocat.returncode}"
            assert time.monotonic() < deadline, (
                f"No MR from {TEST_SOURCE_BRANCH!r} was merged in {ROBOCAT_TIMEOUT_S} s")
            time.sleep(MR_CHECK_INTERVAL_S)
            merged_mrs = project.mergerequests.list(
                source_branch=TEST_SOURCE_BRANCH,
                state="merged",
                updated_after=started_at.isoformat(),
                get_all=True)
            merged_mr = merged_mrs[0] if merged_mrs else None
    finally:
        robocat.terminate()
        robocat.wait(timeout=30)

    assert merged_mr.merged_by["username"] == bot_username, (
        f"MR !{merged_mr.iid} was merged by {merged_mr.merged_by['username']!r}, not by Robocat")
