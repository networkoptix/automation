import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


# NOTE: Hash and eq methods for this object should return different values for different object
# instances on order to lru_cache is working right.
class AwardEmojiManager():
    WATCH_EMOJI = "eyes"
    WAIT_EMOJI = "hourglass_flowing_sand"
    PIPELINE_EMOJI = "construction_site"
    INITIAL_EMOJI = "cat2"
    RETURN_TO_DEVELOPMENT_EMOJI = "exclamation"
    AUTOCHECK_FAILED_EMOJI = "stop_sign"
    AUTOCHECK_OK_EMOJI = "white_check_mark"
    MERGED_EMOJI = "white_check_mark"
    FOLLOWUP_CREATED_EMOJI = "arrow_heading_down"
    FOLOWUP_CREATION_FAILED_EMOJI = "x"
    FOLLOWUP_MERGE_REQUEST_EMOJI = "fast_forward"
    CHERRY_PICK_EMOJI = "cherries"
    UNFINISHED_PROCESSING_EMOJI = "point_up"
    AUTOCHECK_IMPOSSIBLE_EMOJI = "raised_back_of_hand"

    def __init__(self, gitlab_award_emoji_manager, current_user, dry_run=False):
        self._gitlab_manager = gitlab_award_emoji_manager
        self._current_user = current_user
        self._dry_run = dry_run

    @lru_cache(maxsize=16)  # Short term cache. New data is obtained for every bot "handle" call.
    def _cached_list(self):
        return self._gitlab_manager.list()

    def list(self, own):
        if own:
            return [e for e in self._cached_list() if e.user['username'] == self._current_user]
        return self._cached_list()

    def find(self, name, own):
        return [e for e in self.list(own) if e.name == name]

    def create(self, name, **kwargs):
        logger.debug(f"Creating emoji {name}")
        if self._dry_run:
            return

        if not self.find(name, own=True):
            self._cached_list.cache_clear()
            self._gitlab_manager.create({'name': name}, **kwargs)

    def delete(self, name, own, **kwargs):
        logger.debug(f"Removing {name} emoji")
        if self._dry_run:
            return

        found_emojis = self.find(name, own)
        if not found_emojis:
            return

        self._cached_list.cache_clear()
        for emoji in found_emojis:
            self._gitlab_manager.delete(emoji.id, **kwargs)
