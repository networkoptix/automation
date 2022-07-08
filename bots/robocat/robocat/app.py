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
from robocat.bot import Bot, GitlabEventType, GitlabEventData

logger = logging.getLogger(__name__)

robocat = GitLabBot('Robocat')
mr_queue = queue.SimpleQueue()


AsyncCallback = Callable[..., Awaitable[None]]


def add_event_hook(event_type: str) -> Callable[[AsyncCallback], AsyncCallback]:
    def decorator(func: AsyncCallback) -> AsyncCallback:
        async def event_processor(event, *_):
            try:
                await func(event)
            except Exception as e:
                logger.error(f"Crashed while processing {event_type} event: {e!r}")

        return robocat.router.register(f"{event_type} Hook")(event_processor)

    return decorator


@add_event_hook("Merge Request")
async def merge_request_event(event):
    mr_id = event.data["object_attributes"]["iid"]
    logger.debug(f'Got Merge Request event. MR id: {mr_id}')
    mr_queue.put(GitlabEventData(mr_id=mr_id, event_type=GitlabEventType.merge_request))


@add_event_hook("Pipeline")
async def pipeline_event(event):
    mr_object = event.data.get("merge_request")
    if mr_object:
        mr_id = mr_object['iid']
        logger.debug(f'Got Pipeline event. MR id: {mr_id}')
        raw_pipeline_status = event.data["object_attributes"]["status"]
        mr_queue.put(GitlabEventData(
            mr_id=mr_id,
            event_type=GitlabEventType.pipeline,
            raw_pipeline_status=raw_pipeline_status))
    else:
        logger.debug(
            f"Got Pipeline event without the 'merge_request' object. Raw data: {event.data!r}")


@add_event_hook("Note")
async def note_event(event):
    mr_object = event.data.get("merge_request")
    if mr_object:
        mr_id = event.data['merge_request']['iid']
        logger.debug(f'Got Note event. MR id: {mr_id}')
        comment = event.data["object_attributes"]["note"]
        mr_queue.put(GitlabEventData(
            mr_id=mr_id,
            event_type=GitlabEventType.comment,
            added_comment=comment))
    else:
        logger.debug(
            f"Got Note event without the 'merge_request' object. Raw data: {event.data!r}")


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
    parser.add_argument('-c', '--config', help="Config file with all options", default={})
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

    if arguments.config:
        config = automation_tools.utils.parse_config_file(Path(arguments.config))
    else:
        config = {}

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
