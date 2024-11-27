## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import datetime
from dataclasses import dataclass, field
from typing import Any, Optional

from automation_tools.tests.mocks.gitlab import GitlabManagerMock


@dataclass
class JobMock:
    pipeline_ref: "PipelineMock"
    name: str = ""
    id: int = 0
    status: str = "manual"
    stage: str = "default"
    allow_failure: bool = False
    pipeline: dict[str, str] = field(init=False)

    manager: GitlabManagerMock = field(default_factory=GitlabManagerMock, init=False)

    def __post_init__(self):
        self.pipeline = {"id": self.pipeline_ref.id, "status": self.pipeline_ref.status}
        self.manager.gitlab = self.pipeline_ref.project.manager.gitlab

    @property
    def project_id(self):
        return self.pipeline_ref.project_id

    def play(self):
        self.status = "running"
        self.pipeline["status"] = self.pipeline_ref.status = "running"


@dataclass
class JobsManagerMock:
    jobs_list: list = field(default_factory=list)
    pipeline_filter: "PipelineMock" = None

    def list(self, per_page: int = 20, page: int = 1):  # pylint: disable=unused-argument
        if page > 1:
            return []
        if self.pipeline_filter is None:
            return self.jobs_list
        return [j for j in self.jobs_list if j.pipeline_ref == self.pipeline_filter]

    def get(self, j_id, **_):
        jobs_list = self.list()
        return next(j for j in jobs_list if j.id == j_id)

    def add_mock_job(self, job: JobMock):
        job.id = len(self.jobs_list)
        self.jobs_list.append(job)


@dataclass
class PipelineMock:
    project: Any
    id: int
    sha: str
    status: str
    web_url: str = ""
    created_at: Optional[str] = None
    mr: Optional["MergeRequestMock"] = None

    manager: GitlabManagerMock = field(default_factory=GitlabManagerMock, init=False)

    def __post_init__(self):
        self.manager.gitlab = self.project.manager.gitlab
        self.project.jobs.add_mock_job(JobMock(pipeline_ref=self))
        if self.created_at is None:
            self.created_at = datetime.datetime.fromtimestamp(self.id).isoformat()

    @property
    def project_id(self):
        return self.project.id

    @property
    def jobs(self):
        # Create jobs manager object copy with pipeline_ref filter.
        pipeline_jobs = JobsManagerMock(jobs_list=self.project.jobs.jobs_list)
        pipeline_jobs.pipeline_filter = self
        return pipeline_jobs

    def cancel(self):
        pass

    @property
    def ref(self) -> str:
        return f"refs/merge-requests/{self.mr.iid}/head" if self.mr else ""


@dataclass
class PipelineManagerMock:
    pipelines: dict = field(default_factory=dict, init=False)

    def get(self, p_id, **_):
        return self.pipelines[p_id]

    def list(self, **_):
        return list(self.pipelines.values())

    def add_mock_pipeline(self, pipeline: PipelineMock):
        self.pipelines[pipeline.id] = pipeline
