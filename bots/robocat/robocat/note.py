from enum import Enum, auto
import logging
import re
from typing import Any, Dict, NamedTuple
import yaml

logger = logging.getLogger(__name__)


class MessageId(Enum):
    def _generate_next_value_(name, *_):
        return name

    Initial = auto()
    OpenSourceNeedApproval = auto()

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
    WorkflowNoJiraIssueInCommitMessage = auto()
    WorkflowNoJiraIssueInMr = auto()
    WorkflowOk = auto()
    WorkflowParenthesesNotAllowed = auto()

    FollowUpIssueNotMovedToQA = auto()

    BadCommitMessage = auto()
    BadCommitMessageByKeeper = auto()
    CommitMessageIsOk = auto()

    CommandProcess = auto()
    CommandRunPipeline = auto()
    CommandFollowup = auto()
    CommandSetDraftFollowupMode = auto()
    CommandNotExecuted = auto()

    FailedCheckForSuccessfulPipeline = auto()
    FailedCheckForConflictsWithTargetBranch = auto()
    FailedCheckForUnresolvedThreads = auto()
    FailedCheckForNoSupportedProject = auto()


class Comment(NamedTuple):
    id: MessageId
    text: str


class NoteDetails(NamedTuple):
    message_id: MessageId = None
    sha: str = None
    data: Dict[str, Any] = None


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
    ID_KEY = "Message Id"
    SHA_KEY = "Sha"
    DATA_KEY = "Data"
    DETIALS_RE = re.compile(r"<details><pre>\s*(?P<details>.+?)\s*</pre></details>", re.DOTALL)

    def __init__(self, note_data: Dict[str, Any]):
        self.discussion_id = note_data["_discussion_id"]
        self.author = note_data["author"]["username"]
        self.created_at = note_data["created_at"]
        self.body = note_data["body"]
        self.resolvable = note_data.get("resolvable", False)
        if self.resolvable and note_data.get("resolved", False):
            self.resolved_by = note_data.get("resolved_by", "")
        else:
            self.resolved_by = None
        note_details = self._parse_node_details(note_data["body"])
        self.message_id = note_details.message_id
        self.sha = note_details.sha
        self.additional_data = note_details.data or {}

    @classmethod
    def _parse_node_details(cls, note_text: str) -> NoteDetails:
        details_text_match = cls.DETIALS_RE.search(note_text)
        if not details_text_match:
            return NoteDetails()

        details_text = details_text_match.group("details")
        try:
            details = yaml.safe_load(details_text)
        except yaml.scanner.ScannerError as exc:
            logger.error(f"Mailformed Robocat data {details_text!r}: {exc}")
            return NoteDetails()

        try:
            message_id = MessageId(details[cls.ID_KEY])
        except ValueError:
            logger.warning(
                f"Bad message id {details[cls.ID_KEY]!r} in note {note_text!r}; "
                "skipping additional data for this note.")
            return NoteDetails()

        try:
            sha = details[cls.SHA_KEY]
        except KeyError:
            logger.warning(
                f"Missing sha in note {note_text!r}; skipping additional data for this note.")
            return NoteDetails()

        return NoteDetails(message_id=message_id, sha=sha, data=details.get(cls.DATA_KEY, None))

    @classmethod
    def format_details_string(
            cls, message_id: MessageId, sha: str, data: Dict[str, Any] = None) -> str:
        if data:
            payload = {cls.ID_KEY: message_id.value, cls.SHA_KEY: sha, cls.DATA_KEY: data}
        else:
            payload = {cls.ID_KEY: message_id.value, cls.SHA_KEY: sha}
        return f"<details><pre>{yaml.dump(payload, default_flow_style=False)}</pre></details>"
