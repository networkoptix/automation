from dataclasses import dataclass, field
from typing import Any


@dataclass
class CommitMock:
    sha: str
    message: str
    diffs: list = field(default_factory=list)
    files: list = field(default_factory=list)

    def diff(self):
        return self.diffs


@dataclass
class CommitsManagerMock:
    commits: dict = field(default_factory=dict, init=False)

    def get(self, sha, **_):
        return self.commits[sha]

    def list(self, **_):
        return self.commits.values()

    def mock_add_commit(self, commit: CommitMock):
        self.commits[commit.sha] = commit
