import enum
import logging
from typing import List

import gitlab.v4.objects

logger = logging.getLogger(__name__)


class PipelineStatus(enum.Enum):
    skipped = enum.auto()
    running = enum.auto()
    succeeded = enum.auto()
    failed = enum.auto()


class RunPipelineReason(enum.Enum):
    """Reasons why pipeline run requested. The value is a description message"""
    no_pipelines_before = "making initial CI check"
    mr_rebased = "checking if rebase fixed previous fails"
    mr_updated = "checking new MR state"
    requested_by_user = "CI check requested by the user"


class JobStatus(enum.Enum):
    running = enum.auto()
    succeeded = enum.auto()
    failed = enum.auto()
    other = enum.auto()


class Job:
    def __init__(self, raw_job: gitlab.v4.objects):
        self.name = raw_job.name
        self.status = self._job_status_from_string(raw_job.status)

    @staticmethod
    def _job_status_from_string(raw_status: str) -> JobStatus:
        if raw_status == "success":
            return JobStatus.succeeded
        if raw_status == "running":
            return JobStatus.running
        if raw_status == "failed":
            return JobStatus.failed
        return JobStatus.other


class PlayPipelineError(RuntimeError):
    pass


class Pipeline:
    def __init__(self, pipeline):
        self._gitlab_pipeline = pipeline

    @property
    def id(self):
        return self._gitlab_pipeline.id

    @property
    def web_url(self):
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
        if status in ["canceled", "skipped", "created", "manual"]:
            return PipelineStatus.skipped

        if status in ["waiting_for_resource", "preparing", "pending", "running", "scheduled"]:
            return PipelineStatus.running

        if status == "success":
            return PipelineStatus.succeeded

        assert status == "failed", f"Unexpected status {status}"
        return PipelineStatus.failed

    def jobs(self) -> List[Job]:
        return [Job(j) for j in self._get_all_jobs()]

    def play(self):
        if self._gitlab_pipeline.status != "manual":
            raise PlayPipelineError(
                f"Wrong pipeline status: {self._gitlab_pipeline.status!r}. Only manual pipelines "
                "could be played")

        logger.info(f"{self}: Playing...")

        project = self._get_project()
        for job in self._get_all_jobs():
            if job.status == "manual":
                project.jobs.get(job.id, lazy=True).play()

    def stop(self):
        logger.info(f"{self}: Stopping...")
        self._gitlab_pipeline.cancel()

    def _get_project(self):
        project_id = self._gitlab_pipeline.project_id
        return self._gitlab_pipeline.manager.gitlab.projects.get(project_id, lazy=True)

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
