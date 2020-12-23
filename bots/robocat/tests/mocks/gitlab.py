from dataclasses import dataclass, field
from typing import Any

from tests.mocks.user import UserMock
from tests.common_constants import BOT_USERNAME, BOT_USERID


@dataclass
class ProjectManagerMock:
    project: Any = None

    def get(self, *_, **__):
        return self.project

    def add_mock_project(self, project):
        self.project = project


@dataclass
class GitlabMock:
    projects: ProjectManagerMock = field(default_factory=ProjectManagerMock, init=False)
    url: str = ""
    user: Any = UserMock(manager=None, id=BOT_USERID, name=BOT_USERNAME)
    token: Any = None

    @property
    def users(self):
        return self.projects.get().users

    def set_private_token(self, token):
        token["gitlab"] = self
        token["previous_user"] = self.user
        self.token = token

    def auth(self):
        if self.token is not None:
            self.user = self.token["user"]
        else:
            self.user = BOT_USERNAME


@dataclass
class GitlabManagerMock:
    gitlab: GitlabMock = field(default_factory=GitlabMock, init=False)
