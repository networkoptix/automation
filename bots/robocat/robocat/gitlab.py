from __future__ import annotations

import logging
import gitlab

from robocat.pipeline import Pipeline
from robocat.project import Project

logger = logging.getLogger(__name__)


class Gitlab:
    def __init__(self, _raw_gitlab_object: gitlab.Gitlab):
        self._raw_gitlab_object = _raw_gitlab_object

    def create_detached_pipeline(self, project_id: int, mr_id: int) -> Gitlab:
        url = f"/projects/{project_id}/merge_requests/{mr_id}/pipelines"
        self._raw_gitlab_object.http_post(url)
        return self

    def get_project(self, project_id: int) -> Project:
        return Project(self._raw_gitlab_object.projects.get(project_id, lazy=True))

    def get_pipeline(self, project_id: int, pipeline_id: int) -> Pipeline:
        raw_project_object = self._raw_gitlab_object.projects.get(project_id, lazy=True)
        return Pipeline(raw_project_object.pipelines.get(pipeline_id))
