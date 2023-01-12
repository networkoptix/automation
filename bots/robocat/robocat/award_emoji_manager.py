import logging
from functools import lru_cache

from robocat.note import MessageId

logger = logging.getLogger(__name__)


# NOTE: Hash and eq methods for this object should return different values for different object
# instances on order to lru_cache is working right.
class AwardEmojiManager():
    WATCH_EMOJI = "eyes"
    WAIT_EMOJI = "hourglass_flowing_sand"
    PIPELINE_EMOJI = "construction_site"
    NO_PIPELINE_EMOJI = "no_entry"
    INITIAL_EMOJI = "cat2"
    CHECK_FAIL_EXPLANATION_EMOJI = "exclamation"
    AUTOCHECK_FAILED_EMOJI = "stop_sign"
    AUTOCHECK_OK_EMOJI = "white_check_mark"
    MERGED_EMOJI = "white_check_mark"
    FOLLOWUP_CREATED_EMOJI = "arrow_heading_down"
    FOLOWUP_CREATION_FAILED_EMOJI = "x"
    FOLLOWUP_MERGE_REQUEST_EMOJI = "fast_forward"
    CHERRY_PICK_EMOJI = "cherries"
    UNFINISHED_PROCESSING_EMOJI = "point_up"
    # TODO: Remove this constant when the check for a "huge diff" is eliminated.
    AUTOCHECK_IMPOSSIBLE_EMOJI = "raised_back_of_hand"
    NEED_MANUAL_CHECK_EMOJI = "raised_back_of_hand"
    BAD_ISSUE_EMOJI = "beetle"
    LOCAL_SQUASH_PROBLEMS_EMOJI = "warning"
    NOTIFICATION_EMOJI = "bell"
    ISSUE_NOT_MOVED_TO_QA_EMOJI = "point_up"
    COMMAND_NOT_EXECUTED = "no_entry"

    EMOJI_BY_MESSAGE_ID = {
        MessageId.CommandProcess: NOTIFICATION_EMOJI,
        MessageId.CommandRunPipeline: NOTIFICATION_EMOJI,
        MessageId.CommandFollowUp: NOTIFICATION_EMOJI,
        MessageId.CommandSetDraftFollowUpMode: NOTIFICATION_EMOJI,
        MessageId.JobStatusCheckNeedsApproval: NEED_MANUAL_CHECK_EMOJI,
        MessageId.JobStatusChecksPassed: AUTOCHECK_OK_EMOJI,
        MessageId.CommandNotExecuted: COMMAND_NOT_EXECUTED,
        MessageId.FailedCheckForSuccessfulPipeline: CHECK_FAIL_EXPLANATION_EMOJI,
        MessageId.FailedCheckForConflictsWithTargetBranch: CHECK_FAIL_EXPLANATION_EMOJI,
        MessageId.FailedCheckForUnresolvedThreads: CHECK_FAIL_EXPLANATION_EMOJI,
        MessageId.FailedCheckForNoSupportedProject: CHECK_FAIL_EXPLANATION_EMOJI,
        MessageId.InitialMessage: INITIAL_EMOJI,
    }

    def __init__(self, gitlab_award_emoji_manager, current_user):
        self._gitlab_manager = gitlab_award_emoji_manager
        self._current_user = current_user

    @lru_cache(maxsize=16)  # Short term cache. New data is obtained for every bot "handle" call.
    def _cached_list(self):
        return self._gitlab_manager.list()

    def list(self, own):
        if own:
            return [e for e in self._cached_list() if e.user['username'] == self._current_user]
        return self._cached_list()

    def find(self, name, own):
        return [e for e in self.list(own) if e.name == name]

    def create(self, name, **kwargs) -> bool:
        logger.debug(f"Got request to create emoji {name}")

        if not self.find(name, own=True):
            self._cached_list.cache_clear()
            logger.debug(f"Creating emoji {name}")
            self._gitlab_manager.create({'name': name}, **kwargs)

        return True

    def delete(self, name, own, **kwargs) -> bool:
        logger.debug(f"Got request to remove emoji {name}")

        found_emojis = self.find(name, own)
        if not found_emojis:
            return False

        self._cached_list.cache_clear()
        for emoji in found_emojis:
            logger.debug(f"Removing emoji {emoji}")
            self._gitlab_manager.delete(emoji.id, **kwargs)

        return True
