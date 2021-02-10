import gitlab

import sys
import time
from pathlib import Path

import argparse
import logging
import graypy

import automation_tools.utils
import automation_tools.bot_info
from automation_tools.jira import JiraAccessor, JiraError
from robocat.project_manager import ProjectManager
from robocat.merge_request_manager import MergeRequestManager
from robocat.pipeline import PlayPipelineError
from robocat.rule.essential_rule import EssentialRule
from robocat.rule.open_source_check_rule import OpenSourceCheckRule
from robocat.rule.followup_rule import FollowupRule

logger = logging.getLogger(__name__)


class ServiceNameFilter(logging.Filter):
    @staticmethod
    def filter(record):
        record.service_name = "Workflow Robocat"
        return True


class Bot:
    def __init__(self, config, project_id, dry_run):
        self._gitlab = gitlab.Gitlab.from_config("nx_gitlab")
        self._gitlab.auth()
        self._username = self._gitlab.user.username
        self._dry_run = dry_run

        self._project_manager = ProjectManager(
            gitlab_project=self._gitlab.projects.get(project_id),
            current_user=self._username,
            dry_run=dry_run)

        self._rule_essential = EssentialRule()
        self._rule_open_source_check = OpenSourceCheckRule(
                project_manager=self._project_manager,
                **config['open_source_check_rule'])
        self._rule_followup = FollowupRule(
            project_manager=self._project_manager,
            jira=JiraAccessor(**config["jira"]))

    def handle(self, mr_manager: MergeRequestManager):
        essential_rule_check_result = self._rule_essential.execute(mr_manager)
        logger.debug(f"{mr_manager}: {essential_rule_check_result}")

        opens_source_check_result = self._rule_open_source_check.execute(mr_manager)
        logger.debug(f"{mr_manager}: {opens_source_check_result}")

        if not essential_rule_check_result or not opens_source_check_result:
            return

        mr_manager.update_unfinished_processing_flag(True)
        mr_manager.merge_or_rebase()
        followup_result = self._rule_followup.execute(mr_manager)
        logger.debug(f"{mr_manager}: {followup_result}")
        mr_manager.update_unfinished_processing_flag(False)

    def start(self, mr_poll_rate):
        logger.info(
            f"Robocat revision {automation_tools.bot_info.revision()}. Started for project "
            f"[{self._project_manager.data.name}] with {mr_poll_rate} secs poll rate"
            f"{' (--dry-run)' if self._dry_run else ''}")

        for mr_manager in self.get_merge_requests_manager(mr_poll_rate):
            try:
                self.handle(mr_manager)
            except gitlab.exceptions.GitlabOperationError as e:
                logger.warning(f"{mr_manager}: Gitlab error: {e}")
            except JiraError as e:
                logger.warning(f"{mr_manager}: Jira error: {e}")
            except PlayPipelineError as e:
                logger.warning(f"{mr_manager}: Error: {e}")

    def get_merge_requests_manager(self, mr_poll_rate):
        while True:
            start_time = time.time()
            for mr in self._project_manager.get_next_unfinished_merge_request():
                yield MergeRequestManager(mr)
            for mr in self._project_manager.get_next_open_merge_request():
                yield MergeRequestManager(mr)

            sleep_time = max(0, start_time + mr_poll_rate - time.time())
            time.sleep(sleep_time)


def main():
    parser = argparse.ArgumentParser(sys.argv[0])
    parser.add_argument('-c', '--config', help="Config file with all options", default={})
    parser.add_argument('-p', '--project-id', help="ID of project in gitlab (2 for dev/nx)", type=int, required=True)
    parser.add_argument('--log-level', help="Logs level", choices=logging._nameToLevel.keys(), default=logging.INFO)
    parser.add_argument('--dry-run', help="Don't change any MR states", action="store_true")
    parser.add_argument('--mr-poll-rate', help="Merge Requests poll rate, seconds (default: 30)", type=int, default=30)
    parser.add_argument('--graylog', help="Hostname of Graylog service")
    arguments = parser.parse_args()

    logging.basicConfig(
        level=arguments.log_level,
        format='%(asctime)s %(levelname)s %(name)s\t%(message)s')
    if arguments.graylog:
        host, port = arguments.graylog.split(":")
        graylog_handler = graypy.GELFTCPHandler(host, port, level_names=True)
        graylog_handler.addFilter(ServiceNameFilter())
        logging.getLogger().addHandler(graylog_handler)
        logger.debug(f"Logging to Graylog at {arguments.graylog}")

    try:
        if arguments.config:
            config = automation_tools.utils.parse_config_file(Path(arguments.config))
        else:
            config = {}
        bot = Bot(config, arguments.project_id, arguments.dry_run)
        bot.start(arguments.mr_poll_rate)
    except Exception as e:
        logger.error(f'Crashed with exception: {e}', exc_info=1)
        sys.exit(1)


if __name__ == '__main__':
    main()
