from dataclasses import dataclass, field
from typing import Any

from tests.common_constants import USERS, BOT_USERNAME, BOT_USERID, BOT_NAME


@dataclass
class UserMock:
    manager: Any = None
    id: int = BOT_USERID
    name: str = BOT_NAME
    username: str = BOT_USERNAME

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
        self.users = [UserMock(manager=self, id=u["id"], name=u["username"]) for u in USERS]

    def list(self, search=None, **_):
        if search is not None:
            return [u for u in self.users if u.name == search]

        return self.users
