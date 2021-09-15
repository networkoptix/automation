from dataclasses import dataclass, field
from typing import Any
from gitlab import GitlabCherryPickError


@dataclass
class CommitMock:
    sha: str
    message: str
    diffs: list = field(default_factory=list)
    files: list = field(default_factory=list)
    project: Any = None

    @property
    def id(self):
        return self.sha

    def diff(self):
        return self.diffs

    def cherry_pick(self, branch):
        if self.sha in self.project.branches.mock_conflicts.get(branch, []):
            raise GitlabCherryPickError
        self.project.add_mock_commit(branch, self.sha, self.message)


@dataclass
class CommitsManagerMock:
    commits: dict = field(default_factory=dict, init=False)
    project: Any = None

    def get(self, sha, **_):
        return self.commits[sha]

    def list(self, **_):
        return self.commits.values()

    def add_mock_commit(self, commit: CommitMock):
        commit.project = self.project
        self.commits[commit.sha] = commit
