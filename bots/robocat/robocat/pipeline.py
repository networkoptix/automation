## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import enum
import logging
import re
import sys
from dataclasses import dataclass
from functools import cache, singledispatchmethod
from typing import Optional

from gitlab import GitlabJobPlayError
from gitlab.v4.objects import ProjectPipelineJob

if "pytest" in sys.modules:
    from automation_tools.tests.mocks.pipeline import JobMock

IGNORED_JOB_SUFFIX = 'no-bot-start'

logger = logging.getLogger(__name__)


class PipelineStatus(enum.Enum):
    skipped = enum.auto()
    running = enum.auto()
    succeeded = enum.auto()
    failed = enum.auto()


@dataclass
class PipelineLocation:
    pipeline_id: str
    project_id: str


class RunPipelineReason(enum.Enum):
    """Reasons why pipeline run requested. The value is a description message"""
    no_pipelines_before = "making initial CI check"
    mr_rebased = "checking if rebase fixed previous fails"
    mr_updated = "checking new MR state"
    requested_by_user = "CI check requested by the user"
    needed_by_project_settings = "Pipeline must pass before merge"


class JobStatus(enum.Enum):
    running = enum.auto()
    succeeded = enum.auto()
    failed = enum.auto()
    manual = enum.auto()
    other = enum.auto()


class Job:
    @singledispatchmethod
    def __init__(self, *args):
        assert False, (
            f"Unsupported constructor signature: Job({', '.join(str(type(a)) for a in args)})")

    # @__init__.register decorator is unable to handle Union type hint, so we use two identical
    # constructors with different parameter types, delegating actual job to another method, instead
    # of the single constructor with the parameter of type Union[<type1>, <type2>].
    @__init__.register
    def _from_job_object(self, source: ProjectPipelineJob):
        return self._from_job_like_object(source)

    if "pytest" in sys.modules:
        @__init__.register
        def _from_job_mock_object(self, source: "JobMock"):
            return self._from_job_like_object(source)

    def _from_job_like_object(self, source):
        self._status = source.status
        self._name = source.name
        self._id = source.id
        self._stage = source.stage
        self._allow_failure = source.allow_failure
        self._pipeline_id = source.pipeline["id"]
        self._project_id = source.project_id

    @__init__.register
    def _from_job_event(self, source: dict):
        self._status = source["status"]
        self._name = source["name"]
        self._id = source["job_id"]
        self._allow_failure = source["allow_failure"]
        self._stage = source["stage"]
        self._pipeline_id = source["pipeline_id"]
        self._project_id = source["project_id"]

    @property
    def name(self) -> str:
        return self._name

    @property
    def id(self) -> int:
        return int(self._id)

    @property
    def allow_failure(self) -> bool:
        return self._allow_failure

    @property
    def pipeline_id(self) -> bool:
        return self._pipeline_id

    @property
    def stage(self) -> bool:
        return self._stage

    @property
    def status(self) -> JobStatus:
        raw_status = self._status
        if raw_status == "success":
            return JobStatus.succeeded
        if raw_status == "running":
            return JobStatus.running
        if raw_status == "failed":
            return JobStatus.failed
        if raw_status == "manual":
            return JobStatus.manual
        return JobStatus.other

    @property
    def pipeline_location(self) -> PipelineLocation:
        return PipelineLocation(pipeline_id=self.pipeline_id, project_id=self._project_id)

    def is_playable(self) -> bool:
        return self.status == JobStatus.manual and not self.name.endswith(f':{IGNORED_JOB_SUFFIX}')


class PlayPipelineError(RuntimeError):
    pass


class Pipeline:
    _MERGE_REQUEST_REF_RE = re.compile(r"^refs/merge-requests/(\d+)/head$")

    def __init__(self, pipeline):
        self._gitlab_pipeline = pipeline

    @property
    def id(self) -> str:
        return self._gitlab_pipeline.id

    @property
    def mr_id(self) -> Optional[int]:
        ref_match = self._MERGE_REQUEST_REF_RE.match(self._gitlab_pipeline.ref)
        if ref_match:
            return int(ref_match[1])
        return None

    @property
    def web_url(self) -> str:
        return self._gitlab_pipeline.web_url

    def __str__(self):
        return f"Pipeline!{self.id}"

    @property
    def status(self) -> PipelineStatus:
        return self.translate_status(self._gitlab_pipeline.status)

    @property
    def is_manual(self) -> bool:
        return self._gitlab_pipeline.status == "manual"

    @property
    def sha(self) -> str:
        return self._gitlab_pipeline.sha

    @staticmethod
    def translate_status(status: str) -> PipelineStatus:
        if status in ["canceled", "canceling", "skipped", "created", "manual"]:
            return PipelineStatus.skipped

        if status in ["waiting_for_resource", "preparing", "pending", "running", "scheduled"]:
            return PipelineStatus.running

        if status == "success":
            return PipelineStatus.succeeded

        assert status == "failed", f"Unexpected status {status}"
        return PipelineStatus.failed

    def jobs(self) -> list[Job]:
        return [Job(j) for j in self._get_all_jobs()]

    def is_playable(self) -> bool:
        return self._gitlab_pipeline.status == "manual"

    def play(self):
        if not self.is_playable():
            raise PlayPipelineError(
                f"Wrong pipeline status: {self._gitlab_pipeline.status!r}. Only manual pipelines "
                "could be played")

        logger.info(f"{self}: Playing...")
        for job in (j for j in self.jobs() if j.is_playable()):
            self.play_job(job)

    def stop(self):
        logger.info(f"{self}: Stopping...")
        self._gitlab_pipeline.cancel()

    def _get_all_jobs(self):
        result = []
        current_page = 1

        while True:
            jobs_on_current_page = list(
                self._gitlab_pipeline.jobs.list(per_page=100, page=current_page))
            if not jobs_on_current_page:
                break
            result += jobs_on_current_page
            current_page += 1

        return result

    def get_job_by_name(self, name: str) -> Optional[Job]:
        return next(iter(j for j in self.jobs() if j.name == name), None)

    def play_job(self, job: Job):
        project = self._get_project()
        try:
            logger.debug(f"{self}: Starting job {job.name!r} ({job.id})")
            project.jobs.get(job.id, lazy=True).play()
        except GitlabJobPlayError:
            logger.info(f"{self}: Job {job.name!r} ({job.id}) can not be played at the moment")

    @cache
    def _get_project(self):
        project_id = self._gitlab_pipeline.project_id
        return self._gitlab_pipeline.manager.gitlab.projects.get(project_id)

    def is_stage_completed(self, stage_name: str) -> bool:
        return all(j.status in [JobStatus.failed, JobStatus.succeeded]
                   for j in self.jobs() if j.stage == stage_name)
