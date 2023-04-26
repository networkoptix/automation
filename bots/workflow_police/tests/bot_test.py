import pytest

from automation_tools.tests.fixtures import jira, repo_accessor
from bots.workflow_police.tests.fixtures import (
    police_test_repo,
    bot,
    project,
    workflow_enforcer,
    mr_states)


class TestPoliceBot:
    # Commits-to-branches relation is defined in bots/workflow_police/tests/fixtures.py.
    @pytest.mark.parametrize("jira_issues", [
        # Some ignored issues (including "bad" ones).
        [
            {"key": "VMS-1", "branches": ["master", "vms_5.0"]},
            {"key": "VMS-1", "branches": ["vms_5.1", "vms_5.0", "vms_5.0_patch", "master"]},
            {"key": "VMS-2", "branches": ["master", "vms_5.0_patch"]},
            {"key": "VMS-4", "branches": ["master"], "state": "In Review"},
            {"key": "NONEXISTENT-1", "branches": ["master"], "state": "Waiting for QA"},
        ],
        # Some good issues.
        [
            {"key": "VMS-1", "branches": ["master", "vms_5.0_patch"]},
            {"key": "VMS-2", "branches": ["master", "vms_5.0"], "labels": ["version_specific"]},
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

    # Commits-to-branches relation is defined in bots/workflow_police/tests/fixtures.py.
    @pytest.mark.parametrize("jira_issues", [
        # Closed issues.
        [{
            # Branch set is not allowed.
            "key": "VMS-1",
            "branches": ["master", "vms_5.0_patch"],
            "state": "Closed",
            "resolution": "Done",
        }, {
            # No commits in vms_5.1_patch branch.
            "key": "VMS-2",
            "branches": ["master", "vms_5.1", "vms_5.1_patch"],
            "state": "Closed",
            "resolution": "Fixed",
        }],
        # Issues waiting for QA.
        [{
            # Branch set is not allowed.
            "key": "VMS-1",
            "branches": ["master", "vms_5.0_patch"],
            "state": "Waiting for QA",
            "typ": "Task",
            "resolution": "Fixed",
        }, {
            # Branch set is not allowed.
            "key": "VMS-2",
            "branches": ["master", "vms_5.1", "vms_5.1_patch"],
            "state": "Waiting for QA",
            "typ": "Bug",
            "resolution": "Fixed",
        }],
    ])
    def test_issue_reopened(self, jira, jira_issues, bot):
        bot.run(run_once=True)
        for issue_data in jira_issues:
            issue_key = issue_data["key"]
            issue = jira.get_issue(issue_key)

            current_issue_state = issue._raw_issue.fields.status.name
            assert current_issue_state == "In Review", f'Issue "{issue_key}" was not reopend'
