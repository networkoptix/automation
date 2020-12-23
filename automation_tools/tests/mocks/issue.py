from typing import Dict, List, Any
from jira.resources import dict2resource

from automation_tools.tests.mocks.resources import Comment


class JiraIssue:
    def __init__(self, key: str, fields: Dict[str, Any], comments: List[Comment]):
        self.key = key
        self.fields = dict2resource(fields)
        self.fields.comment = dict2resource({"comments": comments})
