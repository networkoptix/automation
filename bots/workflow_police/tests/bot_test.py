import pytest

from automation_tools.tests.fixtures import jira, repo_accessor
from bots.workflow_police.tests.fixtures import (
    police_test_repo,
    bot,
    project,
    workflow_enforcer,
    mr_states)


class TestPoliceBot:
    @pytest.mark.parametrize("jira_issues", [
        # Some ignored issues (including "bad" ones).
        [
            {"key": "VMS-1", "branches": ["master", "vms_4.2"]},
            {"key": "VMS-1", "branches": ["vms_5.0_patch", "vms_4.2", "vms_4.2_patch", "master"]},
            {"key": "VMS-2", "branches": ["master", "vms_4.2_patch"]},
            {"key": "VMS-4", "branches": ["master"], "state": "In Review"},
            {"key": "NONEXISTENT-1", "branches": ["master"], "state": "Waiting for QA"},
        ],
        # Some good issues.
        [
            {"key": "VMS-1", "branches": ["master", "vms_4.2_patch"]},
            {"key": "VMS-2", "branches": ["master", "vms_4.2"], "labels": ["version_specific"]},
        ],
    ])
    def test_issue_not_changed(self, jira, jira_issues, bot):
        bot.run(run_once=True)
        for issue_data in jira_issues:
            issue_key = issue_data["key"]
            issue = jira.get_issue(issue_key)

            initial_issue_state = issue_data.get("state", "Open")
            current_issue_state = issue._raw_issue.fields.status.name
            assert initial_issue_state == current_issue_state, (
                f'State of issue "{issue_key}" was changed from '
                f'"{initial_issue_state}" to "{current_issue_state}"')

    @pytest.mark.parametrize("jira_issues", [
        # Close issues.
        [{
            "key": "VMS-1",
            "branches": ["master", "vms_4.2"],
            "state": "Closed",
            "resolution": "Done",
        }, {
            "key": "VMS-2",
            "branches": ["master", "vms_4.2_patch"],
            "state": "Closed",
            "resolution": "Fixed",
        }],
        # Issues waiting for QA.
        [{
            "key": "VMS-1",
            "branches": ["vms_5.0_patch", "vms_4.2", "vms_4.2_patch", "master"],
            "state": "Waiting for QA",
            "typ": "Task",
        }, {
            "key": "VMS-2",
            "branches": ["vms_5.0_patch", "vms_4.2", "vms_4.2_patch", "master"],
            "state": "Waiting for QA",
            "typ": "Bug",
        }],
    ])
    def test_issue_reopened(self, jira, jira_issues, bot):
        bot.run(run_once=True)
        for issue_data in jira_issues:
            issue_key = issue_data["key"]
            issue = jira.get_issue(issue_key)

            current_issue_state = issue._raw_issue.fields.status.name
            assert current_issue_state == "In Review", f'Issue "{issue_key}" was not reopend'
