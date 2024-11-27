## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from __future__ import annotations
import datetime
import logging

import gitlab

import automation_tools.utils
from robocat.pipeline import Pipeline, PipelineLocation
import robocat.project

logger = logging.getLogger(__name__)


class Gitlab:
    def __init__(self, _raw_gitlab_object: gitlab.Gitlab):
        self._raw_gitlab_object = _raw_gitlab_object

    def get_gitlab_object_for_user(self, user_name: str):
        effective_user = self._get_user_info_by_username(user_name)
        tomorrow_date_string = str(datetime.date.today() + datetime.timedelta(days=1))
        impersonation_token = effective_user.impersonationtokens.create(
            {"name": user_name, "scopes": ["api"], "expires_at": tomorrow_date_string}, lazy=True)
        user_raw_gitlab = gitlab.Gitlab(
            self._raw_gitlab_object.url, private_token=impersonation_token.token)
        user_raw_gitlab.auth()  # Needed to initialize "user" field of the user_gitlab object.

        return Gitlab(user_raw_gitlab)

    def _get_user_info_by_username(self, user_name: str):
        try:
            users = self._raw_gitlab_object.users.list(search=user_name)
            if len(users) > 1:
                logger.debug(f'More than one user with username "{user_name}" is found.')
            return next(u for u in users if u.state == "active")
        except StopIteration as e:
            raise RuntimeError(f'Active user with username "{user_name}" is not found') from e

    def create_detached_pipeline(self, project_id: int, mr_id: int) -> Gitlab:
        url = f"/projects/{project_id}/merge_requests/{mr_id}/pipelines"
        self._raw_gitlab_object.http_post(url)
        return self

    def get_project(self, project_id: int, lazy: bool = True) -> robocat.project.Project:
        return robocat.project.Project(self._raw_gitlab_object.projects.get(project_id, lazy=lazy))

    def get_pipeline(self, pipeline_location: PipelineLocation, lazy: bool = True) -> Pipeline:
        raw_project_object = self._raw_gitlab_object.projects.get(
            pipeline_location.project_id, lazy=lazy)
        return Pipeline(raw_project_object.pipelines.get(pipeline_location.pipeline_id))

    @property
    def user_id(self):
        return self._raw_gitlab_object.user.id

    def get_git_user_info_by_username(self, user_name: str) -> automation_tools.utils.User:
        user_info = self._get_user_info_by_username(user_name)
        return automation_tools.utils.User(
            name=user_info.name, username=user_info.username, email=user_info.email)
