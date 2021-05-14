from __future__ import annotations

from typing import List
import tempfile
import string
import random
import dataclasses

import git

BOT_NAME = "Robo Cat"
BOT_USERNAME = "robocat"
BOT_EMAIL = "robocat@foo.bar"


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
        self.heads = {"master": self.head}

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
        self.mock_add_command_to_log(f"clone {url!r} to {path!r}")

    def create_head(self, branch_name: str, commit_path: str) -> HeadMock:
        try:
            # Check if commit_path is sha.
            commit = next(c for c in self.commits if c.sha == commit_path)
        except StopIteration:
            try:
                # Check if commit_path points to the existing branch.
                branch = next(b for n, b in self.branches.items() if n == commit_path)
                commit = branch.commits[-1]
            except StopIteration as exc:
                raise git.BadName(commit_path)

        return HeadMock(self, branch_name=branch_name, commit=commit)

    def rev_parse(self, full_branch_name: str) -> str:
        if full_branch_name in self.branches:
            return repr(self.branches[full_branch_name])
        raise git.BadName(full_branch_name)

    def iter_commits(self, branch: str, grep: str, since: str):
        result = []
        branch = self.branches[branch]
        for commit in branch.commits:
            if grep in commit.message:
                result.append(commit)
        return result


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
        repo.mock_add_command_to_log(f"add remote {name!r} with url {url!r}")
        if name in repo.remotes:
            repo.mock_add_command_to_log(f"remote {name!r} already exists")
            raise git.GitCommandError()

        repo.remotes[name] = cls(repo, name, url)

    def fetch(self):
        self._repo.mock_add_command_to_log(f"fetch {self._name!r}")

    def push(self, branch: str, force: bool = False) -> List[RemoteMock.PushInfo]:
        push = ("forced " if force else "") + "push"
        self._repo.mock_add_command_to_log(f"{push} {branch!r} to {self._name!r}")
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
        self._repo.mock_add_command_to_log(f"{reset_type} reset {self.ref.name!r} to {commit!r}")

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

    def commit(self, message: str, author: git.Actor = None, committer: git.Actor = None):
        sha = random_sha()
        commit = CommitMock(self._repo, sha=sha, message=message)
        current_branch = self._repo.head.ref
        author = f"{author.name} <{author.email}>"
        committer = f"{committer.name} <{committer.email}>"
        self._repo.mock_add_command_to_log(
            f"commit to branch {current_branch.name!r} "
            f"(sha: {commit.sha!r}, message: {commit.message!r}, "
            f"author: {author!r}, committer: {committer!r}")


def random_sha():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
