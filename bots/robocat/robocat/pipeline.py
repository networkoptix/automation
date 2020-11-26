import enum
import logging
import gitlab

logger = logging.getLogger(__name__)


class PipelineStatus(enum.Enum):
    skipped = enum.auto()
    running = enum.auto()
    succeded = enum.auto()
    failed = enum.auto()


class RunPipelineReason(enum.Enum):
    """Reasons why pipeline run requested. The value is a description message"""
    no_pipelines_before = "making initial CI check"
    mr_rebased = "checking if rebase fixed previous fails"
    mr_updated = "checking new MR state"
    requested_by_user = "CI check requested by the user"


class PlayPipelineError(RuntimeError):
    pass


class Pipeline:
    def __init__(self, pipeline, dry_run=False):
        self._gitlab_pipeline = pipeline
        self._dry_run = dry_run

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
            return PipelineStatus.succeded

        assert status == "failed", f"Unexpected status {status}"
        return PipelineStatus.failed

    def play(self):
        if self._gitlab_pipeline.status != "manual":
            raise PlayPipelineError("Only manual pipelines could be played")

        logger.info(f"{self}: Playing...")
        if not self._dry_run:
            project = self._get_project()
            for job in self._gitlab_pipeline.jobs.list():
                if job.status == "manual":
                    project.jobs.get(job.id, lazy=True).play()

    def _get_project(self):
        project_id = self._gitlab_pipeline.project_id
        return self._gitlab_pipeline.manager.gitlab.projects.get(project_id, lazy=True)
