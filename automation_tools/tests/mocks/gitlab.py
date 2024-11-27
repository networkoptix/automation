## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from dataclasses import dataclass, field
from typing import Any

from automation_tools.tests.mocks.user import UserMock
from automation_tools.tests.gitlab_constants import (
    BOT_USERID, DEFAULT_PROJECT_ID, BOT_EMAIL, BOT_USERNAME)


@dataclass
class ProjectManagerMock:
    projects: dict = field(default_factory=dict)

    def get(self, project_id, **__):
        return self.projects[project_id]

    def add_mock_project(self, project):
        self.projects[project.id] = project


def default_user():
    return UserMock(manager=None, id=BOT_USERID, name=BOT_USERNAME, email=BOT_EMAIL)


@dataclass
class GitlabMock:
    projects: ProjectManagerMock = field(default_factory=ProjectManagerMock, init=False)
    url: str = ""
    user: UserMock = field(default_factory=default_user)
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
