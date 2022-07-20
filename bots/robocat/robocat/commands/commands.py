import logging
from typing import Any

from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId


logger = logging.getLogger(__name__)


class BaseCommand:
    def __init__(self, *args):
        logger.debug(f'Preparing command "{self.verb}" with parameters {args!r}')

    def __str__(self):
        return self.verb

    def run(self, mr_manager: MergeRequestManager):
        logger.info(f'Executing "{self}" for {mr_manager}')
        mr_manager.add_command_confirmation_comment(self._confirmation_message_id)


def robocat_command(verb: str, confirmation_message_id: MessageId, process_mr: bool = False):
    def command_class_decorator(cls: BaseCommand) -> BaseCommand:
        cls.verb = verb
        cls.should_handle_mr_after_run = process_mr
        cls._confirmation_message_id = confirmation_message_id
        return cls

    return command_class_decorator


@robocat_command(verb='process', confirmation_message_id=MessageId.CommandProcess, process_mr=True)
class ProcessCommand(BaseCommand):
    """This command is used for manual initiating of processing the related Merge Request"""
    pass


@robocat_command(verb='run_pipeline', confirmation_message_id=MessageId.CommandRunPipeline)
class RunPipelineCommand(BaseCommand):
    """This command is used for manual running the pipeline for the related Merge Request"""

    def run(self, mr_manager: MergeRequestManager):
        super().run(mr_manager)
        mr_manager.run_user_requested_pipeline()
