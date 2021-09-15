from typing import Dict, List, Any
from jira.resources import dict2resource

from automation_tools.tests.mocks.resources import Comment, JiraProject


class JiraIssue:
    def __init__(self, key: str, fields: Dict[str, Any], comments: List[Comment]):
        self.key = key
        self.fields = dict2resource(fields)
        project_key, _, __ = key.partition("-")
        self.fields.project = JiraProject(project_key)
        self.fields.comment = dict2resource({"comments": comments})

    def update(self, fields: dict = None):
        if not fields:
            return
        for field, value in fields.items():
            self.fields.field = value
