## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import string

import pytest
from robocat.comments import Comment, Emoji, Message
from robocat.note import NoteDetails

# The names stored in the "Message Id" of existing GitLab notes: a renamed member breaks them.
STORED_NAMES = [
    "InitialMessage", "JobStatusCheckNeedsApproval", "JobStatusChecksPassed",
    "InconsistentNxSubmoduleChange", "NxSubmoduleConfigDeleted", "NxSubmoduleConfigMalformed",
    "NxSubmoduleConfigBadGitData", "NxSubmoduleCheckUnknownError",
    "NxSubmoduleCheckHugeDiffUncheckable", "NxSubmoduleCheckPassed", "WorkflowBadFixVersions",
    "WorkflowDifferentCommitMessage", "WorkflowDifferentJiraIssueSets",
    "WorkflowInconsistentFixVersions", "WorkflowBadTargetBranch",
    "WorkflowNoJiraIssueInCommitMessage", "WorkflowNoJiraIssueInMr", "WorkflowOk",
    "WorkflowParenthesesNotAllowed", "InconsistentAssigneesInJiraAndGitlab",
    "UnassignedJiraIssue", "SuspiciousJiraIssueStatus", "FollowUpNotNeeded",
    "FollowUpIssueNotMovedToQA", "BadCommitMessage", "BadCommitMessageByKeeper",
    "CommitMessageIsOk", "CommandProcess", "CommandRunPipeline", "CommandFollowUp",
    "CommandSetDraftFollowUpMode", "CommandNotExecuted", "CommandUnknown",
    "FailedCheckForSuccessfulPipeline", "FailedCheckForConflictsWithTargetBranch",
    "FailedCheckForUnresolvedThreads", "FailedCheckForNoSupportedProject",
    "FailedJobNotification", "ExceptionOccurred", "CannotApproveAsUser",
    "FollowUpExistsForTheBranch", "UnknownBranchWhenCreatingFollowUp",
    "ManualResolutionRequired", "FailedMrMergedJiraComment", "UnknownProjectWhenClosingIssue",
    "RefuseRunPipelineMessage", "AuthorizedApproversAssigned",
    "CommitMessageAuthorizedApproversAssigned", "RunPipelineMessage", "WaitingForCommits",
    "WaitingForApproval", "WaitingForPipeline", "MrMerged", "FollowUpCreationSuccessful",
    "FollowUpCreationFailed", "CannotSquashLocally", "CannotRestoreApprovals",
    "FollowUpInitialMessage", "MergeRejected", "RebaseRejected",
    "RebaseRejectedSourceBranchMissing", "RebaseRejectedCannotPush",
    "RebaseRejectedForcePushProtected",
]


REACTION_EMOJI = [  # The reactions on MRs that are open now: a change loses their state.
    ("WATCHING", "eyes"),
    ("WAIT", "hourglass_flowing_sand"),
    ("FOLLOWUP_MERGE_REQUEST", "fast_forward"),
    ("UNFINISHED_POST_MERGING", "point_up"),
    ("BAD_ISSUE", "beetle"),
    ("SUSPICIOUS_ISSUE", "question"),
]


class TestComment:
    """The catalog of Robocat comments."""

    def test_stored_names_are_unchanged(self):
        """Every name that old notes store still exists, so old notes are still found."""
        assert sorted(STORED_NAMES) == sorted(Comment.__members__)

    @pytest.mark.parametrize("comment", list(Comment), ids=lambda comment: comment.name)
    def test_comment_is_complete(self, comment: Comment):
        """Every comment has a title, an emoji and a text."""
        assert comment.value.title
        assert comment.value.emoji
        assert comment.value.text

    @pytest.mark.parametrize("comment", list(Comment), ids=lambda comment: comment.name)
    def test_note_details_round_trip(self, comment: Comment):
        """A note written with a comment is read back as the same comment."""
        details = NoteDetails(message_id=comment, sha="abc123", data={"key": "value"})

        read = NoteDetails.create_from_text(f"### Title\n\nText\n{details}")

        assert read.message_id is comment
        assert read.sha == "abc123"
        assert read.data == {"key": "value"}

    @pytest.mark.parametrize("comment", list(Comment), ids=lambda comment: comment.name)
    def test_comment_body_is_complete(self, comment: Comment):
        """Every comment builds its posted body: the title line, and every value filled in."""
        fields = {name for _, name, _, _ in string.Formatter().parse(comment.value.text) if name}

        body = Message(comment, {name: f"<{name}>" for name in fields}).format_body()

        assert body.startswith(f"### :{comment.value.emoji}: {comment.value.title}\n")
        assert all(f"<{name}>" in body for name in fields)
        assert "{" not in body and "}" not in body


class TestReactionEmoji:
    """The emoji that Robocat sets on an MR as a state flag and reads back later."""

    @pytest.mark.parametrize(("name", "gitlab_name"), REACTION_EMOJI)
    def test_reaction_emoji_is_unchanged(self, name: str, gitlab_name: str):
        """A reaction keeps its name and GitLab emoji, so Robocat still reads open MRs."""
        assert Emoji[name] == gitlab_name
