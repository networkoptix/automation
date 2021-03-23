from __future__ import annotations
import datetime
import logging

import gitlab

from robocat.pipeline import Pipeline
import robocat.project

logger = logging.getLogger(__name__)


class Gitlab:
    def __init__(self, _raw_gitlab_object: gitlab.Gitlab, impersonation_token=None):
        self._raw_gitlab_object = _raw_gitlab_object
        self._impersonation_token = impersonation_token

    def get_gitlab_object_for_user(self, user_name: str):
        try:
            effective_user = self._raw_gitlab_object.users.list(search=user_name)[0]
        except IndexError as e:
            raise RuntimeError(f"Invalid username: {user_name}") from e

        tomorrow_date_string = str(datetime.date.today() + datetime.timedelta(days=1))
        impersonation_token = effective_user.impersonationtokens.create(
            {"name": user_name, "scopes": ["api"], "expires_at": tomorrow_date_string}, lazy=True)
        user_raw_gitlab = gitlab.Gitlab(
            self._raw_gitlab_object.url, private_token=impersonation_token.token)
        user_raw_gitlab.auth()  # Needed to initialize "user" field of the user_gitlab object.

        return Gitlab(user_raw_gitlab, impersonation_token)

    def create_detached_pipeline(self, project_id: int, mr_id: int) -> Gitlab:
        url = f"/projects/{project_id}/merge_requests/{mr_id}/pipelines"
        self._raw_gitlab_object.http_post(url)
        return self

    def get_project(self, project_id: int, lazy: bool = True) -> robocat.project.Project:
        return robocat.project.Project(self._raw_gitlab_object.projects.get(project_id, lazy=lazy))

    def get_pipeline(self, project_id: int, pipeline_id: int, lazy: bool = True) -> Pipeline:
        raw_project_object = self._raw_gitlab_object.projects.get(project_id, lazy=lazy)
        return Pipeline(raw_project_object.pipelines.get(pipeline_id))

    @property
    def user_id(self):
        return self._raw_gitlab_object.user.id
