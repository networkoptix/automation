import logging

from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId

logger = logging.getLogger(__name__)


def add_failed_pipeline_comment_if_needed(mr_manager: MergeRequestManager, job_name: str):
    has_failed_jobs_for_current_sha = any(
        n for n in mr_manager.notes()
        if n.message_id == MessageId.FailedJobNotification and n.sha == mr_manager.data.sha)

    if has_failed_jobs_for_current_sha:
        logger.debug(
            f"{mr_manager!s}: do not add the failed job comment because for the current revision "
            f"({mr_manager.data.sha}) there is one already added.")
        return

    mr_manager.add_comment_with_message_id(
        MessageId.FailedJobNotification, message_params={"job_name": job_name})
