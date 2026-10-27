## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from unittest.mock import MagicMock

import pytest
from automation_tools.tests.gitlab_constants import (
    BOT_USERNAME,
    GOOD_README_COMMIT_NEW_FILE,
    OPEN_SOURCE_APPROVER_COMMON,
)
from gitlab.exceptions import GitlabError, GitlabHttpError, GitlabMRClosedError
from robocat.comments import Comment, Emoji
from robocat.merge_request import MergeRequest, MergeResult
from robocat.merge_request_manager import MergeRequestManager

from tests.fixtures import mr, mr_state, project

_BASE_MR_STATE = {
    "title": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[0],
    "description": GOOD_README_COMMIT_NEW_FILE["message"].partition("\n\n")[1],
    "blocking_discussions_resolved": True,
    "needed_approvers_number": 0,
    "commits_list": [GOOD_README_COMMIT_NEW_FILE],
    "approvers_list": [OPEN_SOURCE_APPROVER_COMMON],
    "pipelines_list": [(GOOD_README_COMMIT_NEW_FILE["sha"], "success")],
}


class TestMergeRequestMerge:
    @pytest.fixture
    def merge_request(self, mr):
        return MergeRequest(mr, BOT_USERNAME)

    @pytest.mark.parametrize("mr_state", [{**_BASE_MR_STATE, "squash": False}])
    def test_direct_merge_returns_merged(self, merge_request, mr):
        result = merge_request.merge()

        assert result == MergeResult.MERGED
        assert mr.state == "merged"

    @pytest.mark.parametrize("mr_state", [{**_BASE_MR_STATE, "squash": True}])
    def test_direct_merge_with_squash_passes_message(
            self, merge_request, mr, monkeypatch):
        captured = {}

        def fake_merge(squash_commit_message=None, **_):
            captured["squash_commit_message"] = squash_commit_message
            mr.state = "merged"

        monkeypatch.setattr(mr, "merge", fake_merge)

        result = merge_request.merge()

        assert result == MergeResult.MERGED
        expected = f"{mr.title}\n\n{mr.description}"
        assert captured["squash_commit_message"] == expected

    @pytest.mark.parametrize("mr_state", [_BASE_MR_STATE])
    def test_merge_train_http_200_returns_added_to_train(
            self, merge_request, mr, project):
        project.attributes["merge_trains_enabled"] = True
        http_post = MagicMock(return_value=None)
        project.manager.gitlab.http_post = http_post

        result = merge_request.merge()

        assert result == MergeResult.ADDED_TO_MERGE_TRAIN
        assert mr.state == "opened", "MR state must not change when only queued"
        http_post.assert_called_once_with(
            f"/projects/{project.id}/merge_trains/merge_requests/{mr.iid}",
            post_data={"auto_merge": False})

    @pytest.mark.parametrize("mr_state", [_BASE_MR_STATE])
    def test_merge_train_http_409_returns_added_to_train(
            self, merge_request, mr, project):
        project.attributes["merge_trains_enabled"] = True
        project.manager.gitlab.http_post = MagicMock(side_effect=GitlabHttpError(
            "409: Merge request is already set to Auto-Merge", response_code=409))

        result = merge_request.merge()

        assert result == MergeResult.ADDED_TO_MERGE_TRAIN
        assert mr.state == "opened"

    @pytest.mark.parametrize("mr_state", [_BASE_MR_STATE])
    def test_merge_train_non_409_error_propagates(self, merge_request, mr, project):
        project.attributes["merge_trains_enabled"] = True
        project.manager.gitlab.http_post = MagicMock(side_effect=GitlabHttpError(
            "400: Failed to merge", response_code=400))

        with pytest.raises(GitlabHttpError) as exc_info:
            merge_request.merge()

        assert exc_info.value.response_code == 400
        assert mr.state == "opened"


class TestMergeRequestManagerMerge:
    @pytest.fixture
    def mock_mr(self):
        mr = MagicMock(spec=MergeRequest)
        mr.is_merged = False
        mr.id = 42
        mr.title = "Test MR"
        mr.target_branch = "master"
        mr.sha = "deadbeef"
        mr.raw_gitlab_object = MagicMock()
        return mr

    @pytest.fixture
    def manager(self, mock_mr):
        return MergeRequestManager(mock_mr)

    def test_already_merged_short_circuits_without_calling_merge(
            self, manager, mock_mr):
        mock_mr.is_merged = True

        result = manager.merge()

        assert result is True
        mock_mr.merge.assert_not_called()
        mock_mr.create_note.assert_not_called()

    def test_merged_result_posts_mr_merged_comment_and_returns_true(
            self, manager, mock_mr):
        mock_mr.merge.return_value = MergeResult.MERGED

        result = manager.merge()

        assert result is True
        mock_mr.create_note.assert_called_once()
        body = mock_mr.create_note.call_args.args[0]
        assert Comment.MrMerged.name in body
        assert mock_mr.target_branch in body

    def test_added_to_train_result_skips_comment_and_returns_false(
            self, manager, mock_mr):
        mock_mr.merge.return_value = MergeResult.ADDED_TO_MERGE_TRAIN

        result = manager.merge()

        assert result is False
        mock_mr.create_note.assert_not_called()

    def test_gitlab_mr_closed_error_triggers_rebase_and_returns_false(
            self, manager, mock_mr):
        mock_mr.merge.side_effect = GitlabMRClosedError("closed", response_code=405)

        result = manager.merge()

        assert result is False
        mock_mr.rebase.assert_called_once()
        mock_mr.create_note.assert_not_called()

    def test_comment_post_failure_is_swallowed_and_true_still_returned(
            self, manager, mock_mr):
        mock_mr.merge.return_value = MergeResult.MERGED
        mock_mr.create_note.side_effect = GitlabError("comment post failed")

        result = manager.merge()

        assert result is True, (
            "Merge succeeded; failure to add the 'MR merged' comment must not mask success")

    def test_gitlab_rejection_posts_comment_and_returns_false(self, manager, mock_mr):
        """A 400 answer to the merge is explained in a comment, not raised."""
        mock_mr.award_emoji = MagicMock()
        mock_mr.merge.side_effect = GitlabHttpError(
            "400 Bad request - Failed to merge", response_code=400)

        result = manager.merge()

        assert result is False
        body = mock_mr.create_note.call_args.args[0]
        assert f"Message Id: {Comment.MergeRejected.name}" in body
        assert "400 Bad request - Failed to merge" in body
        mock_mr.award_emoji.delete.assert_called_once_with(  # Nothing was merged.
            Emoji.UNFINISHED_POST_MERGING, own=False)

    def test_gitlab_rejection_is_explained_once_per_commit(self, manager, mock_mr):
        """A second refusal for the same commit posts no second comment."""
        mock_mr.award_emoji = MagicMock()
        mock_mr.merge.side_effect = GitlabHttpError(
            "400 Bad request - Failed to merge", response_code=400)
        manager.merge()
        mock_mr.notes_data.return_value = [{
            "id": 1,
            "author": {"username": BOT_USERNAME},
            "created_at": "2026-10-26T12:00:00Z",
            "body": mock_mr.create_note.call_args.args[0],
        }]

        assert manager.merge() is False
        assert mock_mr.create_note.call_count == 1

    def test_gitlab_server_error_is_raised(self, manager, mock_mr):
        """A 5xx answer is a server failure, not a refusal: it stays an exception."""
        mock_mr.merge.side_effect = GitlabHttpError("502 Bad Gateway", response_code=502)

        with pytest.raises(GitlabHttpError):
            manager.merge()
        mock_mr.create_note.assert_not_called()
