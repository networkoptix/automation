## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import logging

from robocat.merge_request_manager import MergeRequestManager
from robocat.note import find_last_comment, MessageId

logger = logging.getLogger(__name__)


def add_failed_pipeline_comment_if_needed(mr_manager: MergeRequestManager, job_name: str):
    failed_job_comment = find_last_comment(
        notes=mr_manager.notes(),
        message_id=MessageId.FailedJobNotification,
        condition=lambda n: n.sha == mr_manager.data.sha)

    if failed_job_comment:
        logger.debug(
            f"{mr_manager!s}: do not add the failed job comment because for the current revision "
            f"({mr_manager.data.sha}) there is one already added.")
        return

    mr_manager.add_comment_with_message_id(
        MessageId.FailedJobNotification, message_params={"job_name": job_name})
