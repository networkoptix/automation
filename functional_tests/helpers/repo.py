from typing import List

import git


def create_branch(repo: git.Repo, branch_name: str):
    repo.create_head(branch_name)


def create_and_push_commit(
        repo: git.Repo, branch_name: str, updated_files: List[str], message: str):
    repo.head.reference = repo.heads[branch_name]
    repo.index.add(updated_files)
    repo.index.commit(message)
    repo.remotes.origin.push(repo.head.name)
