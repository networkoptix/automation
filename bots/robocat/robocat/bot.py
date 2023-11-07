import os
import enum
import logging
from pathlib import Path
import queue
import requests
import threading
import time
from typing import TypedDict, Union

import git
import gitlab

import automation_tools.utils
import automation_tools.bot_info
from automation_tools.jira import JiraAccessor, JiraError
import automation_tools.git
import robocat.commands.parser
from robocat.project_manager import ProjectManager
from robocat.project import Project
from robocat.merge_request_actions.notify_user_actions import add_failed_pipeline_comment_if_needed
from robocat.merge_request_manager import MergeRequestManager
from robocat.pipeline import PlayPipelineError, Pipeline, PipelineStatus
from robocat.rule import ALL_RULES

logger = logging.getLogger(__name__)

MR_POLL_RATE_S = 30


class GitlabEventType(enum.Enum):
    merge_request = enum.auto()
    pipeline = enum.auto()
    job = enum.auto()
    comment = enum.auto()


class MrPreviousData(TypedDict):
    state: str


class GitlabMrRelatedEventData(TypedDict):
    mr_id: str
    mr_state: str


class GitlabMrEventData(GitlabMrRelatedEventData):
    mr_previous_data: MrPreviousData
    is_revision_updated: bool


class GitlabPipelineEventData(GitlabMrRelatedEventData):
    raw_pipeline_status: str


class GitlabCommentEventData(GitlabMrRelatedEventData):
    added_comment: str


class GitlabJobEventData(TypedDict):
    pipeline_id: str
    name: str
    status: str
    allow_failure: bool


class GitlabEventData(TypedDict):
    payload: Union[GitlabMrRelatedEventData, GitlabJobEventData]
    event_type: GitlabEventType


class Bot(threading.Thread):
    @property
    def event_handler(self):
        return {
            GitlabEventType.comment: self._process_comment_event,
            GitlabEventType.pipeline: self._process_pipeline_event,
            GitlabEventType.job: self._process_job_event,
            GitlabEventType.merge_request: self._process_mr_event,
        }

    def __init__(
            self,
            config,
            project_id: int,
            mr_queue: queue.SimpleQueue):
        super().__init__()

        raw_gitlab = gitlab.Gitlab.from_config("nx_gitlab")
        raw_gitlab.auth()
        gitlab_user_info = raw_gitlab.users.get(raw_gitlab.user.id)
        self._username = gitlab_user_info.username
        committer = automation_tools.utils.User(
            email=gitlab_user_info.email, name=gitlab_user_info.name,
            username=gitlab_user_info.username)

        gitlab_project = raw_gitlab.projects.get(project_id)
        project = Project(gitlab_project)

        try:
            from automation_tools.utils import merge_dicts, parse_config_string
            local_config = parse_config_string(
                project.get_file_content(ref="master", file="robocat.json"), "json")
            config = dict(merge_dicts(config, local_config))
        except gitlab.GitlabGetError:
            pass

        self._repo = automation_tools.git.Repo(**config["repo"], committer=committer)
        self._project_manager = ProjectManager(
            gitlab_project=gitlab_project,
            current_user=self._username,
            repo=self._repo)
        self._jira = JiraAccessor(**config["jira"])

        # If no rules are listed as enabled, fall back to enabling all rules. This is to preserve
        # the original behavior on branches without this config option.
        all_rule_identiers = [rule.identifier for rule in ALL_RULES]
        self._rules = {rule.identifier: rule(config, self._project_manager, self._jira)
                       for rule in ALL_RULES
                       if rule.identifier in config.get("enabled_rules", all_rule_identiers)}
        self._mr_queue = mr_queue
        self._polling = False  # By default assume that we are in the "webhook" mode.

    def handle(self, mr_manager: MergeRequestManager):
        def _execute(rule):
            result = rule.execute(mr_manager)
            logger.debug(f"[{rule.identifier}] {mr_manager}: {result}")
            return result

        default_rules = ["essential", "nx_submodules", "commit_message", "job_status"]

        results = [_execute(self._rules[rule]) for rule in default_rules if rule in self._rules]
        if not all(results):
            return

        if "workflow" in self._rules:
            workflow_check_result = self._rules["workflow"].execute(mr_manager)
            logger.debug(f"[workflow] {mr_manager}: {workflow_check_result}")

            if not workflow_check_result:
                return

        self.merge_and_do_postprocessing(mr_manager)

    def merge_and_do_postprocessing(self, mr_manager: MergeRequestManager):
        mr_manager.squash_locally_if_needed(self._repo)

        mr_manager.update_unfinished_processing_flag(True)

        mr_manager.merge_or_rebase()

        if "process_related" in self._rules:
            process_related_result = self._rules["process_related"].execute(mr_manager)
            logger.debug(f"{mr_manager}: {process_related_result}")

        if self._polling and "follow_up" in self._rules:
            follow_up_result = self._rules["follow_up"].execute(mr_manager)
            logger.debug(f"{mr_manager}: {follow_up_result}")

        mr_manager.update_unfinished_processing_flag(False)

    def run(self):
        logger.info(
            f"Robocat revision {automation_tools.bot_info.revision()}. Started for project "
            f"[{self._project_manager.data.name}].")

        self._polling = False

        for mr in self._project_manager.get_next_open_merge_request():
            self._mr_queue.put(
                GitlabEventData(
                    payload=GitlabMrEventData(mr_id=mr.id, mr_state='opened'),
                    event_type=GitlabEventType.merge_request))

        while (True):
            event_data = self._mr_queue.get()
            try:
                logger.debug(f"{event_data}: Start event processing.")
                self.process_event(event_data)
                logger.debug(f"{event_data}: Finish event processing")
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
        (event_type, payload) = (event_data["event_type"], event_data["payload"])
        if event_type == GitlabEventType.job:
            pipeline = self._project_manager.get_pipeline(payload["pipeline_id"])
            mr_id = pipeline.mr_id
            if not mr_id:
                return
        else:
            mr_id = payload["mr_id"]

        mr_manager = self._project_manager.get_merge_request_manager_by_id(mr_id)
        if not mr_manager.is_mr_assigned_to_current_user:
            return

        self.event_handler[event_type](payload=payload, mr_manager=mr_manager)

    def _handle_mr_if_needed(
            self, current_mr_state: str, previous_mr_state: str, mr_manager: MergeRequestManager):

        if current_mr_state == "merged" and previous_mr_state in ["opened", "locked"]:
            logger.info(f"{mr_manager}: Merge Request is just merged; executing follow-up rule.")
            follow_up_result = self._rules["follow_up"].execute(mr_manager)
            logger.debug(f"{mr_manager}: {follow_up_result}")
            return

        if current_mr_state == "opened":
            self.handle(mr_manager)

    def _process_comment_event(
            self, payload: GitlabCommentEventData, mr_manager: MergeRequestManager):
        command = robocat.commands.parser.create_command_from_text(
            username=self._username,
            text=payload["added_comment"])
        logger.debug(
            f'Comment {payload["added_comment"]} parsed as "{command}" command.')

        if command:
            command.run(
                mr_manager=mr_manager,
                project_manager=self._project_manager,
                jira=self._jira)
            if command.should_handle_mr_after_run:
                self.handle(mr_manager)

    def _process_pipeline_event(
            self, payload: GitlabPipelineEventData, mr_manager: MergeRequestManager):
        pipeline_status = Pipeline.translate_status(payload["raw_pipeline_status"])
        logger.debug(f"New pipeline status for MR {mr_manager.data.id} is {pipeline_status}.")
        if pipeline_status == PipelineStatus.running:
            return

        self._handle_mr_if_needed(
            current_mr_state=payload["mr_state"],
            previous_mr_state=payload.get("mr_previous_data", {}).get("state", ""),
            mr_manager=mr_manager)

    def _process_job_event(self, payload: GitlabJobEventData, mr_manager: MergeRequestManager):
        job_name = payload["name"]
        job_status = payload["status"]
        logger.debug(f"New {job_name} job status for MR {mr_manager.data.id} is {job_status}.")
        if job_status != "failed" or payload["allow_failure"]:
            return
        add_failed_pipeline_comment_if_needed(mr_manager=mr_manager, job_name=job_name)

    def _process_mr_event(
            self, payload: GitlabMrRelatedEventData, mr_manager: MergeRequestManager):
        # Workaround for GitLab problem: webhook can be triggered before the internal MR state
        # becomes consistent (e.g.: sometimes webhook is triggered after pushing new commit to the
        # approved MR before the approvals are cleared).
        if payload.get("is_revision_updated"):
            mr_manager.is_revision_just_updated = True

        self._handle_mr_if_needed(
            current_mr_state=payload["mr_state"],
            previous_mr_state=payload.get("mr_previous_data", {}).get("state", ""),
            mr_manager=mr_manager)

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

        self._polling = True

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
