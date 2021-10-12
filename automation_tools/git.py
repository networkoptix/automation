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
                self.repo.config_writer().set_value(
                    "user", "email", "workflow-robocat@networkoptix.com").release()
                self.repo.config_writer().set_value(
                    "user", "name", "workflow-robocat@networkoptix.com").release()
            else:
                self._committer = None
            self.repo.config_writer().set_value("merge", "renamelimit", 100000).release()
        except git.exc.NoSuchPathError:
            self.repo = git.Repo.clone_from(url, path)

    def update_repository(self, remote: str = "origin"):
        logger.debug(f"Fetching {remote}...")
        try:
            self.repo.remotes[remote].fetch()
        except git.exc.BadName as e:
            # Workaround for https://github.com/gitpython-developers/GitPython/issues/768.
            logger.debug(f"'BadName' exception while fetching remote: {e}. Retrying...")
            self.repo.git.gc("--auto")
            self.repo.remotes[remote].fetch()

    def add_remote(self, remote: str, url: str):
        try:
            git.remote.Remote.add(self.repo, name=remote, url=url)
        except git.GitCommandError as exc:
            logger.debug(f"{self}: Remote repository {remote} already exists ({exc}).")

    def grep_recent_commits(self, substring: str, branch: str) -> List:
        return list(self.repo.iter_commits(
            f"origin/{branch}", grep=substring, since=RECENT_COMMENTS_DEPTH))

    def check_branch_exists(self, branch: str, remote: str = "origin") -> bool:
        try:
            full_branch_name = f"{remote}/{branch}" if remote is not None else branch
            self.repo.rev_parse(full_branch_name)
            return True
        except git.BadName:
            return False

    def squash(
            self, remote: str, url: str, branch: str, message: str, base_sha: str,
            author: automation_tools.utils.User):
        self.add_remote(remote, url)
        self.update_repository(remote)
        self._hard_checkout(remote, branch)
        self._soft_reset(base_sha)
        self._commit(message, git.Actor(name=author.name, email=author.email))
        self._push(remote, branch, force=True)

    def _hard_checkout(self, remote: str, branch: str):
        full_branch_name = f"{remote}/{branch}"
        if branch not in self.repo.heads:
            logger.debug(f"Creating branch {branch} at {full_branch_name}...")
            self.repo.head.reference = self.repo.create_head(branch, full_branch_name)
        elif self._current_branch_name != branch:
            self.repo.head.reference = self.repo.heads[branch]
        self._hard_reset(full_branch_name)

    @property
    def _current_branch_name(self):
        return self.repo.head.reference.name

    def _soft_reset(self, commit: str):
        logger.debug(f"Resetig HEAD to {commit} (soft)...")
        self.repo.head.reset(commit=commit, index=False, working_tree=False)

    def _hard_reset(self, commit: str):
        logger.debug(f"Resetig HEAD to {commit} (hard)...")
        self.repo.head.reset(commit=commit, index=True, working_tree=True)

    def _mixed_reset(self, commit: str):
        logger.debug(f"Resetig HEAD to {commit} (hard)...")
        self.repo.head.reset(commit=commit, index=True, working_tree=False)

    def _commit(self, message: str, author: git.Actor):
        self.repo.index.commit(message, author=author, committer=self._committer)

    def _push(self, remote: str, branch: str, force: bool = False):
        push_info = self.repo.remotes[remote].push(branch, force=force)[0]
        if push_info.flags & git.remote.PushInfo.ERROR:
            remote_url = ", ".join(self.repo.remotes[remote].urls)
            raise git.GitError(
                f"Failed to push branch {branch!r} to {remote_url!r}: {push_info.summary!r}")

    def cherry_pick(self, sha: str, remote: str = "origin", branch: str = None) -> bool:
        if branch is not None:
            self._hard_checkout(remote, branch)

        try:
            logger.debug(f"Cherry-picking {sha} to {branch}...")
            self.repo.git.cherry_pick("-x", sha)
            return True
        except git.GitCommandError as error:
            if "nothing to commit" in error.stdout:
                logging.warning(
                    f"An error occured while cherry-picking: {error!r}. "
                    f"Stdout is: {error.stdout}, stderr is: {error.stderr}. "
                    "Probably, just empty cherry-pick. Trying to continue cherry-pick process.")
                self._mixed_reset("HEAD")
            else:
                raise error from None

        return False

    def create_branch(
            self, new_branch: str, target_remote: str, source_branch: str,
            source_remote: str = "origin", override_local_branch: bool = True):
        self.update_repository(source_remote)
        self.update_repository(target_remote)
        self._hard_checkout(source_remote, source_branch)
        if override_local_branch and self.check_branch_exists(new_branch, None):
            self.repo.head.reference.delete(self.repo, "-D", new_branch)
        self.repo.head.reference = self.repo.create_head(new_branch)
        self._push(target_remote, new_branch, force=True)

    def push_current_branch(self, remote: str):
        logger.debug(f"Pushing {self._current_branch_name} to {remote}")
        self._push(remote, self._current_branch_name, force=True)
