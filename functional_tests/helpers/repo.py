import time
from typing import List, Optional

import git

BRANCH_COUNTER = 1


def create_branch(repo: git.Repo, branch_name: str):
    repo.create_head(branch_name)


def create_and_push_commit(
        repo: git.Repo, branch_name: str, updated_files: List[str], message: str):
    create_commit(repo, branch_name, updated_files, message)
    push(repo, branch_name)

    time.sleep(5)  # Wait for some time to allow gitlab to do all the post-push magic.


def create_commit(
        repo: git.Repo, branch_name: str, updated_files: List[str], message: str):
    repo.head.reference = repo.heads[branch_name]
    repo.index.add(updated_files)
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


def push(repo: git.Repo, branch_name: str):
    push_info = repo.remotes.origin.push(repo.head.name)[0]
    if push_info.flags & git.remote.PushInfo.ERROR:
        remote_url = ", ".join(repo.remotes.origin.urls)
        raise git.exc.GitError(
            f"Failed to push branch {branch_name!r} to {remote_url!r}: {push_info.summary!r}")
