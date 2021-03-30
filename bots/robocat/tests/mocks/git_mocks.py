from __future__ import annotations

from typing import List
import tempfile
import string
import random
import dataclasses

import git


class RepoMock:
    def __init__(self, path):
        self._command_log_file = tempfile.TemporaryFile(mode="w+")
        original_commit = CommitMock(self, sha="000000000000", message="")
        self.commits = [original_commit]
        self.branches = {
            "origin/master": BranchMock(self, name="master", commits=[original_commit])}
        self.index = IndexMock(self)
        self.remotes = {"origin": RemoteMock(self, name="origin", url="")}
        self.head = HeadMock(self, branch_name="master", commit=original_commit)

    def __del__(self):
        self._command_log_file.close()

    def mock_read_commands_log(self) -> List[str]:
        self._command_log_file.seek(0)
        result = self._command_log_file.readlines()
        self._command_log_file.close()
        self._command_log_file = tempfile.TemporaryFile(mode="w+")
        return result

    def mock_add_command_to_log(self, command: str):
        print(command.replace('\n', ' '), file=self._command_log_file)

    def clone_from(self, url, path):
        self.mock_add_command_to_log(f'clone "{url}" to "{path}"')

    def create_head(self, branch_name: str, commit_path: str) -> HeadMock:
        try:
            # Check if commit_path is sha.
            commit = next(c for c in self.commits if c.sha == commit_path)
        except StopIteration:
            try:
                # Check if commit_path points to the existing branch.
                branch = next(b[n] for n, b in self.branches.items() if n == commit_path)
                commit = branch.commits[-1]
            except StopIteration as exc:
                # Create new branch trying to guess the remote name. If the euristics fails, throw
                # an exception.
                if not commit_path.endswith(f"/{branch_name}"):
                    raise RuntimeError(
                        f'There are no branch for "{commit_path}" and it is not possible to '
                        f'create one') from exc
                commit = CommitMock(self, sha=random_sha(), message="")
                self.branches[commit_path] = BranchMock(self, name=branch_name, commits=[commit])

        return HeadMock(self, branch_name=branch_name, commit=commit)


@dataclasses.dataclass
class CommitMock:
    repo: RepoMock
    sha: str
    message: str


@dataclasses.dataclass
class BranchMock:
    repo: RepoMock
    name: str
    commits: List[CommitMock]


class RemoteMock:
    @dataclasses.dataclass
    class PushInfo():
        flags: int = 0
        summary: str = ""

    def __init__(self, repo: RepoMock, name: str, url: str):
        self._repo = repo
        self._name = name
        self._url = url

    @classmethod
    def add(cls, repo: RepoMock, name, url):
        repo.mock_add_command_to_log(f'add remote "{name}" with url "{url}"')
        if name in repo.remotes:
            repo.mock_add_command_to_log(f'remote "{name}" already exists')
            raise git.GitCommandError()

        repo.remotes[name] = cls(repo, name, url)

    def fetch(self):
        self._repo.mock_add_command_to_log(f'fetch "{self._name}"')

    def push(self, branch: str, force: bool = False) -> List[RemoteMock.PushInfo]:
        push = ("forced " if force else "") + "push"
        self._repo.mock_add_command_to_log(f'{push} "{branch}" to "{self._name}"')
        return [RemoteMock.PushInfo()]


class HeadMock:
    def __init__(self, repo: RepoMock, branch_name: str, commit: CommitMock):
        self._repo = repo
        self.commit = commit
        self.ref = next(b for b in repo.branches.values() if b.name == branch_name)

    def reset(self, commit, index: bool, working_tree: bool):
        if working_tree:
            if index:
                reset_type = "hard"
            else:
                assert False, "Bad reset type"
        else:
            if index:
                reset_type = "medium"
            else:
                reset_type = "soft"
        self._repo.mock_add_command_to_log(f'{reset_type} reset "{self.ref.name}" to "{commit}"')

    @property
    def reference(self):
        return self

    @reference.setter
    def reference(self, head_reference: HeadMock):
        self._copy(head_reference)

    def _copy(self, obj: HeadMock):
        self.ref = obj.ref
        self.commit = obj.commit


class IndexMock():
    def __init__(self, repo: RepoMock):
        self._repo = repo

    def commit(self, message: str):
        sha = random_sha()
        commit = CommitMock(self._repo, sha=sha, message=message)
        current_branch = self._repo.head.ref
        self._repo.mock_add_command_to_log(
            f'commit to branch "{current_branch.name}" '
            f'(sha: "{commit.sha}", message: "{commit.message}"')


def random_sha():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
