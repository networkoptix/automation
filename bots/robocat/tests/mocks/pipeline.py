from dataclasses import dataclass, field
from typing import Any

from tests.mocks.gitlab import GitlabManagerMock


@dataclass
class JobMock:
    pipeline: Any
    id: int = 0
    status: str = "manual"

    def play(self):
        self.status = "running"
        self.pipeline.status = "running"


@dataclass
class JobsManagerMock:
    jobs_list: list = field(default_factory=list)
    pipeline_filter: Any = None

    def list(self):
        if self.pipeline_filter is None:
            return self.jobs_list
        return [j for j in self.jobs_list if j.pipeline == self.pipeline_filter]

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

    manager: GitlabManagerMock = field(default_factory=GitlabManagerMock, init=False)

    def __post_init__(self):
        self.manager.gitlab = self.project.manager.gitlab
        self.project.jobs.add_mock_job(JobMock(pipeline=self))

    @property
    def project_id(self):
        return self.project.id

    @property
    def jobs(self):
        # Create jobs manager object copy with pipeline filter.
        pipeline_jobs = JobsManagerMock(jobs_list=self.project.jobs.jobs_list)
        pipeline_jobs.pipeline_filter = self
        return pipeline_jobs


@dataclass
class PipelineManagerMock:
    pipelines: dict = field(default_factory=dict, init=False)

    def get(self, p_id, **_):
        return self.pipelines[p_id]

    def list(self, **_):
        return self.pipelines.values()

    def add_mock_pipeline(self, pipeline: PipelineMock):
        self.pipelines[pipeline.id] = pipeline
