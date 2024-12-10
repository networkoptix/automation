## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import logging
import os
import queue
import requests
import threading
import time
from datetime import timedelta, datetime
from typing import Optional

import git
import gitlab

import automation_tools.utils
import automation_tools.bot_info
from automation_tools.jira import GitlabBranchDescriptor, JiraAccessor, JiraError
from automation_tools.jira_comments import JiraComment, JiraCommentDataKey, JiraMessageId
import automation_tools.git
import robocat.commands.parser
from robocat.gitlab_events import (
    GitlabEventType,
    GitlabMrEventData,
    GitlabPipelineEventData,
    GitlabCommentEventData,
    GitlabJobEventData,
    GitlabEventData)
from robocat.config import Config
from robocat.project_manager import ProjectManager
from robocat.project import Project
from robocat.merge_request_actions.notify_user_actions import add_failed_pipeline_comment_if_needed
from robocat.merge_request_manager import MergeRequestManager
from robocat.note import find_last_comment, MessageId
from robocat.pipeline import Job, JobStatus, PlayPipelineError, Pipeline, PipelineStatus
from robocat.rule import ALL_RULES

logger = logging.getLogger(__name__)

MR_POLL_RATE_S = 30


class Bot(threading.Thread):
    LONG_EVENT_PROCESSING_THRESHOLD_S = 20
    LONG_WAIT_THRESHOLD_S = 30

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
            mr_queue: queue.PriorityQueue,
            raw_gitlab: gitlab.Gitlab = None,
            config_check_only: bool = False,
            config_ref: str = "master"):
        super().__init__()

        raw_gitlab = raw_gitlab or gitlab.Gitlab.from_config("nx_gitlab")
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
                project.get_file_content(ref=config_ref, file="robocat.json"), "json")
            self.config = Config(**dict(merge_dicts(config, local_config)))
        except gitlab.GitlabGetError:
            self.config = Config(**config)

        if config_check_only:
            return

        self._setup_environment()
        self._repo = automation_tools.git.Repo(
            path=self.config.repo.path,
            url=self.config.repo.url,
            committer=committer)
        self._project_manager = ProjectManager(
            gitlab_project=gitlab_project,
            current_user=self._username,
            repo=self._repo)
        project_keys = (
            list(self.config.jira.project_mapping.keys())
            if self.config.jira.project_mapping
            else self.config.jira.project_keys)
        self._jira = JiraAccessor(
            url=self.config.jira.url,
            login=self.config.jira.login,
            password=self.config.jira.password,
            timeout=self.config.jira.timeout,
            retries=self.config.jira.retries,
            project_keys=project_keys)

        # If no rules are listed as enabled, fall back to enabling all rules. This is to preserve
        # the original behavior on branches without this config option.
        all_rule_identiers = [rule.identifier for rule in ALL_RULES]
        self._rules = {rule.identifier: rule(self.config, self._project_manager, self._jira)
                       for rule in ALL_RULES
                       if rule.identifier in (self.config.enabled_rules or all_rule_identiers)}
        self._mr_queue = mr_queue
        self._polling = False  # By default assume that we are in the "webhook" mode.

    def _setup_environment(self):
        # The ServiceNameFilter is created before we have this information. So we need to set it
        # in the environment, which allows the filter to annotate the service name with the repo,
        # which in turn makes it possible to filter per-repo instances of Robocat in Graylog.
        url = self.config.repo.url
        try:
            repo = url.split(":")[-1].replace(".git", "")
            os.environ["BOT_GIT_REPO"] = repo
        except KeyError:
            logger.warning("Can't set BOT_GIT_REPO environment variable.")

    def handle(self, mr_manager: MergeRequestManager):
        if not mr_manager.is_post_merging_unfinished():
            if not self._do_pre_processing_actions(mr_manager):
                return

            if not self._execute_rules(mr_manager):
                return

            if not self._try_merge(mr_manager):
                return

        self._execute_post_merge_rules(mr_manager)

    def _do_pre_processing_actions(self, mr_manager: MergeRequestManager) -> bool:
        logger.debug(f"{mr_manager}: Pre-processing")
        mr_manager.update_merge_base()

        # Check if we have un-run pipeline requested by user.
        if command_run_pipeline := find_last_comment(
                notes=mr_manager.notes(), message_id=MessageId.CommandRunPipeline):
            if not command_run_pipeline.additional_data.get("CommandExecuted", False):
                mr_manager.run_user_requested_pipeline()

        # Ensure comment that MR is merged to its target branch to the corresponding Jira Issues.
        if (mr_manager.data.is_merged):
            self._add_merged_comment_to_jira_issues_if_needed(mr_manager)

        # TODO: Add here
        # - adding to MR initial Robocat message (move from essential rule).
        return True

    def _execute_rules(self, mr_manager: MergeRequestManager) -> bool:
        def _execute(rule):
            result = rule.execute(mr_manager)
            logger.debug(f"[{rule.identifier}] {mr_manager}: {result}")
            return result

        logger.debug(f"{mr_manager}: Executing necessary rules")

        default_rules = ["essential", "nx_submodule", "commit_message", "job_status"]

        results = [_execute(self._rules[rule]) for rule in default_rules if rule in self._rules]

        if not all(results):
            return False

        if "workflow" in self._rules:
            return _execute(self._rules["workflow"])

        return True

    def _try_merge(self, mr_manager: MergeRequestManager) -> bool:
        logger.debug(f"{mr_manager}: Prepare merge")

        if not mr_manager.prepare_to_merge(self._repo):
            logger.debug(f"{mr_manager}: Not ready to merge")
            return False

        logger.debug(f"{mr_manager}: Start merge")

        # Do it before merging because this operation can result in exception. So if it is happen
        # after successful merge, the merged MR will not have the "unfinished post-merge" flag.
        mr_manager.update_unfinished_post_merging_flag(True)

        try:
            if result := mr_manager.merge():
                self._add_merged_comment_to_jira_issues_if_needed(mr_manager)
        except Exception as e:
            mr_manager.update_unfinished_post_merging_flag(False)
            # TODO: Add to Bot event queue an event for trying to process this MR again.
            raise e

        return result

    def _add_merged_comment_to_jira_issues_if_needed(self, mr_manager: MergeRequestManager):
        for issue_key in mr_manager.data.issue_keys:
            try:
                issue = self._jira.get_issue(issue_key)
                branch_descriptor = GitlabBranchDescriptor(
                    branch_name=mr_manager.data.target_branch,
                    project_path=self._project_manager.data.path)
                if issue.has_bot_comment(
                        message_id=JiraMessageId.MrMergedToBranch,
                        params={JiraCommentDataKey.MrId: mr_manager.data.id}):
                    continue
                issue.add_comment(JiraComment(
                    message_id=JiraMessageId.MrMergedToBranch,
                    params={
                        "mr_name": mr_manager.data.title,
                        "mr_url": mr_manager.data.url,
                        "mr_branch": str(branch_descriptor),
                    },
                    data={
                        JiraCommentDataKey.MrId.name: mr_manager.data.id,
                        JiraCommentDataKey.MrBranch.name: str(branch_descriptor),
                    }))
            except JiraError as e:
                logger.error(f'{mr_manager}: Failed to add "MR merged" comment to Jira Issue: {e}')
                self.add_comment_with_message_id(
                    message_id=MessageId.FailedMrMergedJiraComment,
                    message_params={"error": str(e), "issue_key": issue_key})

    def _execute_post_merge_rules(self, mr_manager: MergeRequestManager):
        logger.debug(f"{mr_manager}: Executing post-merge rules")

        if "process_related" in self._rules:
            process_related_result = self._rules["process_related"].execute(mr_manager)
            logger.debug(f"{mr_manager}: {process_related_result}")

        if self._polling and "follow_up" in self._rules:
            follow_up_result = self._rules["follow_up"].execute(mr_manager)
            logger.debug(f"{mr_manager}: {follow_up_result}")

        if "post_processing" in self._rules:
            post_processing_result = self._rules["post_processing"].execute(mr_manager)
            logger.debug(f"{mr_manager}: {post_processing_result}")

        mr_manager.update_unfinished_post_merging_flag(False)

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
            self.process_event(self._mr_queue.get())

    def process_event(self, event_data: GitlabEventData):
        mr_manager = None
        timestamp_format = "%Y-%m-%d %H:%M:%S.%f"
        start_time = time.time()

        def _log_processing_start():
            log_level = (
                logging.INFO if start_time - event_data.receive_time > self.LONG_WAIT_THRESHOLD_S
                else logging.DEBUG)
            log_message = (
                f"{event_data}: Event processing started at "
                f"{datetime.fromtimestamp(start_time).strftime(timestamp_format)}. Recieve time: "
                f"{datetime.fromtimestamp(event_data.receive_time).strftime(timestamp_format)}, "
                f"delta: {timedelta(seconds=start_time - event_data.receive_time)}.")
            logger.log(level=log_level, msg=log_message)
            logger.log(level=log_level, msg=f"Tasks left in the queue: {self._mr_queue.qsize()}")

        def _log_processing_end():
            end_time = time.time()
            log_level = (
                logging.INFO if end_time - start_time > self.LONG_EVENT_PROCESSING_THRESHOLD_S
                else logging.DEBUG)
            log_message = (
                f"{event_data}: Finish event processing. Time taken: "
                f"{timedelta(seconds=end_time - start_time)}.")
            logger.log(level=log_level, msg=log_message)

        try:
            _log_processing_start()
            if mr_manager := self._create_mr_manager_by_event_data(event_data):
                self.event_handler[event_data.event_type](
                    payload=event_data.payload, mr_manager=mr_manager)
            _log_processing_end()
        except Exception as e:
            create_exception_comment(event_data=event_data, exception=e, mr_manager=mr_manager)

    def _create_mr_manager_by_event_data(
            self, event_data: GitlabEventData) -> Optional[MergeRequestManager]:
        if event_data.event_type == GitlabEventType.job:
            job = Job(event_data.payload)
            pipeline = self._project_manager.get_pipeline(job.pipeline_location)
            mr_id = pipeline.mr_id
        else:
            mr_id = event_data.payload["mr_id"]

        if not mr_id:
            return None

        mr_manager = self._project_manager.get_merge_request_manager_by_id(mr_id)
        if not mr_manager.is_mr_assigned_to_current_user:
            return None

        return mr_manager

    def _handle_mr_if_needed(
            self, current_mr_state: str, previous_mr_state: str, mr_manager: MergeRequestManager):

        if current_mr_state == "merged" and previous_mr_state in ["opened", "locked"]:
            logger.info(f"{mr_manager}: Merge Request was just merged; executing necessary rules.")

            if "follow_up" in self._rules:
                follow_up_result = self._rules["follow_up"].execute(mr_manager)
                logger.debug(f"{mr_manager}: {follow_up_result}")

            if "post_processing" in self._rules:
                post_processing_result = self._rules["post_processing"].execute(mr_manager)
                logger.debug(f"{mr_manager}: {post_processing_result}")

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
                config=self.config,
                project_manager=self._project_manager,
                jira=self._jira)
            if command.should_handle_mr_after_run:
                self.handle(mr_manager)

    def _process_pipeline_event(
            self, payload: GitlabPipelineEventData, mr_manager: MergeRequestManager):
        logger.info(f"Start processing Pipeline event {payload}.")
        pipeline_status = Pipeline.translate_status(payload["raw_pipeline_status"])
        if pipeline_status == PipelineStatus.running:
            return

        self._handle_mr_if_needed(
            current_mr_state=payload["mr_state"],
            previous_mr_state=payload.get("mr_previous_data", {}).get("state", ""),
            mr_manager=mr_manager)

    def _process_job_event(self, payload: GitlabJobEventData, mr_manager: MergeRequestManager):
        job = Job(payload)
        logger.debug(f"New {job.name} job status for MR {mr_manager.data.id} is {job.status}.")
        if job.status not in [JobStatus.failed, JobStatus.succeeded]:
            return

        if job.status == JobStatus.failed and not job.allow_failure:
            add_failed_pipeline_comment_if_needed(mr_manager=mr_manager, job_name=job.name)

        autorun_stage = self.config.pipeline.autorun_stage
        if job.stage == autorun_stage:
            job_pipeline = self._project_manager.get_pipeline(job.pipeline_location)
            if job_pipeline.is_stage_completed(autorun_stage):
                logger.info(f"MR {mr_manager!r} processing triggered by Job event {payload}.")
                self.handle(mr_manager)

    def _process_mr_event(self, payload: GitlabMrEventData, mr_manager: MergeRequestManager):
        logger.info(f"Start processing Merge Request event {payload}.")
        if (self.config.repo.need_code_owner_approval
                and mr_manager.is_follow_up()
                and payload["code_changed"]):
            mr_manager.remove_robocat_approval()

        self._handle_mr_if_needed(
            current_mr_state=payload["mr_state"],
            previous_mr_state=payload.get("mr_previous_data", {}).get("state", ""),
            mr_manager=mr_manager)

    def get_merge_requests_manager(self, mr_id: Optional[int] = None):
        if mr_id:
            yield self._project_manager.get_merge_request_manager_by_id(mr_id)
            return

        while True:
            start_time = time.time()
            for mr in self._project_manager.get_next_unfinished_merge_request():
                yield MergeRequestManager(mr, self._username)
            for mr in self._project_manager.get_next_open_merge_request():
                yield MergeRequestManager(mr, self._username)

            sleep_time = max(0, start_time + MR_POLL_RATE_S - time.time())
            time.sleep(sleep_time)

    def run_poller(self, mr_id: Optional[int] = None):
        logger.info(
            f"Robocat revision {automation_tools.bot_info.revision()}. Started for project "
            f"[{self._project_manager.data.name}] in polling mode.")

        self._polling = True

        for mr_manager in self.get_merge_requests_manager(mr_id):
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
            except Exception as exception:
                stack_trace_repr, exc_info = automation_tools.utils.get_exception_info(exception)
                logger.warning(f"{mr_manager}: Unknown error: {exc_info}; \n{stack_trace_repr}")


def create_exception_comment(
        event_data: GitlabEventData,
        mr_manager: Optional[MergeRequestManager],
        exception: Exception):
    stack_trace_repr, exception_info = automation_tools.utils.get_exception_info(exception)
    logger.warning(f"{exception_info}; Event: {event_data.as_string_dict()}\n{stack_trace_repr}")

    if not mr_manager:
        return

    previous_exception_comment = find_last_comment(
        notes=mr_manager.notes(),
        message_id=MessageId.ExceptionOccurred,
        condition=lambda n: (
            n.message_id == MessageId.ExceptionOccurred
            and n.sha == mr_manager.data.sha
            and n.additional_data.get("exception_info") == exception_info
            and n.additional_data.get("stack_trace") == stack_trace_repr))

    if previous_exception_comment:
        comment_data = previous_exception_comment.additional_data
        comment_data["last_repetition_event_info"] = event_data.as_string_dict()
        comment_data["repetitions"] = previous_exception_comment.additional_data["repetitions"] + 1
        mr_manager.update_comment_data(
            note_id=previous_exception_comment.note_id, data=comment_data)
    else:
        comment_data = {
            "last_repetition_event_info": event_data.as_string_dict(),
            "exception_info": exception_info,
            "stack_trace": stack_trace_repr,
            "repetitions": 1,
        }
        mr_manager.add_comment_with_message_id(
            message_id=MessageId.ExceptionOccurred, message_data=comment_data)
