## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from dataclasses import dataclass
from typing import Optional

from jira.resources import dict2resource

from automation_tools.tests.gitlab_constants import DEFAULT_USER


@dataclass
class Status:
    name: str


@dataclass
class Version:
    name: str
    description: str
    archived: bool = False


@dataclass
class IssueType:
    name: str


@dataclass
class User:
    displayName: str
    accountId: str
    emailAddress: str


@dataclass
class Comment:
    body: str
    author: Optional[User] = None

    def __post_init__(self):
        if not self.author:
            self.author = User(
                accountId=DEFAULT_USER['id'],
                displayName=DEFAULT_USER['name'],
                emailAddress=DEFAULT_USER['email'])


@dataclass
class JiraProject:
    key: str


@dataclass
class Resolution:
    name: str


class RemoteLink:
    def __init__(self, url: str):
        self.object = dict2resource({"url": url})
