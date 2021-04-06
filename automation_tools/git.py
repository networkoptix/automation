from pathlib import Path
from typing import List, Optional
import logging

import git

import automation_tools.utils

logger = logging.getLogger(__name__)

RECENT_COMMENTS_DEPTH = '18 month ago'


class Repo:
    def __init__(
            self, path: Path, url: str,
            committer: Optional[automation_tools.utils.User] = None):
        try:
            self.repo = git.Repo(path)
            if committer is not None:
                self._committer = git.Actor(name=committer.name, email=committer.email)
            else:
                self._committer = None
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

    def squash(
            self, remote: str, url: str, branch: str, message: str, base_sha: str,
            author: automation_tools.utils.User):
        self.add_remote(remote, url)
        self.update_repository(remote)
        self._checkout(remote, branch)
        self._soft_reset(base_sha)
        self._commit(message, git.Actor(name=author.name, email=author.email))
        self._push(remote, branch, force=True)

    def _checkout(self, remote: str, branch: str):
        full_branch_name = f"{remote}/{branch}"
        if branch not in self.repo.heads:
            self.repo.head.reference = self.repo.create_head(branch, full_branch_name)
        elif self.repo.head.reference.name != branch:
            self.repo.head.reference = self.repo.heads[branch]
        self._hard_reset(full_branch_name)

    def _soft_reset(self, commit: str):
        self.repo.head.reset(commit=commit, index=False, working_tree=False)

    def _hard_reset(self, commit: str):
        self.repo.head.reset(commit=commit, index=True, working_tree=True)

    def _commit(self, message: str, author: git.Actor):
        self.repo.index.commit(message, author=author, committer=self._committer)

    def _push(self, remote: str, branch: str, force: bool = False):
        push_info = self.repo.remotes[remote].push(branch, force=force)[0]
        if push_info.flags & git.remote.PushInfo.ERROR:
            remote_url = ", ".join(self.repo.remotes[remote].urls)
            raise git.GitError(
                f"Failed to push branch {branch!r} to {remote_url!r}: {push_info.summary!r}")
