import logging
from typing import Set

from automation_tools.jira import JiraAccessor
import robocat.merge_request_actions.follow_up_actions
from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId
from robocat.project_manager import ProjectManager
from robocat.rule.follow_up_rule import FollowUpRule


logger = logging.getLogger(__name__)


class BaseCommand:
    def __init__(self, *args):
        logger.debug(f'Preparing command "{self.verb}" with parameters {args!r}')

    def __str__(self):
        return self.verb

    @classmethod
    def description(cls):
        return f"`{cls.verb}`: {cls.__doc__}"

    def run(self, mr_manager: MergeRequestManager, **_):
        logger.info(f'Executing "{self}" for {mr_manager}')
        mr_manager.add_comment_with_message_id(self._confirmation_message_id)


def robocat_command(
        verb: str,
        confirmation_message_id: MessageId,
        aliases: Set[str] = None,
        process_mr: bool = False):
    def command_class_decorator(cls: BaseCommand) -> BaseCommand:
        cls.verb = verb
        cls.verb_aliases = {verb}
        if aliases:
            cls.verb_aliases.update(aliases)
        cls.should_handle_mr_after_run = process_mr
        cls._confirmation_message_id = confirmation_message_id
        return cls

    return command_class_decorator


@robocat_command(verb='process', confirmation_message_id=MessageId.CommandProcess, process_mr=True)
class ProcessCommand(BaseCommand):
    """Manually initiate processing of the related Merge Request."""
    pass


@robocat_command(
    verb='run-pipeline',
    confirmation_message_id=MessageId.CommandRunPipeline,
    aliases=['run_pipeline'])
class RunPipelineCommand(BaseCommand):
    """Manually run the pipeline for the related Merge Request."""

    def run(self, mr_manager: MergeRequestManager, **kwargs):
        super().run(mr_manager, **kwargs)
        mr_manager.run_user_requested_pipeline()


@robocat_command(
    verb='follow-up',
    confirmation_message_id=MessageId.CommandFollowUp,
    aliases=['follow_up'])
class FollowUpCommand(BaseCommand):
    """Execute follow-up actions for the related Merge Request."""

    def run(
            self,
            mr_manager: MergeRequestManager,
            project_manager: ProjectManager,
            jira: JiraAccessor):
        super().run(mr_manager)
        if mr_manager.data.is_merged:
            follow_up_rule = FollowUpRule(project_manager=project_manager, jira=jira)
            follow_up_result = follow_up_rule.execute(mr_manager)
            logger.debug(f"{mr_manager}: {follow_up_result}")
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
    confirmation_message_id=MessageId.CommandSetDraftFollowUpMode,
    aliases=['draft_follow_up'])
class DraftFollowUpCommand(BaseCommand):
    '''Set the follow-up creation mode to "Draft."'''

    def run(
            self,
            mr_manager: MergeRequestManager,
            project_manager: ProjectManager,
            jira: JiraAccessor):
        super().run(mr_manager)

        # Do nothing if the Merge Request is not merged. The follow-up creation mode is changed
        # by the fact of the presence of the confirming bot comment (the one with
        # 'CommandSetDraftFollowUpMode' id).
        if not mr_manager.data.is_merged:
            return

        # If the Merge Request is already merged, create the follow-up Merge Requests.
        robocat.merge_request_actions.follow_up_actions.create_follow_up_merge_requests(
            jira=jira,
            project_manager=project_manager,
            mr_manager=mr_manager,
            set_draft_flag=True)
        mr_manager.add_comment_with_message_id(MessageId.CommandFollowUp)
