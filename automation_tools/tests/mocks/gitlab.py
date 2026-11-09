## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import re
from dataclasses import dataclass, field
from typing import Any

from automation_tools.tests.gitlab_constants import (
    BOT_EMAIL,
    BOT_USERID,
    BOT_USERNAME,
    DEFAULT_PROJECT_ID,
)
from automation_tools.tests.mocks.user import UserMock


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

    def http_put(self, path: str, post_data: dict[str, Any] | None = None, **_) -> dict[str, Any]:
        """Merge a mock MR as GitLab does: its merge() gets the fields of the request body."""
        match = re.fullmatch(r"/projects/(\d+)/merge_requests/(\d+)/merge", path)
        assert match, f"The mock does not know PUT {path}"
        merge_request = self.projects.get(int(match[1])).mergerequests.get(int(match[2]))
        merge_request.merge(**(post_data or {}))
        return {"state": merge_request.state, "squash_commit_sha": merge_request.squash_commit_sha}


@dataclass
class GitlabManagerMock:
    gitlab: GitlabMock = field(default_factory=GitlabMock, init=False)
