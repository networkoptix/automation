## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import logging
from typing import Set

from automation_tools.jira import JiraAccessor
from robocat.config import Config
from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId
from robocat.project_manager import ProjectManager
import robocat.comments
import robocat.merge_request_actions.follow_up_actions


logger = logging.getLogger(__name__)


class BaseCommand:
    def __init__(self, *args):
        self.command = args[0]
        logger.debug(f'Preparing command "{self.verb}" with parameters {args!r}')

    def __str__(self):
        return self.verb

    @classmethod
    def description(cls):
        return f"`{cls.verb}`: {cls.__doc__}"

    def run(self, mr_manager: MergeRequestManager, **_):
        logger.info(f'Executing "{self}" for {mr_manager}')
        mr_manager.add_comment(robocat.comments.Message(id=self._confirmation_message_id))


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
            config: Config,
            project_manager: ProjectManager,
            jira: JiraAccessor):
        super().run(mr_manager)
        if mr_manager.data.is_merged:
            robocat.merge_request_actions.follow_up_actions.create_follow_up_merge_requests(
                jira=jira,
                project_manager=project_manager,
                mr_manager=mr_manager,
                set_draft_flag=False,
                approve_by_robocat=config.repo.need_code_owner_approval,
                default_branch_project_mapping=config.jira.project_mapping)
        else:
            mr_manager.add_comment(robocat.comments.Message(
                id=MessageId.CommandNotExecuted,
                params={
                    'command': self.command,
                    'explanation': (
                        'Refusing to execute follow-up actions upon unmerged Merge Request'),
                }))


@robocat_command(
    verb='draft-follow-up',
    confirmation_message_id=MessageId.CommandSetDraftFollowUpMode,
    aliases=['draft_follow_up'])
class DraftFollowUpCommand(BaseCommand):
    '''Set the follow-up creation mode to "Draft".'''

    def run(
            self,
            mr_manager: MergeRequestManager,
            config: Config,
            project_manager: ProjectManager,
            jira: JiraAccessor):
        super().run(mr_manager)

        # Do nothing if the Merge Request is not merged. The follow-up creation mode is changed
        # by the fact of the presence of the confirming bot comment (the one with
        # 'CommandSetDraftFollowUpMode' id).
        if not mr_manager.data.is_merged:
            return

        # If the Merge Request is already merged, create the follow-up Merge Requests.
        mr_manager.add_comment(robocat.comments.Message(id=MessageId.CommandFollowUp))
        robocat.merge_request_actions.follow_up_actions.create_follow_up_merge_requests(
            jira=jira,
            project_manager=project_manager,
            mr_manager=mr_manager,
            set_draft_flag=True,
            approve_by_robocat=config.repo.need_code_owner_approval,
            default_branch_project_mapping=config.jira.project_mapping)


@robocat_command(verb='__unknown__', confirmation_message_id=MessageId.CommandUnknown)
class UnknownCommand(BaseCommand):
    '''Inform the user that the command is not recognized'''

    def run(self, mr_manager: MergeRequestManager, **_):
        logger.info(f'Executing "{self}" for {mr_manager}')
        mr_manager.add_comment(robocat.comments.Message(
            id=self._confirmation_message_id,
            params={'command': self.command}))
