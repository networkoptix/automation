from dataclasses import dataclass, field
from typing import Any

from automation_tools.tests.mocks.git_mocks import BOT_EMAIL, BOT_USERNAME
from tests.mocks.user import UserMock
from tests.robocat_constants import BOT_USERID, DEFAULT_PROJECT_ID


@dataclass
class ProjectManagerMock:
    projects: dict = field(default_factory=dict)

    def get(self, project_id, **__):
        return self.projects[project_id]

    def add_mock_project(self, project):
        self.projects[project.id] = project


@dataclass
class GitlabMock:
    projects: ProjectManagerMock = field(default_factory=ProjectManagerMock, init=False)
    url: str = ""
    user: Any = UserMock(manager=None, id=BOT_USERID, name=BOT_USERNAME, email=BOT_EMAIL)
    token: Any = None

    @property
    def users(self):
        return self.projects.get(DEFAULT_PROJECT_ID).users

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
