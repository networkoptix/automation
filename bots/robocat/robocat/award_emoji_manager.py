import logging

logger = logging.getLogger(__name__)


class AwardEmojiManager():
    WATCH_EMOJI = "eyes"
    WAIT_EMOJI = "hourglass_flowing_sand"
    PIPELINE_EMOJI = "construction_site"
    INITIAL_EMOJI = "cat2"
    RETURN_TO_DEVELOPMENT_EMOJI = "exclamation"
    AUTOCHECK_FAILED_EMOJI = "stop_sign"
    AUTOCHECK_OK_EMOJI = "white_check_mark"
    MERGED_EMOJI = "white_check_mark"

    def __init__(self, gitlab_award_emoji_manager, current_user, dry_run=False):
        self._gitlab_manager = gitlab_award_emoji_manager
        self._current_user = current_user
        self._dry_run = dry_run

    def list(self, own):
        if own:
            return [
                e for e in self._gitlab_manager.list(as_list=False)
                if e.user['username'] == self._current_user]
        return self._gitlab_manager.list()

    def find(self, name, own):
        return [e for e in self.list(own) if e.name == name]

    def create(self, name, **kwargs):
        logger.debug(f"Creating emoji {name}")
        if self._dry_run:
            return

        if not self.find(name, own=True):
            self._gitlab_manager.create({'name': name}, **kwargs)

    def delete(self, name, own, **kwargs):
        logger.debug(f"Removing {name} emoji")
        if self._dry_run:
            return

        for emoji in self.find(name, own):
            self._gitlab_manager.delete(emoji.id, **kwargs)
