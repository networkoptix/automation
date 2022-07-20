import enum
import logging
import queue
import requests
import threading
import time
from typing import TypedDict

import git
import gitlab

import automation_tools.utils
import automation_tools.bot_info
from automation_tools.jira import JiraAccessor, JiraError
import automation_tools.git
import robocat.commands.parser
from robocat.project_manager import ProjectManager
from robocat.merge_request_manager import MergeRequestManager
from robocat.pipeline import PlayPipelineError, Pipeline, PipelineStatus
from robocat.rule.commit_message_check_rule import CommitMessageCheckRule
from robocat.rule.nx_submodule_check_rule import NxSubmoduleCheckRule
from robocat.rule.essential_rule import EssentialRule
from robocat.rule.open_source_check_rule import OpenSourceCheckRule
from robocat.rule.followup_rule import FollowupRule
from robocat.rule.workflow_check_rule import WorkflowCheckRule
from robocat.rule.process_related_projects_issues import ProcessRelatedProjectIssuesRule

logger = logging.getLogger(__name__)

MR_POLL_RATE_S = 30


class GitlabEventType(enum.Enum):
    merge_request = enum.auto()
    pipeline = enum.auto()
    comment = enum.auto()


class GitlabEventData(TypedDict):
    mr_id: str
    event_type: GitlabEventType
    added_comment: str
    raw_pipeline_status: str


class Bot(threading.Thread):
    def __init__(self, config, project_id: int, mr_queue: queue.SimpleQueue):
        super().__init__()

        raw_gitlab = gitlab.Gitlab.from_config("nx_gitlab")
        raw_gitlab.auth()
        gitlab_user_info = raw_gitlab.users.get(raw_gitlab.user.id)
        self._username = gitlab_user_info.username
        committer = automation_tools.utils.User(
            email=gitlab_user_info.email, name=gitlab_user_info.name,
            username=gitlab_user_info.username)
        self._repo = automation_tools.git.Repo(**config["repo"], committer=committer)

        self._project_manager = ProjectManager(
            gitlab_project=raw_gitlab.projects.get(project_id),
            current_user=self._username,
            repo=self._repo)

        jira = JiraAccessor(**config["jira"])

        self._rule_nx_submodules_check = NxSubmoduleCheckRule(
            self._project_manager,
            **config["nx_submodule_check_rule"])
        # For now, use the same approval rules for OpenSourceCheckRule and CommitMessageCheckRule.
        self._rule_commit_message = CommitMessageCheckRule(
            approve_rules=config["open_source_check_rule"]["approve_rules"])
        self._rule_essential = EssentialRule(project_keys=config["jira"].get("project_keys"))
        self._rule_open_source_check = OpenSourceCheckRule(
            project_manager=self._project_manager, **config["open_source_check_rule"])
        self._rule_workflow_check = WorkflowCheckRule(jira=jira)
        self._rule_followup = FollowupRule(project_manager=self._project_manager, jira=jira)
        self._rule_process_related_projects_issues = ProcessRelatedProjectIssuesRule(
            jira=jira, **config["process_related_merge_requests_rule"])

        self._mr_queue = mr_queue

    def handle(self, mr_manager: MergeRequestManager):
        essential_rule_check_result = self._rule_essential.execute(mr_manager)
        logger.debug(f"{mr_manager}: {essential_rule_check_result}")

        nx_submodule_check_result = self._rule_nx_submodules_check.execute(mr_manager)
        logger.debug(f"{mr_manager}: {nx_submodule_check_result}")

        commit_message_check_result = self._rule_commit_message.execute(mr_manager)
        logger.debug(f"{mr_manager}: {commit_message_check_result}")

        open_source_check_result = self._rule_open_source_check.execute(mr_manager)
        logger.debug(f"{mr_manager}: {open_source_check_result}")

        if (not nx_submodule_check_result or
                not essential_rule_check_result or
                not commit_message_check_result or
                not open_source_check_result):
            if essential_rule_check_result == EssentialRule.ExecutionResult.merged:
                followup_result = self._rule_followup.execute(mr_manager)
                logger.debug(f"{mr_manager}: {followup_result}")
            return

        workflow_check_result = self._rule_workflow_check.execute(mr_manager)
        logger.debug(f"{mr_manager}: {workflow_check_result}")

        if not workflow_check_result:
            return

        self.merge_and_do_postprocessing(mr_manager)

    def merge_and_do_postprocessing(self, mr_manager: MergeRequestManager):
        mr_manager.squash_locally_if_needed(self._repo)

        mr_manager.update_unfinished_processing_flag(True)

        mr_manager.merge_or_rebase()

        process_related_result = self._rule_process_related_projects_issues.execute(mr_manager)
        logger.debug(f"{mr_manager}: {process_related_result}")

        followup_result = self._rule_followup.execute(mr_manager)
        logger.debug(f"{mr_manager}: {followup_result}")

        mr_manager.update_unfinished_processing_flag(False)

    def run(self):
        logger.info(
            f"Robocat revision {automation_tools.bot_info.revision()}. Started for project "
            f"[{self._project_manager.data.name}].")

        for mr in self._project_manager.get_next_open_merge_request():
            self._mr_queue.put(
                GitlabEventData(mr_id=mr.id, event_type=GitlabEventType.merge_request))

        while(True):
            event_data = self._mr_queue.get()
            try:
                self.process_event(event_data)
            except gitlab.exceptions.GitlabError as e:
                logger.warning(f"{event_data}: Gitlab error: {e}")
            except JiraError as e:
                logger.warning(f"{event_data}: Jira error: {e}")
            except automation_tools.utils.AutomationError as e:
                logger.warning(f"{event_data}: Generic bot error: {e}")
            except git.GitError as e:
                logger.warning(f"{event_data}: Git error: {e}")
            except PlayPipelineError as e:
                logger.warning(f"{event_data}: Pipeline error: {e}")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"{event_data}: Connection error: {e}")
            except Exception as e:
                logger.warning(f"{event_data}: Unknown error: {e}")

    def process_event(self, event_data: GitlabEventData):
        mr_id = event_data["mr_id"]
        mr_manager = self._project_manager.get_merge_request_manager_by_id(mr_id)
        if not mr_manager.is_mr_assigned_to_current_user:
            return

        if event_data["event_type"] == GitlabEventType.comment:
            command = robocat.commands.parser.create_command_from_text(
                username=self._username,
                text=event_data["added_comment"])
            logger.debug(f'Comment {event_data["added_comment"]} parsed as "{command}" command.')

            if command:
                command.run(mr_manager)
                if command.should_handle_mr_after_run:
                    self.handle(mr_manager)
            return

        if event_data["event_type"] == GitlabEventType.pipeline:
            pipeline_status = Pipeline.translate_status(event_data["raw_pipeline_status"])
            logger.debug(f"New pipeline status for mr {mr_id} is {pipeline_status}.")
            if pipeline_status == PipelineStatus.running:
                return

        self.handle(mr_manager)

    def get_merge_requests_manager(self, mr_poll_rate):
        while True:
            start_time = time.time()
            for mr in self._project_manager.get_next_unfinished_merge_request():
                yield MergeRequestManager(mr, self._username)
            for mr in self._project_manager.get_next_open_merge_request():
                yield MergeRequestManager(mr, self._username)

            if mr_poll_rate is None:
                break

            sleep_time = max(0, start_time + mr_poll_rate - time.time())
            time.sleep(sleep_time)

    def run_poller(self):
        logger.info(
            f"Robocat revision {automation_tools.bot_info.revision()}. Started for project "
            f"[{self._project_manager.data.name}] in polling mode.")

        for mr_manager in self.get_merge_requests_manager(MR_POLL_RATE_S):
            try:
                self.handle(mr_manager)
            except gitlab.exceptions.GitlabError as e:
                logger.warning(f"{mr_manager}: Gitlab error: {e}")
            except JiraError as e:
                logger.warning(f"{mr_manager}: Jira error: {e}")
            except automation_tools.utils.AutomationError as e:
                logger.warning(f"{mr_manager}: Generic bot error: {e}")
            except git.GitError as e:
                logger.warning(f"{mr_manager}: Git error: {e}")
            except PlayPipelineError as e:
                logger.warning(f"{mr_manager}: Pipeline error: {e}")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"{mr_manager}: Connection error: {e}")
            except Exception as e:
                logger.warning(f"{mr_manager}: Unknown error: {e}")
