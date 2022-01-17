#!/usr/bin/env python3

import sys
from pathlib import Path
import argparse
import logging
from typing import Dict

import yaml
import jira

from config import (
    JIRA_PROJECTS, NEW_VERSION_NAME, PREVIOUS_RELEASE_VERSION_NAMES, VERSION_SETS_TO_PATCH)

RESOLUTION_NAMES_TO_SKIP = {"Rejected", "Duplicate", "Won't Do", "Cannot Reproduce", "Declined"}

SCRIPT_DESCRIPTION = """
This script is to be used for fixing "fixVersions" field of Jira Issues after adding a new gitlab
branch for the new release version. This is needed when the new repo branch and Jira version are
introduced for the upcoming release. After the branch and the version are created (e.g. 5.0 version
and vms_5.0 branch), one can use the script to find (or find and patch) all Issues which are
present in the vms_5.0 branch and should have the 5.0 version added in Jira. Also the script
detects the Issues that have "bad" value in "fixVersions" field. The rules for listing/patching are
as follows:

1. List as eligible for patching (unless in dry-run mode) the following Issues:
    - Issues which "fixVerions" value is equal to one of the values listed in VERSION_SETS_TO_PATCH
        variable.
2. Skip (do nothing) the following Issues:
    - Issues without "master" in "fixVersions".
    - Issues which "fixVerions" value contains one of the values listed in
        PREVIOUS_RELEASE_VERSION_NAMES variable.
 - Rejected or Duplicated Issues.
3. List as suspicious all the other Issues.

Configuration:

The variables mentioned above are inside the file config.py in the same directory with the script
itself. There are some other configuration variables as well (see comments in config.py).
"""

logger = logging.getLogger(__name__)


def run(config: Dict[str, str], depth_in_days: int, dry_run: bool = False):
    jira_handler = jira.JIRA(
        server=config["url"], basic_auth=(config["login"], config["password"]),
        max_retries=config["retries"], timeout=config["timeout"])

    issues = jira_handler.search_issues(
        f"project in({','.join(JIRA_PROJECTS)}) AND created >= -{depth_in_days}d",
        maxResults=None)
    for issue in issues:
        version_set = set(v.name for v in issue.fields.fixVersions)
        issue_title = f"{issue.key}: {issue.fields.summary}"

        if "master" not in version_set:
            logger.debug(f'Issue "{issue_title}" does not have "master" in its fixVersions')
            continue

        if NEW_VERSION_NAME in version_set:
            logger.debug(
                f'Issue "{issue_title}" alreary has "{NEW_VERSION_NAME}" '
                'in its fixVersions')
            continue

        if version_set.intersection(PREVIOUS_RELEASE_VERSION_NAMES):
            logger.debug(
                f'Issue "{issue_title}" has a suspicious version set in '
                f'fixVersions: {version_set}')
            continue

        resolution = issue.fields.resolution
        if resolution is not None and resolution.name in RESOLUTION_NAMES_TO_SKIP:
            logger.debug(f'Issue "{issue_title}" is {resolution.name}')
            continue

        if version_set in VERSION_SETS_TO_PATCH:
            upgraded_version_set = version_set.union({NEW_VERSION_NAME})
            if not dry_run:
                logger.info(
                    f'Patching fixVersions for Issue "{issue_title}":'
                    f" {version_set} -> {upgraded_version_set}")
                issue.update(fields={"fixVersions": [{"name": v} for v in upgraded_version_set]})
            else:
                logger.info(
                    f'fixVersions for Issue "{issue_title}" is to be patched:'
                    f" {version_set} -> {upgraded_version_set}")

        else:
            logger.warning(
                f'Issue "{issue_title}" has a suspicious version set in '
                f'fixVersions: {version_set}')


def main():
    parser = argparse.ArgumentParser(
        sys.argv[0], description=SCRIPT_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "config_file",
        help=(
            "Yaml file with configuration options, example: "
            "https://gitlab.lan.hdw.mx/dev/Automation/-/blob/master/bots/workflow_police/"
            'config.test.yaml. This parameter is mandatory.'))
    parser.add_argument(
        "--days", type=int, default=45,
        help=(
            'Determines the "depths" of Jira Issue scan. The Issues that are created this many '
            "days before the current date WILL NOT be scanned. Default value: 45."))
    parser.add_argument(
        "--no-dry-run", action="store_true",
        help=(
            "Add this option to do real changes. If this option is not set, the script will only "
            "print the Issues that are to be updated."))
    parser.add_argument(
        "--log-level", choices=logging._nameToLevel.keys(), default=logging.INFO,
        help="The level of the log file. Default value: INFO.")
    arguments = parser.parse_args()

    logging.basicConfig(
        level=arguments.log_level,
        format='%(asctime)s %(levelname)s\t%(message)s')

    with open(Path(arguments.config_file), 'r') as f:
        config = yaml.safe_load(f)
        f.close()

    run(config=config["jira"], depth_in_days=arguments.days, dry_run=(not arguments.no_dry_run))


if __name__ == '__main__':
    main()
