## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from unittest.mock import MagicMock

import gitlab
import pytest
from automation_tools.tests.gitlab_constants import BOT_USERNAME
from gitlab.v4.objects import ProjectMergeRequest
from robocat.merge_request import MergeRequest

MERGE_REQUEST_DATA = {  # The fields of the merge request GET that the tests read.
    "iid": 5,
    "title": "VMS-1: Fix the bug",
    "author": {"username": "developer", "name": "Developer"},
    "sha": "0123456789abcdef0123456789abcdef01234567",
}
APPROVAL_ANSWER = {  # GitLab answers approve and unapprove with the approval state only.
    "iid": 5,
    "title": "VMS-1: Fix the bug",
    "approvals_left": 0,
    "approved_by": [],
}


class TestApprovalKeepsMergeRequestData:
    """python-gitlab replaces the MR data with the approval answer: Robocat must keep its data."""

    @pytest.fixture
    def merge_request(self, monkeypatch) -> MergeRequest:
        """An MR of the real python-gitlab classes; only the GitLab server is fake."""
        raw_gitlab = gitlab.Gitlab("https://gitlab.example.com", private_token="token")
        monkeypatch.setattr(raw_gitlab, "http_post", lambda *_, **__: dict(APPROVAL_ANSWER))
        monkeypatch.setattr(  # Robocat must not need to read the MR again.
            raw_gitlab, "http_get", MagicMock(side_effect=AssertionError("Unexpected GET")))
        monkeypatch.setattr(raw_gitlab, "http_list", lambda *_, **__: [])  # No discussions.
        manager = raw_gitlab.projects.get(1, lazy=True).mergerequests
        return MergeRequest(ProjectMergeRequest(manager, dict(MERGE_REQUEST_DATA)), BOT_USERNAME)

    @pytest.mark.parametrize("action", ["ensure_approve", "ensure_unapprove"])
    def test_merge_request_data_stays(self, merge_request, action):
        """After a successful approve or unapprove, the MR author and commit are still known."""
        assert getattr(merge_request, action)() is True

        assert merge_request.author.username == "developer"
        assert merge_request.sha == MERGE_REQUEST_DATA["sha"]
