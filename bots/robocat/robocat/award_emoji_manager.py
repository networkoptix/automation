## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)


# NOTE: Hash and eq methods for this object should return different values for different object
# instances on order to lru_cache is working right.
class AwardEmojiManager():
    def __init__(self, gitlab_award_emoji_manager, current_user):
        self._gitlab_manager = gitlab_award_emoji_manager
        self._current_user = current_user

    # The cache belongs to the class rather than to the instance, so every object it has seen
    # stays alive for the lifetime of the process. Suppressed rather than restructured here:
    # changing the caching strategy is a behavioural change and needs its own change.
    # Short term cache. New data is obtained for every bot "handle" call.
    @lru_cache(maxsize=16)  # noqa: B019
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
