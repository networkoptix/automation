## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import gitlab
import pytest
from gitlab.v4.objects import CurrentUser, CurrentUserManager
from robocat.gitlab import logged_in_user


class TestLoggedInUser:
    """The token owner that python-gitlab sets in auth()."""

    def test_returns_user_set_by_auth(self, monkeypatch):
        """After auth(), the helper returns the user that python-gitlab read."""
        raw_gitlab = gitlab.Gitlab("https://gitlab.example.com", private_token="token")
        user = CurrentUser(CurrentUserManager(raw_gitlab), {"id": 7, "username": "robocat"})
        monkeypatch.setattr(CurrentUserManager, "get", lambda *_, **__: user)  # No server call.

        raw_gitlab.auth()

        assert logged_in_user(raw_gitlab) is user
        assert logged_in_user(raw_gitlab).id == 7

    def test_raises_without_auth(self):
        """Without auth(), python-gitlab has no user: the helper raises a clear error."""
        raw_gitlab = gitlab.Gitlab("https://gitlab.example.com", private_token="token")

        with pytest.raises(RuntimeError, match=r"auth\(\) was not called"):
            logged_in_user(raw_gitlab)
