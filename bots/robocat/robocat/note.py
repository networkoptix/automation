## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from collections.abc import Callable
from enum import Enum, auto
import logging
import re
from typing import Any, Optional
import yaml

logger = logging.getLogger(__name__)


class MessageId(Enum):
    def _generate_next_value_(name, *_):
        return name

    InitialMessage = auto()
    JobStatusCheckNeedsApproval = auto()
    JobStatusChecksPassed = auto()
    InconsistentNxSubmoduleChange = auto()
    NxSubmoduleConfigDeleted = auto()
    NxSubmoduleConfigMalformed = auto()
    NxSubmoduleConfigBadGitData = auto()
    NxSubmoduleCheckUnknownError = auto()
    NxSubmoduleCheckHugeDiffUncheckable = auto()
    NxSubmoduleCheckPassed = auto()
    WorkflowBadFixVersions = auto()
    WorkflowDifferentCommitMessage = auto()
    WorkflowDifferentJiraIssueSets = auto()
    WorkflowInconsistentFixVersions = auto()
    WorkflowBadTargetBranch = auto()
    WorkflowNoJiraIssueInCommitMessage = auto()
    WorkflowNoJiraIssueInMr = auto()
    WorkflowOk = auto()
    WorkflowParenthesesNotAllowed = auto()
    InconsistentAssigneesInJiraAndGitlab = auto()
    SuspiciousJiraIssueStatus = auto()
    FollowUpNotNeeded = auto()
    FollowUpIssueNotMovedToQA = auto()
    BadCommitMessage = auto()
    BadCommitMessageByKeeper = auto()
    CommitMessageIsOk = auto()
    CommandProcess = auto()
    CommandRunPipeline = auto()
    CommandFollowUp = auto()
    CommandSetDraftFollowUpMode = auto()
    CommandNotExecuted = auto()
    CommandUnknown = auto()
    FailedCheckForSuccessfulPipeline = auto()
    FailedCheckForConflictsWithTargetBranch = auto()
    FailedCheckForUnresolvedThreads = auto()
    FailedCheckForNoSupportedProject = auto()
    FailedJobNotification = auto()
    ExceptionOccurred = auto()
    CannotApproveAsUser = auto()
    FollowUpExistsForTheBranch = auto()
    UnknownBranchWhenCreatingFollowUp = auto()
    ManualResolutionRequired = auto()
    FailedMrMergedJiraComment = auto()
    UnknownProjectWhenClosingIssue = auto()
    RefuseRunPipelineMessage = auto()
    AuthorizedApproversAssigned = auto()
    RunPipelineMessage = auto()
    WaitingForCommits = auto()
    WaitingForApproval = auto()
    WaitingForPipeline = auto()
    MrMerged = auto()
    FollowUpCreationSuccessful = auto()
    FollowUpCreationFailed = auto()
    CannotSquashLocally = auto()
    CannotRestoreApprovals = auto()

class NoteDetails:
    _ID_KEY = "Message Id"
    _SHA_KEY = "Sha"
    _DATA_KEY = "Data"
    _DETAILS_RE = re.compile(r"<details><pre>\s*(?P<details>.+?)\s*</pre></details>", re.DOTALL)

    def __init__(self, message_id: MessageId = None, sha: str = None, data: dict[str, Any] = None):
        self.message_id = message_id
        self.sha = sha
        self.data = data

    def __str__(self):
        payload = {self._ID_KEY: self.message_id.value, self._SHA_KEY: self.sha}
        if self.data:
            payload[self._DATA_KEY] = self.data
        return f"<details><pre>{yaml.dump(payload, default_flow_style=False)}</pre></details>"

    @classmethod
    def create_from_text(cls, text: str) -> "NoteDetails":
        details_text_match = cls._DETAILS_RE.search(text)
        if not details_text_match:
            return cls()

        details_text = details_text_match.group("details")
        try:
            details = yaml.safe_load(details_text)
        except yaml.scanner.ScannerError as exc:
            logger.error(f"Malformed Robocat data {details_text!r}: {exc}.")
            return cls()

        try:
            message_id = MessageId(details[cls._ID_KEY])
        except ValueError:
            logger.warning(
                f"Bad message id {details[cls._ID_KEY]!r} in note {text!r}; skipping additional "
                "data for this note.")
            return cls()

        try:
            sha = details[cls._SHA_KEY]
        except KeyError:
            logger.warning(
                f"Missing sha in note {text!r}; skipping additional data for this note.")
            return cls()

        return cls(message_id=message_id, sha=sha, data=details.get(cls._DATA_KEY, None))

    def substitute_details_in_text(self, text: str) -> str:
        return re.sub(self._DETAILS_RE, str(self), text)


# Gitlab allows to collapse some parts of the comment using <details> tag, so we are adding a
# "hidden" machine-readable information to the bot comments inside this tag. The format is as
# follows:
# <details>
# Message Id: "message_type_id"
# Sha: "sha"
# Data:
#   "additional_data_line_1"
#   ...
#   "additional_data_line_n"
# </details>
#
# where
# "message_type_id" is an unique string identifying the message type,
# "sha" is the hash of the last commit in the Merge Request at the moment of the comment creation,
# "additional_data_line_*" lines represents an arbitrary yaml-encoded data specific to the message
# type; these lines along with the "Data:" line are optional.
class Note:
    def __init__(self, note_data: dict[str, Any]):
        self.note_id = note_data["id"]
        self.discussion_id = note_data.get("_discussion_id")
        self.author = note_data["author"]["username"]
        self.created_at = note_data["created_at"]
        self.body = note_data["body"]
        self.resolvable = note_data.get("resolvable", False)
        if self.resolvable and note_data.get("resolved", False):
            self.resolved_by = note_data.get("resolved_by", "")
        else:
            self.resolved_by = None
        note_details = NoteDetails.create_from_text(note_data["body"])
        self.message_id = note_details.message_id
        self.sha = note_details.sha
        self.additional_data = note_details.data or {}

    def update_details(self, details: NoteDetails):
        self.body = details.substitute_details_in_text(self.body)
        self.message_id = details.message_id
        self.sha = details.sha
        self.additional_data = details.data or {}


def find_first_comment(
        notes: list[Note],
        message_id: MessageId,
        condition: Optional[Callable[[Note], bool]] = None,
        crash_if_not_found: bool = False) -> Optional[Note]:
    if condition is None:
        condition = lambda _: True
    try:
        return next(
            iter(n for n in notes if n.message_id == message_id and condition(n)))
    except StopIteration as e:
        if crash_if_not_found:
            raise e
        return None


def find_last_comment(
        notes: list[Note],
        message_id: MessageId,
        condition: Optional[Callable[[Note], bool]] = None,
        crash_if_not_found: bool = False) -> Optional[Note]:
    return find_first_comment(
        notes=reversed(notes),
        message_id=message_id,
        condition=condition,
        crash_if_not_found=crash_if_not_found)
