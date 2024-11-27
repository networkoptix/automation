## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from dataclasses import dataclass, field
from typing import Any

from automation_tools.tests.gitlab_constants import (
    USERS, BOT_USERID, BOT_USERNAME, BOT_NAME, BOT_EMAIL)


@dataclass
class UserMock:
    manager: Any = None
    id: int = BOT_USERID
    name: str = BOT_NAME
    username: str = BOT_USERNAME
    email: str = BOT_EMAIL
    state: str = "active"

    @dataclass
    class Impersonationtoken:
        user_manager: Any
        token: dict = field(
            default_factory=lambda: {"user": "", "gitlab": None, "previous_user": None})
        previous_user: str = None

        def create(self, params, **_):
            self.token["user"] = self.user_manager.list(search=params["name"])[0]
            self.token["this"] = self
            return self

        def delete(self):
            if (g := self.token["gitlab"]) is not None:
                g.user = self.token["previous_user"]
                g.token = None

    @property
    def impersonationtokens(self):
        return self.Impersonationtoken(user_manager=self.manager)


@dataclass
class UserManagerMock:
    users: list = field(default_factory=list)

    def __post_init__(self):
        self.users = [
            UserMock(
                manager=self, id=u["id"], username=u["username"], name=u["name"], email=u["email"])
            for u in USERS]

    def list(self, search=None, **_):
        if search is not None:
            return [u for u in self.users if u.username == search]

        return self.users
