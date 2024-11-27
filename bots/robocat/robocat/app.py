## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import os
import argparse
import logging
import queue
import signal
import sys
import traceback
import threading
from typing import Awaitable, Callable

from gidgetlab.aiohttp import GitLabBot
import graypy

import automation_tools.utils
from robocat.bot import Bot
from robocat.gitlab_events import (
    GitlabEventType,
    GitlabMrEventData,
    GitlabPipelineEventData,
    GitlabCommentEventData,
    GitlabJobEventData,
    GitlabEventData,
    MrPreviousData)

logger = logging.getLogger(__name__)

robocat = GitLabBot('Robocat')
mr_queue = queue.PriorityQueue()


AsyncCallback = Callable[..., Awaitable[None]]


MR_STATE_ID_TO_STATE_NAME = {
    1: "opened",
    2: "closed",
    3: "merged",
    4: "locked",
}


def add_event_hook(
        event_type: str, object_key: str = None) -> Callable[[AsyncCallback], AsyncCallback]:
    def decorator(func: AsyncCallback) -> AsyncCallback:
        async def event_processor(event, *_):
            try:
                if object_key is None:
                    await func(event)
                    return

                event_object = event.data.get(object_key)
                if event_object:
                    await func(event, event_object)
                else:
                    logger.debug(
                        f"Got {event_type} event without the Merge Request object. Raw data: "
                        f"{event.data!r}")
            except Exception as e:
                logger.error(f"Crashed while processing {event_type} event: {e!r}")

        return robocat.router.register(f"{event_type} Hook")(event_processor)

    return decorator


@add_event_hook("Merge Request", "object_attributes")
async def merge_request_event(event, mr_object):
    mr_id = mr_object['iid']
    mr_state = mr_object['state']
    is_code_changed = ('oldrev' in mr_object)
    logger.debug(
        f"Got Merge Request event. MR id: {mr_id} (state {mr_state}, code is "
        f'{"" if is_code_changed else "not "}changed )')
    mr_changes = event.data["changes"]

    # Convert state ids to state names.
    if "state_id" in mr_changes:
        mr_changes["state"] = {
            k: MR_STATE_ID_TO_STATE_NAME[v] for k, v in mr_changes["state_id"].items()}
        del mr_changes["state_id"]

    mr_previous_data = {
        k: mr_changes.get(k, {}).get("previous") for k in MrPreviousData.__required_keys__}
    payload = GitlabMrEventData(
        mr_id=mr_id,
        mr_state=mr_state,
        mr_previous_data=mr_previous_data,
        # From GitLab Webhook events documentation: "The field object_attributes.oldrev is only
        # available when there are actual code changes".
        code_changed=is_code_changed)
    mr_queue.put(GitlabEventData(event_type=GitlabEventType.merge_request, payload=payload))


@add_event_hook("Pipeline", "merge_request")
async def pipeline_event(event, mr_object):
    mr_id = mr_object['iid']
    pipeline_id = event.data["object_attributes"]["id"]
    mr_state = mr_object['state']
    logger.debug(f'Got Pipeline event for pipeline {pipeline_id!r}. MR id: {mr_id} ({mr_state})')
    raw_pipeline_status = event.data["object_attributes"]["status"]
    payload = GitlabPipelineEventData(
        mr_id=mr_id, mr_state=mr_state,
        raw_pipeline_status=raw_pipeline_status,
        pipeline_id=pipeline_id)
    mr_queue.put(GitlabEventData(event_type=GitlabEventType.pipeline, payload=payload))


@add_event_hook("Note", "merge_request")
async def note_event(event, mr_object):
    mr_id = mr_object['iid']
    mr_state = mr_object['state']
    logger.debug(f'Got Note event. MR id: {mr_id} ({mr_state})')
    comment = event.data["object_attributes"]["note"]
    payload = GitlabCommentEventData(mr_id=mr_id, mr_state=mr_state, added_comment=comment)
    # Add the event to the queue with the highest priority.
    mr_queue.put(GitlabEventData(priority=0, event_type=GitlabEventType.comment, payload=payload))


@add_event_hook("Job")
async def job_event(event):
    pipeline_id = event.data["pipeline_id"]
    project_id = event.data["project_id"]
    build_name = event.data["build_name"]
    build_status = event.data["build_status"]

    logger.debug(
        f'Got Job event. Pipeline id: {pipeline_id}, status {build_status}, name {build_name}')
    payload = GitlabJobEventData(
        job_id=event.data["build_id"],
        pipeline_id=pipeline_id,
        project_id=project_id,
        name=build_name,
        status=build_status,
        stage=event.data["build_stage"],
        allow_failure=event.data["build_allow_failure"])
    mr_queue.put(GitlabEventData(event_type=GitlabEventType.job, payload=payload))


class ServiceNameFilter(logging.Filter):
    @staticmethod
    def filter(record: logging.LogRecord):
        record.service_name = "Workflow Robocat"
        if repo_name := os.getenv("BOT_GIT_REPO"):
            record.service_name += f" ({repo_name})"
        return True


class DiscardHealthCheckMessage(logging.Filter):
    """k8s pod health check performed every 2 seconds,
    discard health check requests messages from container log"""
    @staticmethod
    def filter(record: logging.LogRecord):
        return 'GET /health' not in record.getMessage()


class DiscardAiohttpAccessMessage(logging.Filter):
    """aiohttp send a lot of irrelevant messages - skip them"""
    @staticmethod
    def filter(record: logging.LogRecord):
        return not (record.name == 'aiohttp.access' and record.levelno < logging.WARNING)


def thread_exception_hook(args):
    logger.error(
        f'Unexpected exception in thread: {args.exc_value!r}\n'
        f'{"".join(traceback.format_tb(args.exc_traceback))}\n'
        'Exiting.')
    signal.raise_signal(signal.SIGTERM)


def config_check(config: dict, project_id: int, config_ref: str):
    import gitlab

    # Create a GitLab client instance to check the config. We don't have the nx_gitlab config
    # in the automation pipeline, but we do have the GITLAB_API_TOKEN environment variable set.
    # We only need this token to fetch a repo-specific config, so this is enough for this case.
    gitlab_token = os.getenv("GITLAB_API_TOKEN")
    if not gitlab_token:
        logger.error(
            "The config_check mode requires the GITLAB_API_TOKEN environment variable.")
        sys.exit(1)
    gitlab_url = os.getenv("CI_SERVER_URL", "https://gitlab.example.com")
    raw_gitlab = gitlab.Gitlab(gitlab_url, private_token=gitlab_token)
    # Creating a Bot instance will load the configuration and the pydantic code that verifies
    # the structure will be executed.
    Bot(
        config=config,
        project_id=project_id,
        config_ref=config_ref,
        mr_queue=mr_queue,
        raw_gitlab=raw_gitlab,
        config_check_only=True)
    logger.info("Config check passed successfully, exiting.")


def main():
    parser = argparse.ArgumentParser(sys.argv[0])
    parser.add_argument(
        '-c', '--config',
        help="Config file with all global options",
        type=automation_tools.utils.config_from_filename,
        default={})
    parser.add_argument(
        '-p', '--project-id',
        help="Id of a project in gitlab (2 for dev/nx)",
        type=int,
        required=True)
    parser.add_argument(
        '--log-level',
        help="Logs level",
        choices=logging._nameToLevel.keys(),
        default=logging.INFO)
    parser.add_argument(
        '--mode',
        help="Working mode",
        choices=["webhook", "poll", "config_check", "run_once"],
        default="webhook")
    parser.add_argument(
        '--mr-id',
        help="Merge Request id to process. Make sense only for \"run_once\" mode",
        type=int,
        required=False)
    parser.add_argument(
        '--config-ref',
        help="Git reference to get the repo-specific config from",
        type=str,
        default="master")
    parser.add_argument('--graylog', help="Hostname of Graylog service")
    arguments = parser.parse_args()

    log_handler = None
    if arguments.graylog:
        host, port = arguments.graylog.split(":")
        log_handler = graypy.GELFTCPHandler(host, port, level_names=True)
        log_handler.addFilter(ServiceNameFilter())
        log_handler.addFilter(DiscardHealthCheckMessage())
        log_handler.addFilter(DiscardAiohttpAccessMessage())
    else:
        log_handler = logging.StreamHandler()

    logging.basicConfig(
        level=arguments.log_level,
        handlers=[log_handler],
        format='%(asctime)s %(levelname)s %(name)s\t%(message)s')

    if arguments.mode == "webhook":
        threading.excepthook = thread_exception_hook
        executor_thread = Bot(
            config=arguments.config,
            project_id=arguments.project_id,
            mr_queue=mr_queue,
            config_ref=arguments.config_ref)
        executor_thread.start()
        robocat.run()
    elif arguments.mode == "poll":
        executor = Bot(
            config=arguments.config,
            project_id=arguments.project_id,
            mr_queue=mr_queue,
            config_ref=arguments.config_ref)
        executor.run_poller()
    elif arguments.mode == "config_check":
        config_check(
            config=arguments.config,
            project_id=arguments.project_id,
            config_ref=arguments.config_ref)
    elif arguments.mode == "run_once":
        if not arguments.mr_id:
            logger.error("MR id is required for \"run_once\" mode, exiting.")
            sys.exit(64)  # Command line usage error.
        executor = Bot(
            config=arguments.config,
            project_id=arguments.project_id,
            mr_queue=mr_queue,
            config_ref=arguments.config_ref)
        executor.run_poller(arguments.mr_id)


if __name__ == '__main__':
    main()
