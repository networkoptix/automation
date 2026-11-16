## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from typing import Any, cast

import pytest
from automation_tools.jira import JiraAccessor
from automation_tools.tests.gitlab_constants import BOT_USERNAME
from robocat.comments import Comment, Emoji
from robocat.project_manager import ProjectManager
from robocat.rule.essential_rule import EssentialRule

from tests import runner_failure_test
from tests.fixtures import bot_config
from tests.merge_request_test import (
    MERGE_REQUEST_PATH,
    FakeGitLabServer,
    merge_request_manager,
    posted_comments,
)

SYNCING = {"approved": False, "approvals_left": 0, "approvals_required": 1}  # GitLab 19.4: ~15 s.
NOT_APPROVED = {"approved": False, "approvals_left": 1, "approvals_required": 1}
MERGE_REQUEST = {  # The open MR of the AUT-289 tests, with a passed pipeline.
    **runner_failure_test.MERGE_REQUEST,
    "detailed_merge_status": "approvals_syncing",
}
PIPELINE = {**runner_failure_test.PIPELINE, "status": "success"}


def gitlab_with_approvals(approvals: dict[str, Any]) -> FakeGitLabServer:
    """GitLab with the MR that Robocat watches; its approvals answer as given."""
    server = FakeGitLabServer({
        ("GET", f"{MERGE_REQUEST_PATH}/pipelines"): (200, [PIPELINE]),
        ("GET", runner_failure_test.PIPELINE_PATH): (200, PIPELINE),
        ("GET", f"{MERGE_REQUEST_PATH}/approvals"): (200, approvals),
    })
    server.award_emoji = [{"id": 7, "name": Emoji.WATCHING, "user": {"username": BOT_USERNAME}}]
    return server


@pytest.fixture
def essential_rule(bot_config) -> EssentialRule:
    """The real essential rule; it uses neither the project manager nor Jira."""
    return EssentialRule(bot_config, cast(ProjectManager, None), cast(JiraAccessor, None))


class TestApprovalsWhileGitLabSyncs:
    """After a push or a rebase GitLab answers approved: False with 0 left (dev/automation!573)."""

    def test_no_comment_while_gitlab_syncs(self, essential_rule):
        """No "unknown number more required" comment and no wait emoji: the next event checks."""
        server = gitlab_with_approvals(SYNCING)

        result = essential_rule.execute(merge_request_manager(server, MERGE_REQUEST))

        assert result == EssentialRule.ExecutionResult.not_approved
        assert posted_comments(server) == []
        assert [emoji["name"] for emoji in server.award_emoji] == [Emoji.WATCHING]

    def test_missing_approval_is_reported(self, essential_rule):
        """When GitLab has synced, a missing approval gets its number and the wait emoji."""
        server = gitlab_with_approvals(NOT_APPROVED)

        result = essential_rule.execute(merge_request_manager(server, MERGE_REQUEST))

        assert result == EssentialRule.ExecutionResult.not_approved
        assert posted_comments(server) == [Comment.WaitingForApproval]
        assert "**1 more**" in server.notes[0]["body"]
        assert Emoji.WAIT in [emoji["name"] for emoji in server.award_emoji]
