#!/usr/bin/env python3

import argparse
import jira
import logging
from pathlib import Path
import sys
from typing import Dict
import yaml

import automation_tools.git

SCRIPT_DESCRIPTION = """
This script is to be used for fixing "fixVersions" field of Jira Issues after adding a new gitlab
branch for the new release version. This is needed when the new repo branch and Jira version are
introduced for the upcoming release. After the new version (e.g. 6.0) is created but before the new
branch is created (e.g. vms_6.0 branch), one can use the script to find all the Issues which are
present in the master branch and should have the previous release version (e.g. 5.1) in theirs
"fixVersions" field. The rules for listing are as follows:

1. Extract from "dev/nx" repository all the commits mentioning "VMS-<something> and "SQ-<something"
    Issues, starting from the commit passed to the script in the "--fork-point" parameter (usually
    it is the last common commit between "master" branch and the previous release branch.
2. Get the information about all the Issues mentioned in the commits from Jira.
2. Skip (do nothing) the following Issues:
    - Issues without "master" in "fixVersions".
    - Issues with new version in theirs "fixVersions".
3. List all the Issues that do not have previous version in theirs "fixVersions" field.
"""

logger = logging.getLogger(__name__)


def run(
        git_config: Dict[str, str],
        jira_config: Dict[str, str],
        fork_point: str,
        new_version: str,
        previous_version: str):

    repo_accessor = automation_tools.git.Repo(**git_config)
    jira_accessor = jira.JIRA(
        jira_config["url"],
        basic_auth=(jira_config["login"], jira_config["password"]),
        max_retries=jira_config["retries"],
        timeout=jira_config["timeout"])

    recent_commits = repo_accessor.grep_recent_commits(
        '', f'{fork_point}..master', exact_rev=True)
    issue_keys = set()
    for commit in recent_commits:
        issues_string, *_ = commit.message.partition(':')
        for issue_key in issues_string.split(','):
            if issue_key.startswith('VMS-') or issue_key.startswith('SQ-'):
                issue_keys.add(issue_key.rstrip().lstrip())

    for issue_key in issue_keys:
        try:
            issue = jira_accessor.issue(issue_key)
        except jira.exceptions.JIRAError as e:
            logger.warning(f'Jira exception while getting Issue {issue_key}: {e}')
            continue

        version_set = set(v.name for v in issue.fields.fixVersions)
        issue_title = f"{issue.key}: {issue.fields.summary}"

        if "master" not in version_set:
            logger.debug(f'Issue "{issue_title}" does not have "master" in its fixVersions')
            continue

        if new_version in version_set:
            logger.debug(f'Issue "{issue_title}" already has "{new_version}" in its fixVersions')
            continue

        if previous_version not in version_set:
            logger.info(
                f'Issue "{issue_title}" does not have {previous_version} in its version set: '
                f'{version_set}.')


def main():
    parser = argparse.ArgumentParser(sys.argv[0])
    parser.add_argument(
        'config_file',
        help=(
            'Yaml file with configuration options, example: '
            'https://gitlab.nxvms.dev/dev/Automation/-/blob/master/bots/workflow_police/'
            'config.test.yaml. This parameter is mandatory.'))
    parser.add_argument(
        '--fork-point',
        type=str,
        required=True,
        help=('Last common commit between master and the new version branch '
              '(git merge-base master <new_version_branch>).'))
    parser.add_argument(
        '--new-version', type=str, required=True, help='New version (e.g. "6.0").')
    parser.add_argument(
        '--previous-version', type=str, required=True, help='Previous version (e.g. "5.1").')
    parser.add_argument(
        '--log-level', choices=logging._nameToLevel.keys(), default=logging.INFO,
        help='The level of the log file. Default value: INFO.')
    arguments = parser.parse_args()

    logging.basicConfig(
        level=arguments.log_level,
        format='%(message)s')

    with open(Path(arguments.config_file), 'r') as f:
        config = yaml.safe_load(f)
        f.close()

    run(
        git_config=config['vms_repo'],
        jira_config=config['jira'],
        fork_point=arguments.fork_point,
        new_version=arguments.new_version,
        previous_version=arguments.previous_version)


if __name__ == '__main__':
    main()
