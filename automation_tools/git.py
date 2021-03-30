from pathlib import Path
from typing import List, Optional
import logging

import git

import automation_tools.utils

logger = logging.getLogger(__name__)

RECENT_COMMENTS_DEPTH = '18 month ago'


class Repo:
    def __init__(self, path: Path, url: str):
        try:
            self.repo = git.Repo(path)
        except git.exc.NoSuchPathError:
            self.repo = git.Repo.clone_from(url, path)

    def update_repository(self, remote: str = "origin"):
        self.repo.remotes[remote].fetch()

    def add_remote(self, remote: str, url: str):
        try:
            git.remote.Remote.add(self.repo, name=remote, url=url)
        except git.GitCommandError as exc:
            logger.debug(f"{self}: Remote repository {remote} already exists ({exc}).")

    def grep_recent_commits(self, substring: str, branch: str) -> List:
        return list(self.repo.iter_commits(
            f"origin/{branch}", grep=substring, since=RECENT_COMMENTS_DEPTH))

    def check_branch_exists(self, branch: str) -> bool:
        try:
            self.repo.rev_parse(f"origin/{branch}")
            return True
        except git.BadName:
            return False

    def squash(self, remote: str, url: str, branch: str, message: str, base_sha: str):
        self.add_remote(remote, url)
        self.update_repository(remote)
        self._checkout(remote, branch)
        self._soft_reset(base_sha)
        self._commit(message)
        self._push(remote, branch, force=True)

    def _checkout(self, remote: str, branch: str):
        full_branch_name = f"{remote}/{branch}"
        if self.repo.head.ref.name != branch:
            branch_head = self.repo.create_head(branch, full_branch_name)
            self.repo.head.reference = branch_head
        self.repo.head.reset(commit=full_branch_name, index=True, working_tree=True)

    def _soft_reset(self, commit: str):
        self.repo.head.reset(commit=commit, index=False, working_tree=False)

    def _commit(self, message: str):
        self.repo.index.commit(message)

    def _push(self, remote: str, branch: str, force: bool = False):
        push_info = self.repo.remotes[remote].push(branch, force=force)[0]
        if push_info.flags & git.remote.PushInfo.ERROR:
            remote_url = ", ".join(self.repo.remotes[remote].urls)
            raise git.GitError(
                f'Failed to push branch "{branch}" to {remote_url}: {push_info.summary}')
