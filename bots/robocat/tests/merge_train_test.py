## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from unittest.mock import MagicMock

import pytest

from automation_tools.tests.gitlab_constants import (
    DEFAULT_JIRA_ISSUE_KEY,
    GOOD_README_COMMIT_NEW_FILE,
    OPEN_SOURCE_APPROVER_COMMON,
)
from automation_tools.tests.fixtures import repo_versions  # noqa: F401
from tests.fixtures import *  # noqa: F401,F403


_MERGEABLE_MR_STATE = {
    "title": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[0],
    "description": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[1],
    "blocking_discussions_resolved": True,
    "needed_approvers_number": 0,
    "commits_list": [GOOD_README_COMMIT_NEW_FILE],
    "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
    "pipelines_list": [(
        GOOD_README_COMMIT_NEW_FILE["sha"],
        "success",
        [("open-source:check", "success"), ("new-open-source-files:check", "success")],
    )],
    "squash": False,
}

_MERGEABLE_JIRA_ISSUES = [{
    "key": DEFAULT_JIRA_ISSUE_KEY,
    "branches": ["master"],
    "state": "In Review",
    "type": "Task",
}]


def _has_jira_merged_comment(jira, issue_key) -> bool:
    issue = jira._jira.issue(issue_key)
    return any(
        "has been merged to branch" in c.body for c in issue.fields.comment.comments)


class TestMergeTrain:
    @pytest.mark.parametrize("jira_issues", [_MERGEABLE_JIRA_ISSUES])
    @pytest.mark.parametrize("mr_state", [_MERGEABLE_MR_STATE])
    def test_merge_completes_via_train_posts_jira_comment_on_next_event(
            self, bot, mr, mr_manager, project, jira, jira_issues):
        project.attributes["merge_trains_enabled"] = True
        project.manager.gitlab.http_post = MagicMock(return_value=None)

        bot.handle(mr_manager)
        assert not _has_jira_merged_comment(jira, jira_issues[0]["key"])

        # Simulate the train completing the merge externally. Clear the
        # "unfinished post-merge" flag so the next handle() reaches the merge step.
        mr.state = "merged"
        mr_manager.update_unfinished_post_merging_flag(False)

        bot.handle(mr_manager)

        assert _has_jira_merged_comment(jira, jira_issues[0]["key"]), (
            "Jira 'merged to branch' comment must be posted once the train completes the merge")
