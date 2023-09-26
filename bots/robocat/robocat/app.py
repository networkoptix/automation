import argparse
import logging
from pathlib import Path
import queue
import signal
import sys
import traceback
import threading
from typing import Awaitable, Callable

from gidgetlab.aiohttp import GitLabBot
import graypy

import automation_tools.utils
from robocat.bot import (
    Bot,
    GitlabEventType,
    GitlabEventData,
    GitlabMrEventData,
    GitlabPipelineEventData,
    GitlabCommentEventData,
    GitlabJobEventData,
    MrPreviousData)

logger = logging.getLogger(__name__)

robocat = GitLabBot('Robocat')
mr_queue = queue.SimpleQueue()


AsyncCallback = Callable[..., Awaitable[None]]


MR_STATE_ID_TO_STATE_NAME = {
    1: "opened",
    2: "closed",
    3: "merged",
    4: "locked",
}


def add_event_hook(
        event_type: str,
        object_key: str = None) -> Callable[[AsyncCallback], AsyncCallback]:
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
                    logger.info(
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
    logger.debug(f'Got Merge Request event. MR id: {mr_id} ({mr_state})')
    mr_changes = event.data["changes"]

    # Convert state ids to state names.
    if "state_id" in mr_changes:
        mr_changes["state"] = {
            k: MR_STATE_ID_TO_STATE_NAME[v] for k, v in mr_changes["state_id"].items()}
        del mr_changes["state_id"]

    mr_previous_data = {
        k: mr_changes.get(k, {}).get("previous") for k in MrPreviousData.__required_keys__}
    payload = GitlabMrEventData(mr_id=mr_id, mr_state=mr_state, mr_previous_data=mr_previous_data)
    mr_queue.put(GitlabEventData(event_type=GitlabEventType.merge_request, payload=payload))


@add_event_hook("Pipeline", "merge_request")
async def pipeline_event(event, mr_object):
    mr_id = mr_object['iid']
    mr_state = mr_object['state']
    logger.debug(f'Got Pipeline event. MR id: {mr_id} ({mr_state})')
    raw_pipeline_status = event.data["object_attributes"]["status"]
    payload = GitlabPipelineEventData(
        mr_id=mr_id, mr_state=mr_state, raw_pipeline_status=raw_pipeline_status)
    mr_queue.put(GitlabEventData(event_type=GitlabEventType.pipeline, payload=payload))


@add_event_hook("Note", "merge_request")
async def note_event(event, mr_object):
    mr_id = mr_object['iid']
    mr_state = mr_object['state']
    logger.debug(f'Got Note event. MR id: {mr_id} ({mr_state})')
    comment = event.data["object_attributes"]["note"]
    payload = GitlabCommentEventData(mr_id=mr_id, mr_state=mr_state, added_comment=comment)
    mr_queue.put(GitlabEventData(event_type=GitlabEventType.comment, payload=payload))


@add_event_hook("Job")
async def job_event(event):
    pipeline_id = event.data["pipeline_id"]
    build_name = event.data["build_name"]
    build_status = event.data["build_status"]
    build_allow_failure = event.data["build_allow_failure"]

    logger.debug(
        f'Got Job event. Pipeline id: {pipeline_id}, status {build_status}, name {build_name}')
    payload = GitlabJobEventData(
        pipeline_id=pipeline_id,
        name=build_name,
        status=build_status,
        allow_failure=build_allow_failure)
    mr_queue.put(GitlabEventData(event_type=GitlabEventType.job, payload=payload))


class ServiceNameFilter(logging.Filter):
    @staticmethod
    def filter(record):
        record.service_name = "Workflow Robocat"
        return True


class DiscardHealhCheckMessage(logging.Filter):
    """k8s pod health check performed every 2 seconds,
    discard health check requests messages from container log"""
    @staticmethod
    def filter(record):
        return 'GET /health' not in record.getMessage()


def thread_exception_hook(args):
    logger.error(
        f'Unexpected exception in thread: {args.exc_value!r}\n'
        f'{"".join(traceback.format_tb(args.exc_traceback))}\n'
        'Exiting.')
    signal.raise_signal(signal.SIGTERM)


def main():
    parser = argparse.ArgumentParser(sys.argv[0])
    parser.add_argument(
        '-c', '--config',
        help="Config file with all global options",
        type=automation_tools.utils.config_from_filename,
        default={})
    parser.add_argument(
        "-lc", "--local-config",
        help="Local config file, usually located in the repo that is processed by robocat",
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
        choices=["webhook", "poll"],
        default="webhook")
    parser.add_argument('--graylog', help="Hostname of Graylog service")
    arguments = parser.parse_args()

    log_handler = None
    if arguments.graylog:
        host, port = arguments.graylog.split(":")
        log_handler = graypy.GELFTCPHandler(host, port, level_names=True)
        log_handler.addFilter(ServiceNameFilter())
        log_handler.addFilter(DiscardHealhCheckMessage())
    else:
        log_handler = logging.StreamHandler()

    logging.basicConfig(
        level=arguments.log_level,
        handlers=[log_handler],
        format='%(asctime)s %(levelname)s %(name)s\t%(message)s')

    # Update (overwrite) the global configuration with the local one.
    config = dict(automation_tools.utils.merge_dicts(arguments.config, arguments.local_config))

    if arguments.mode == "webhook":
        threading.excepthook = thread_exception_hook
        executor_thread = Bot(config, arguments.project_id, mr_queue)
        executor_thread.start()

        robocat.run()
    else:  # arguments.mode == "poll"
        executor = Bot(config, arguments.project_id, mr_queue)
        executor.run_poller()


if __name__ == '__main__':
    main()
