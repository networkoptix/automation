from dataclasses import dataclass
from jira.resources import dict2resource


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
class Comment:
    body: str


@dataclass
class JiraProject:
    key: str


class RemoteLink:
    def __init__(self, url: str):
        self.object = dict2resource({"url": url})
