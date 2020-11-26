import pytest

from tests.common_constants import (
    BAD_OPENSOURCE_COMMIT,
    FILE_COMMITS_SHA,
    DEFAULT_OPEN_SOURCE_APPROVER)
from tests.fixtures import *


class TestBot:
    @pytest.mark.parametrize("mr_state", [
        # Return to development on the second handle iteration if essential rule is ok but
        # open source rule check is failed and merge request is not approved by an eligible user.
        {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [BAD_OPENSOURCE_COMMIT],
            "pipelines_list": [(BAD_OPENSOURCE_COMMIT["sha"], "success")]
        },
        {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_readme"],
                "message": "msg",
                "diffs": [],
                "files": ["open/readme.md"]
            }],
            "pipelines_list": [(FILE_COMMITS_SHA["good_readme"], "success")]
        },
    ])
    def test_autoreturn_to_develop(self, bot, mr, mr_manager):
        bot.handle(mr_manager)
        assert not mr.merged
        assert not mr.blocking_discussions_resolved

        bot.handle(mr_manager)
        assert not mr.merged
        assert mr.work_in_progress

        # Nothing changes after the third handler run.
        comments_before = mr.comments()
        pipelines_before = mr.pipelines()
        emojis_before = [e.name for e in mr.awardemojis.list()]

        bot.handle(mr_manager)
        assert not mr.merged
        assert mr.work_in_progress

        comments_after = mr.comments()
        pipelines_after = mr.pipelines()
        emojis_after = [e.name for e in mr.awardemojis.list()]
        assert comments_before == comments_after
        assert pipelines_before == pipelines_after
        assert emojis_before == emojis_after

    @pytest.mark.parametrize("mr_state", [
        {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_readme"],
                "message": "msg",
                "diffs": [],
                "files": ["open/readme.md"]
            }],
            "approvers_list": [DEFAULT_OPEN_SOURCE_APPROVER],
            "pipelines_list": [(FILE_COMMITS_SHA["good_readme"], "success")]
        },
    ])
    def test_merge(self, bot, mr, mr_manager):
        bot.handle(mr_manager)
        assert mr.merged
        assert not mr.rebased

    @pytest.mark.parametrize("mr_state", [
        {
            "needs_rebase": True,
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_readme"],
                "message": "msg",
                "diffs": [],
                "files": ["open/readme.md"]
            }],
            "approvers_list": [DEFAULT_OPEN_SOURCE_APPROVER],
            "pipelines_list": [(FILE_COMMITS_SHA["good_readme"], "success")]
        },
    ])
    def test_rebase(self, bot, mr, mr_manager):
        bot.handle(mr_manager)
        assert not mr.merged
        assert mr.rebased
