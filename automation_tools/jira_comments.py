## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from enum import Enum, auto
from typing import Optional, Union
import re
import yaml

import automation_tools.bot_info


class JiraMessageId(Enum):
    def _generate_next_value_(name, *_):
        return name

    IssueMovedToQa = auto()
    IssueClosed = auto()
    ReopenIssue = auto()
    FollowUpMrsCreated = auto()
    FollowUpError = auto()
    IssueAlreadyFinalized = auto()
    UnableToReopenIssue = auto()
    MrMergedToBranch = auto()


class JiraCommentDataKey(Enum):
    MrBranch = auto()
    MrId = auto()


class JiraCommentError(RuntimeError):
    pass


class JiraComment:
    _TECHNICAL_DETAILS_WRAPPER_START = "{noformat:title=Technical details:}"
    _TECHNICAL_DETAILS_WRAPPER_END = "{noformat}"
    _ID_KEY = "Message Id"
    _DATA_KEY = "Data"
    # TODO: Remove "|{{noformat}}" from the regex after some weeks - it is here for the
    # compatibility wtih the previous format.
    _DETAILS_RE = re.compile(
        rf"(?:{_TECHNICAL_DETAILS_WRAPPER_START}|{{noformat}})\s*(?P<details>.+?)\s*"
        f"{_TECHNICAL_DETAILS_WRAPPER_END}",
        re.DOTALL)

    def __init__(
            self,
            message_id: JiraMessageId,
            params: Union[dict[str, str], str],
            data: dict[str, str] = None):
        self.message_id = message_id
        self.data = data
        if isinstance(params, str):
            self._raw_text = params
            self._message_params = None
        else:
            self._raw_text = None
            self._message_params = params

    def __str__(self):
        if self._raw_text and self._message_params:
            raise JiraCommentError(
                "Comment object is invalid: both raw text and message parameters are set.")

        if self._raw_text:
            return self._raw_text

        text = MESSAGE_TEMPLATES[self.message_id].format(**self._message_params)

        details = {self._ID_KEY: self.message_id.value}
        if self.data:
            details[self._DATA_KEY] = self.data
        text += (
            f"\n\n{self._TECHNICAL_DETAILS_WRAPPER_START}" + yaml.safe_dump(details) +
            f"{self._TECHNICAL_DETAILS_WRAPPER_END}")

        bot_name = automation_tools.bot_info.name()
        bot_signature = BOT_SIGNATURES.get(bot_name, f"Unknown bot name: {bot_name}").format(
            revision=automation_tools.bot_info.revision() or '')
        text += f"\n\n{bot_signature}"

        return text

    @classmethod
    def from_string(cls, text: str) -> Optional["JiraComment"]:
        details_text_match = cls._DETAILS_RE.search(text)
        if not details_text_match:
            return None

        details_text = details_text_match.group("details")
        try:
            details = yaml.safe_load(details_text)
        except yaml.scanner.ScannerError as exc:
            raise JiraCommentError(f"Malformed comment data {details_text!r}: {exc}.")

        try:
            message_id = JiraMessageId(details[cls._ID_KEY])
        except KeyError:
            raise JiraCommentError(f"Malformed comment data {details_text!r}: No {cls._ID_KEY!r}.")
        except ValueError:
            raise JiraCommentError(
                f"Bad message id {details[cls._ID_KEY]!r} in comment {text!r}; skipping "
                f"additional data for this note.")

        return cls(message_id=message_id, data=details.get(cls._DATA_KEY, None), params=text)


BOT_SIGNATURES = {
    "Robocat": """h5. 🐱 Robocat rev. {revision}. See its [documentation|https://github.com/networkoptix/automation/blob/master/bots/robocat/readme.md].""",  # noqa
    "Police": "h5. 🚔 Workflow Police {revision}. Find its documentation in Confluence.",
}


MESSAGE_TEMPLATES = {
    JiraMessageId.IssueMovedToQa: """Issue moved to QA because merge requests for all "fixVersions"
were merged into their respective branches:

* {branches}""",
    JiraMessageId.IssueClosed: """Issue closed because merge requests for all "fixVersions" were
merged into their respective branches:

* {branches}""",
    JiraMessageId.ReopenIssue: """Returning the issue, workflow violation found:

* {reason}.

{{color:#97a0af}}Issues closed with a resolution
"{{color}}{{color:#97a0af}}*{resolution}*{{color}}{{color:#97a0af}}" come under mandatory Workflow
Police inspection. Please, consider changing resolution value if the issue *does not imply any code
changes*.{{color}}""",
    JiraMessageId.FollowUpMrsCreated: """Merge requests for cherry-picking changes were autocreated
for the following branches:

* {branches}""",
    JiraMessageId.FollowUpError: """An error occurred while trying to execute follow-up actions for
merge request [{mr_name}|{mr_url}]:

{{panel}}{error}{{panel}}

Please, investigate the problem - check this merge request and all related Jira issues.""",
    JiraMessageId.IssueAlreadyFinalized: """The Issue is already in "{status}" status. This
situation is considered as a workflow violation - it is strongly advised to avoid this in the
future.""",
    JiraMessageId.UnableToReopenIssue: """Unable to reopen issue {issue}: {error}. Forcing status
"{status}".""",
    JiraMessageId.MrMergedToBranch: """Merge request [{mr_name}|{mr_url}] has been merged to branch
*{mr_branch}*.
""",
}
