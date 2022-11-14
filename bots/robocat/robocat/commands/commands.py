import logging

from automation_tools.jira import JiraAccessor
import robocat.merge_request_actions.followup_actions
from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId
from robocat.project_manager import ProjectManager
from robocat.rule.followup_rule import FollowupRule


logger = logging.getLogger(__name__)


class BaseCommand:
    def __init__(self, *args):
        logger.debug(f'Preparing command "{self.verb}" with parameters {args!r}')

    def __str__(self):
        return self.verb

    def run(self, mr_manager: MergeRequestManager, **_):
        logger.info(f'Executing "{self}" for {mr_manager}')
        mr_manager.add_comment_with_message_id(self._confirmation_message_id)


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

    def run(self, mr_manager: MergeRequestManager, **kwargs):
        super().run(mr_manager, **kwargs)
        mr_manager.run_user_requested_pipeline()


@robocat_command(verb='follow-up', confirmation_message_id=MessageId.CommandFollowup)
class FollowupCommand(BaseCommand):
    """This command is used for executing follow-up actions upon the related Merge Request"""

    def run(
            self,
            mr_manager: MergeRequestManager,
            project_manager: ProjectManager,
            jira: JiraAccessor):
        super().run(mr_manager)
        if mr_manager.data.is_merged:
            followup_rule = FollowupRule(project_manager=project_manager, jira=jira)
            followup_result = followup_rule.execute(mr_manager)
            logger.debug(f"{mr_manager}: {followup_result}")
        else:
            mr_manager.add_comment_with_message_id(
                MessageId.CommandNotExecuted,
                message_params={
                    'command': self.verb,
                    'explanation': (
                        'Refusing to execute follow-up actions upon unmerged Merge Request'),
                    })


@robocat_command(
    verb='draft-follow-up',
    confirmation_message_id=MessageId.CommandSetDraftFollowupMode)
class DraftFollowupCommand(BaseCommand):
    '''This command is used for setting follow-up creation mode to "Draft"'''

    def run(
            self,
            mr_manager: MergeRequestManager,
            project_manager: ProjectManager,
            jira: JiraAccessor):
        super().run(mr_manager)

        # Do nothing if the Merge Request is not merged. The follow-up creation mode is changed
        # by the fact of the presence of the confirming bot comment (the one with
        # 'CommandSetDraftFollowupMode' id).
        if not mr_manager.data.is_merged:
            return

        # If the Merge Request is already merged, create the follow-up Merge Requests.
        robocat.merge_request_actions.followup_actions.create_followup_merge_requests(
            jira=jira,
            project_manager=project_manager,
            mr_manager=mr_manager,
            set_draft_flag=True)
        mr_manager.add_comment_with_message_id(MessageId.CommandFollowup)
