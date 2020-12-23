import pytest

from robocat.award_emoji_manager import AwardEmojiManager
from tests.common_constants import (
    BAD_OPENSOURCE_COMMIT,
    FILE_COMMITS_SHA,
    DEFAULT_OPEN_SOURCE_APPROVER)
from tests.fixtures import *


class TestBot:
    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Return to development on the second handle iteration if essential rule is ok but
        # open source rule check is failed and merge request is not approved by an eligible user.
        ([{"key": "VMS-666", "branches": ["master", "vms_4.1"]}], {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [BAD_OPENSOURCE_COMMIT],
            "pipelines_list": [(BAD_OPENSOURCE_COMMIT["sha"], "success")]
        }),
        ([{"key": "VMS-666", "branches": ["master", "vms_4.1"]}], {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": "msg",
                "diffs": [],
                "files": ["open/dontreadme.md"]
            }],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")]
        }),
    ])
    def test_autoreturn_to_develop(self, bot, mr, mr_manager):
        bot.handle(mr_manager)
        assert not mr.state == "merged"
        assert not mr.blocking_discussions_resolved

        bot.handle(mr_manager)
        assert not mr.state == "merged"
        assert mr.work_in_progress

        # Nothing changes after the third handler run.
        comments_before = mr.comments()
        pipelines_before = mr.pipelines()
        emojis_before = [e.name for e in mr.awardemojis.list()]

        bot.handle(mr_manager)
        assert not mr.state == "merged"
        assert mr.work_in_progress

        comments_after = mr.comments()
        pipelines_after = mr.pipelines()
        emojis_after = [e.name for e in mr.awardemojis.list()]
        assert comments_before == comments_after
        assert pipelines_before == pipelines_after
        assert emojis_before == emojis_after

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        ([{"key": "VMS-666", "branches": ["master", "vms_4.1"]}], {
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": "msg",
                "diffs": [],
                "files": ["open/dontreadme.md"]
            }],
            "approvers_list": [DEFAULT_OPEN_SOURCE_APPROVER],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")]
        }),
    ])
    def test_merge(self, bot, mr, mr_manager):
        bot.handle(mr_manager)
        assert mr.state == "merged"
        assert not mr.rebased

        emojis = mr.awardemojis.list()
        assert not any(
            e for e in emojis if e.name == AwardEmojiManager.UNFINISHED_PROCESSING_EMOJI), (
            'Hasn\'t unfinished processing flag.')

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        ([{"key": "VMS-666", "branches": ["master", "vms_4.1"]}], {
            "needs_rebase": True,
            "blocking_discussions_resolved": True,
            "needed_approvers_number": 0,
            "commits_list": [{
                "sha": FILE_COMMITS_SHA["good_dontreadme"],
                "message": "msg",
                "diffs": [],
                "files": ["open/dontreadme.md"]
            }],
            "approvers_list": [DEFAULT_OPEN_SOURCE_APPROVER],
            "pipelines_list": [(FILE_COMMITS_SHA["good_dontreadme"], "success")]
        }),
    ])
    def test_rebase(self, bot, mr, mr_manager):
        bot.handle(mr_manager)
        assert not mr.state == "merged"
        assert mr.rebased

        emojis = mr.awardemojis.list()
        assert not any(
            e for e in emojis if e.name == AwardEmojiManager.UNFINISHED_PROCESSING_EMOJI), (
            'Hasn\'t unfinished processing flag.')
