## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from __future__ import annotations

import tempfile
import string
import random
import dataclasses
from pathlib import Path
import shutil

import git


class RepoMock:
    def __init__(self, *_):
        self._command_log_file = tempfile.TemporaryFile(mode="w+")
        original_commit = CommitMock(self, sha="000000000000", message="")
        self.commits = [original_commit]
        self.branches = {
            "origin/master": BranchMock(self, name="master", commits=[original_commit])}
        self.index = IndexMock(self)
        self.remotes = {"origin": RemoteMock(self, name="origin", url="")}
        self.head = HeadMock(self, branch_name="master", commit=original_commit)
        self.heads = {"master": self.head}
        self.git = GitCommandMock(self)
        self.mock_gitlab_projects = {}
        self.mock_cherry_pick_conflicts = []
        self.mock_changes_already_in_branch = []
        self.mock_unknown_commits = set()

    def __del__(self):
        self._command_log_file.close()

    def mock_read_commands_log(self) -> list[str]:
        self._command_log_file.seek(0)
        result = self._command_log_file.readlines()
        self._command_log_file.close()
        self._command_log_file = tempfile.TemporaryFile(mode="w+")
        return result

    def mock_add_command_to_log(self, command: str):
        print(command.replace('\n', ' '), file=self._command_log_file)

    def mock_reset_commands_log(self):
        self._command_log_file = tempfile.TemporaryFile(mode="w+")

    def add_mock_commit(self, sha: str, message: str):
        new_commit = CommitMock(self, sha=sha, message=message)
        self.commits.append(new_commit)
        self.head.commit = new_commit
        self.head.ref.commits.append(new_commit)

    @classmethod
    def clone_from(cls, url, to_path):
        soruce_path = Path(__file__).parent / "data" / url
        try:
            shutil.copytree(soruce_path, to_path, dirs_exist_ok=True)
        except FileNotFoundError:
            raise git.exc.GitCommandError(status=f"Bad repo url", command=f"git clone {url}")

        result = cls()
        if (soruce_path / ".gitmock" / "unknown_commits").is_file():
            with open(soruce_path / ".gitmock" / "unknown_commits") as f:
                commit = f.readline().strip()
                if commit:
                    result.mock_unknown_commits.add(commit)

        return result

    def create_head(self, branch_name: str, commit_path: str = None) -> HeadMock:
        if commit_path is None:
            commit = self.commits[-1]
            self.branches[branch_name] = BranchMock(self, name=branch_name, commits=self.commits)
        else:
            # Check if commit_path is sha.
            commit = next((c for c in self.commits if c.sha == commit_path), None)
            if not commit:
                # Check if commit_path points to an existing branch.
                branch = next((b for n, b in self.branches.items() if n == commit_path), None)
                if not branch:
                    raise git.BadName(commit_path)
                commit = branch.commits[-1]

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

    def mock_add_gitlab_project(self, project: ProjectMock):
        self.mock_gitlab_projects[project.ssh_url_to_repo] = project

    def config_writer(self):
        return GitConfigParserMock()


class GitCommandMock:
    def __init__(self, repo: RepoMock):
        self._repo = repo

    def cherry_pick(self, *args):
        self._repo.mock_add_command_to_log(f"Cherry-pick with arguments: {args!r}")
        sha = args[-1]
        if sha == "--continue":
            return
        if sha in self._repo.mock_cherry_pick_conflicts:
            raise git.GitCommandError(command=f"git cherry-pick {args!r}", status="Conflict")
        if sha in self._repo.mock_changes_already_in_branch:
            raise git.GitCommandError(
                command=f"git cherry-pick {args!r}",
                status="Empty commit",
                stdout="nothing to commit")
        commit = next(c for c in self._repo.commits if c.sha == sha)
        if "-x" in args:
            message = f"{commit.message}\n\n(cherry picked from commit {sha})"
        else:
            message = commit.message
        self._repo.add_mock_commit(sha=random_sha(), message=message)

    def clean(self, *_):
        pass


@dataclasses.dataclass
class CommitMock:
    repo: RepoMock
    sha: str
    message: str


@dataclasses.dataclass
class BranchMock:
    repo: RepoMock
    name: str
    commits: list[CommitMock]


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
            error_message = f"remote {name!r} already exists"
            repo.mock_add_command_to_log(error_message)
            raise git.GitCommandError(status=error_message, command="git add remote")

        repo.remotes[name] = cls(repo, name, url)

    def mock_attach_gitlab_project(self, project: ProjectMock):
        self._url = project.ssh_url_to_repo
        self._repo.mock_add_gitlab_project(project)

    def fetch(self, *_):
        self._repo.mock_add_command_to_log(f"fetch {self._name!r}")
        if self._url in self._repo.mock_gitlab_projects:
            project = self._repo.mock_gitlab_projects[self._url]
            for branch in project.branches.branches:
                full_branch_name = f"{project.namespace['full_path']}/{branch.name}"
                self._repo.branches[full_branch_name] = BranchMock(
                    self,
                    name=branch.name,
                    commits=[CommitMock(self, sha=random_sha(), message="")])

    def push(self, branch: str, force: bool = False) -> list[RemoteMock.PushInfo]:
        push = ("forced " if force else "") + "push"
        self._repo.mock_add_command_to_log(f"{push} {branch!r} to {self._name!r}")
        if branch not in self._repo.branches:
            return [RemoteMock.PushInfo()]

        # TODO: Here should be a deep copy of BranchMock object.
        self._repo.branches[f"{self._name}/{branch}"] = self._repo.branches[branch]

        if self._url in self._repo.mock_gitlab_projects:
            project = self._repo.mock_gitlab_projects[self._url]
            project.add_mock_branch(branch)
            for commit in self._repo.branches[branch].commits:
                if commit.sha not in [c.sha for c in project.commits.list()]:
                    project.add_mock_commit(branch, commit.sha, commit.message)

        return [RemoteMock.PushInfo()]


class HeadMock:
    def __init__(self, repo: RepoMock, branch_name: str, commit: CommitMock):
        self._repo = repo
        self.commit = commit
        self._branch_name = branch_name

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
        if commit in self._repo.mock_unknown_commits:
            raise git.exc.GitCommandError(status="Unknown commit", command=f"git reset {commit}")
        self._repo.mock_add_command_to_log(f"{reset_type} reset {self.ref.name!r} to {commit!r}")

    @property
    def reference(self):
        return self

    @reference.setter
    def reference(self, head_reference: HeadMock):
        self._copy(head_reference)

    def _copy(self, obj: HeadMock):
        self._repo = obj._repo
        self.commit = obj.commit
        self._branch_name = obj._branch_name

    @property
    def ref(self):
        return next(b for b in self._repo.branches.values() if b.name == self._branch_name)

    @property
    def name(self):
        return self.ref.name


class IndexMock:
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


class GitConfigParserMock:
    def __init__(self):
        pass

    def set_value(self, *args):
        return self

    def release(self):
        pass


def random_sha():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
