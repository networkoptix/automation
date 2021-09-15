import time
from typing import List, Optional

import git

import helpers.tests_config

BRANCH_COUNTER = 1


def create_branch(repo: git.Repo, branch_name: str):
    repo.create_head(branch_name)


def create_and_push_commit(
        repo: git.Repo, branch_name: str, updated_files: List[str], message: str,
        wait_after_push: bool = True, forced_push: bool = False):
    create_commit(repo, branch_name, updated_files, message)
    push(repo, branch_name, force=forced_push)

    if wait_after_push:
        time.sleep(helpers.tests_config.POST_MR_SLIIP_S)


def create_commit(
        repo: git.Repo, branch_name: str, updated_files: List[str], message: str):
    repo.head.reference = repo.heads[branch_name]
    repo.index.add(updated_files)
    proc = repo.git.status(untracked_files=True, as_process=True)
    repo.index.commit(message)


def amend_last_commit(
        repo: git.Repo, branch_name: str, updated_files: Optional[List[str]] = None,
        message: Optional[str] = None):
    repo.head.reference = repo.heads[branch_name]

    if updated_files is not None:
        repo.head.reset(commit="HEAD~1", index=True, working_tree=False)
        repo.index.add(updated_files)
    else:
        repo.head.reset(commit="HEAD~1", index=False, working_tree=False)

    new_message = message if message is not None else repo.head.commit.message
    repo.index.commit(new_message)


def push(repo: git.Repo, branch_name: str, force: bool = False):
    push_info = repo.remotes.origin.push(repo.head.name, force=force)[0]
    if push_info.flags & git.remote.PushInfo.ERROR:
        remote_url = ", ".join(repo.remotes.origin.urls)
        raise git.exc.GitError(
            f"Failed to push branch {branch_name!r} to {remote_url!r}: {push_info.summary!r}")


def hard_checkout(repo: git.Repo, branch_name: str):
    repo.head.reference = repo.heads[branch_name]
    repo.head.reset(commit="HEAD", index=True, working_tree=True)
