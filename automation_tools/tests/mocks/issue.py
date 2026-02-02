## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from typing import Any, Optional
from jira.resources import dict2resource

from automation_tools.tests.mocks.resources import Comment, JiraProject


class JiraIssue:
    def __init__(
            self,
            key: str,
            fields: dict[str, Any],
            comments: list[Comment],
            assignee: Optional[str] = ""):
        self.key = key
        self.fields = dict2resource(fields)
        project_key, _, __ = key.partition("-")
        self.fields.project = JiraProject(project_key)
        self.fields.comment = dict2resource({"comments": comments})
        if assignee is None:
            self.fields.assignee = None
        else:
            self.fields.assignee = dict2resource({
                "displayName": assignee, "emailAddress": "", "accountId": 0})

    def update(self, fields: dict = None):
        if not fields:
            return
        for field, value in fields.items():
            self.fields.field = value
