## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import logging
from typing import Any

import automation_tools.checkers.config
import automation_tools.jira
import pytest
import requests
from automation_tools.checkers.config import AllowedVersionSet
from automation_tools.jira_helpers import (
    JIRA_STATUS_CLOSED,
    JIRA_STATUS_OPEN,
    JIRA_STATUS_PROGRESS,
    JIRA_STATUS_REVIEW,
    JiraProjectConfigOverride,
)
from automation_tools.tests.fake_jira_server import (
    JIRA_URL,
    NXLIB_ISSUE,
    NXLIB_START_DEVELOPMENT,
    NXLIB_TRANSITIONS,
    FakeJiraServer,
    Transition,
    jira_client_on,
)
from automation_tools.tests.fixtures import repo_accessor, repo_versions
from automation_tools.tests.gitlab_constants import DEFAULT_JIRA_ISSUE_KEY, DEFAULT_USER
from robocat.bot import Bot
from robocat.comments import Emoji
from robocat.rule.base_rule import BaseRule
from robocat.rule.jira_status_rule import JiraStatusRule
from robocat.rule.workflow_check_rule import WorkflowCheckRule

from tests.fixtures import (
    bot_config,
    mr,
    mr_manager,
    mr_state,
    project,
    project_manager,
)

DRAFT_MR = {"title": f"{DEFAULT_JIRA_ISSUE_KEY}: Draft work", "work_in_progress": True}
READY_MR = {"title": f"{DEFAULT_JIRA_ISSUE_KEY}: Ready work"}
VMS_PROJECT = {"key": "VMS", "id": "10100", "name": "VMS"}
VMS_MASTER = {  # A Fix Version of VMS as Jira answers it: the description names the branch.
    "self": f"{JIRA_URL}/rest/api/2/version/14305", "id": "14305", "name": "master (6.2)",
    "description": "<master> Ongoing development branch", "archived": False, "released": False,
    "projectId": 10100,
}
PROJECT_VERSIONS = {  # Robocat caches them for 10 minutes for all accessors: one answer for all.
    "VMS": [VMS_MASTER],
    "NXLIB": [],
    "INFRA": [],
    "SRE": [],
    "NXUN": [],
}
PROJECT_CONFIGS: dict[str, JiraProjectConfigOverride] = {  # Names as in robocat_config.
    "INFRA": {},  # The standard names, like most Projects.
    "SRE": {"statuses": {
        JIRA_STATUS_OPEN: "To Do",
        JIRA_STATUS_PROGRESS: "In Progress",
        JIRA_STATUS_REVIEW: "Review",
        JIRA_STATUS_CLOSED: "Done",
    }},
    "NXUN": {"statuses": {
        JIRA_STATUS_OPEN: "To Do",
        JIRA_STATUS_PROGRESS: "In Development",
        JIRA_STATUS_CLOSED: "Done",
    }},
}
ASSIGNEE = {  # The Jira user of the MR author: the workflow rule compares the names.
    "accountId": DEFAULT_USER["username"], "displayName": DEFAULT_USER["name"],
    "emailAddress": DEFAULT_USER["email"], "active": True,
}
VMS_START_DEVELOPMENT = Transition("11", "Start Development", "In progress")
VMS_READY_TO_REVIEW = Transition("31", "Ready to Review", "In Review")
VMS_REVIEW_FAILED = Transition("41", "Review Failed", "In progress")
INFRA_STOP_WORK = Transition("4", "Stop work", "Open")
INFRA_CLOSE = Transition("51", "Close", "Closed")
SRE_DONE = Transition("31", "Done", "Done")
NXUN_READY_FOR_REVIEW = Transition("18", "MR created and ready for review", "In Review")
TRANSITIONS = {  # From each status, as Jira answered for VMS Bugs and for NXLIB-434.
    "VMS": {
        "Open": [  # VMS-63480.
            Transition("201", "Reject", "Closed"),
            VMS_START_DEVELOPMENT,
            VMS_READY_TO_REVIEW,
            Transition("161", "Feedback", "Feedback"),
            Transition("171", "Done Externally", "Waiting for QA"),
            Transition("211", "Block", "Blocked"),
            Transition("221", "Select for development", "Selected for Development"),
        ],
        "In progress": [  # VMS-59758.
            Transition("201", "Reject", "Closed"),
            Transition("21", "Stop Development", "Open"),
            VMS_READY_TO_REVIEW,
            Transition("161", "Feedback", "Feedback"),
            Transition("171", "Done Externally", "Waiting for QA"),
            Transition("211", "Block", "Blocked"),
            Transition("221", "Select for development", "Selected for Development"),
        ],
        "In Review": [  # VMS-63404.
            Transition("201", "Reject", "Closed"),
            VMS_REVIEW_FAILED,
            Transition("61", "Merged", "Waiting for QA"),
        ],
    },
    "INFRA": {"In Review": [INFRA_STOP_WORK, INFRA_CLOSE]},  # INFRA-723.
    "SRE": {"Review": [  # SRE-2285: all transitions of SRE are global.
        Transition("3", "Blocked", "Blocked"),
        Transition("4", "Abandoned", "Abandoned"),
        Transition("11", "To Do", "To Do"),
        Transition("21", "In Progress", "In Progress"),
        SRE_DONE,
        Transition("32", "Needs Info", "Needs Info"),
        Transition("33", "Review", "Review"),
    ]},
    "NXUN": {"In Development": [  # NXUN-1604.
        Transition("5", "abandoned", "abandoned"),
        Transition("32", "Dev Blocked", "Dev Blocked"),
        Transition("11", "pause development", "To Do"),
        NXUN_READY_FOR_REVIEW,
        Transition("25", "not seeing the issue", "Waiting for QA"),
    ]},
    **NXLIB_TRANSITIONS,
}


def vms_issue(status: str, key: str = DEFAULT_JIRA_ISSUE_KEY, **fields: Any) -> dict[str, Any]:
    """A VMS Bug as Jira answers it, in a status; other fields replace the usual ones."""
    return {
        "id": key.partition("-")[2], "key": key, "self": f"{JIRA_URL}/rest/api/2/issue/{key}",
        "fields": {
            "status": {"name": status}, "project": VMS_PROJECT,
            "issuetype": {"name": "Bug", "subtask": False}, "labels": [],
            "fixVersions": [VMS_MASTER], "assignee": ASSIGNEE, "resolution": None, **fields,
        },
    }


def in_bot_order(*rules: BaseRule) -> list[BaseRule]:
    """The rules in the order that the bot runs them before a merge."""
    return sorted(rules, key=lambda rule: Bot.PRE_MERGE_RULES.index(rule.identifier))


@pytest.fixture
def jira_server(jira_issues) -> FakeJiraServer:
    """The fake Jira server with the Issues of the test."""
    return FakeJiraServer(jira_issues, TRANSITIONS, PROJECT_VERSIONS)


@pytest.fixture
def jira_accessor(jira_server, monkeypatch) -> automation_tools.jira.JiraAccessor:
    """Robocat's real JiraAccessor and jira client; they talk to the fake server."""
    monkeypatch.setattr("jira.JIRA", jira_client_on(jira_server))
    return automation_tools.jira.JiraAccessor(
        url=JIRA_URL, login="robocat", password="token", timeout=10, retries=0,
        project_keys=set(PROJECT_VERSIONS), custom_project_configs=PROJECT_CONFIGS)


@pytest.fixture
def jira_status_rule(bot_config, project_manager, jira_accessor) -> JiraStatusRule:
    """The rule with the real JiraAccessor."""
    return JiraStatusRule(bot_config, project_manager, jira_accessor)


@pytest.fixture
def workflow_rule(bot_config, project_manager, jira_accessor, monkeypatch) -> WorkflowCheckRule:
    """The workflow rule with the real JiraAccessor; VMS allows the master version alone."""
    monkeypatch.setattr(automation_tools.checkers.config, "ALLOWED_VERSIONS_SETS", {
        "VMS": [AllowedVersionSet({VMS_MASTER["name"]}, "Next release development")]})
    return WorkflowCheckRule(bot_config, project_manager, jira_accessor)


class TestJiraStatusRule:
    """The Jira Issue follows the draft state of its MR (AUT-17), through the real jira library."""

    @pytest.mark.parametrize(("jira_issues", "mr_state", "transitions_made", "final_status"), [
        # Draft MR: an Open Issue goes to In progress.
        ([vms_issue("Open")], DRAFT_MR, [VMS_START_DEVELOPMENT], "In progress"),
        # Ready MR: an In progress Issue goes to In Review.
        ([vms_issue("In progress")], READY_MR, [VMS_READY_TO_REVIEW], "In Review"),
        # Ready at once: an Open Issue goes to In progress, then on to In Review.
        ([vms_issue("Open")], READY_MR, [VMS_START_DEVELOPMENT, VMS_READY_TO_REVIEW], "In Review"),
        # Draft again: an In Review Issue goes back to In progress.
        ([vms_issue("In Review")], DRAFT_MR, [VMS_REVIEW_FAILED], "In progress"),
        # NXLIB's own names: "OPEN" goes to "In Progress".
        ([NXLIB_ISSUE], {"title": "NXLIB-434: Draft work", "work_in_progress": True},
         [NXLIB_START_DEVELOPMENT], "In Progress"),
    ])
    def test_issue_follows_the_draft_state(self, jira_status_rule, jira_server, mr_manager,
                                           jira_issues, transitions_made, final_status):
        """Jira gets exactly the transitions of the moves in one run; the next run sends none."""
        result = jira_status_rule.execute(mr_manager)

        assert result == JiraStatusRule.ExecutionResult.rule_execution_successful
        assert jira_server.transitions_made == transitions_made
        assert jira_server.status(jira_issues[0]["key"]) == final_status
        jira_status_rule.execute(mr_manager)  # The next event of the MR.
        assert jira_server.transitions_made == transitions_made

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [([vms_issue("Open")], READY_MR)])
    def test_log_names_the_jira_statuses(self, jira_status_rule, mr_manager, caplog):
        """The log names the statuses as Jira shows them, not by Robocat's standard keys."""
        caplog.set_level(logging.INFO, logger=JiraStatusRule.__module__)

        jira_status_rule.execute(mr_manager)

        moves = [record.getMessage().partition(": ")[2] for record in caplog.records
                 if record.name == JiraStatusRule.__module__]
        assert moves == [
            f"Moved the Jira Issue {DEFAULT_JIRA_ISSUE_KEY} from 'Open' to 'In progress': "
            "the MR is ready.",
            f"Moved the Jira Issue {DEFAULT_JIRA_ISSUE_KEY} from 'In progress' to 'In Review': "
            "the MR is ready.",
        ]

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Already right for the MR.
        ([vms_issue("In progress")], DRAFT_MR),
        ([vms_issue("In Review")], READY_MR),
        # A finished Issue: the workflow rule warns about it.
        ([vms_issue("Waiting for QA")], DRAFT_MR),
        ([vms_issue("Closed")], READY_MR),
        # An Epic, and an Issue with the ignore label.
        ([vms_issue("Open", issuetype={"name": "Epic", "subtask": False})], DRAFT_MR),
        ([vms_issue("Open", labels=[automation_tools.checkers.config.IGNORE_LABEL])], DRAFT_MR),
    ])
    def test_issue_stays(self, jira_status_rule, jira_server, mr_manager, jira_issues):
        """The Issue keeps its status; the rule does not block the MR."""
        result = jira_status_rule.execute(mr_manager)

        assert result == JiraStatusRule.ExecutionResult.rule_execution_successful
        assert result  # Never blocks the merge.
        assert jira_server.transitions_made == []
        issue = jira_issues[0]
        assert jira_server.status(issue["key"]) == issue["fields"]["status"]["name"]

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # A Jira project that Robocat does not know.
        ([], {"title": "XYZ-1: Draft work", "work_in_progress": True}),
    ])
    def test_unknown_project_is_not_asked(self, jira_status_rule, jira_server, mr_manager):
        """Robocat does not ask Jira about an Issue of a project that it does not know."""
        result = jira_status_rule.execute(mr_manager)

        assert result == JiraStatusRule.ExecutionResult.rule_execution_successful
        assert jira_server.issue_requests() == []

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # A follow-up MR that Robocat made.
        ([vms_issue("Open")], {**DRAFT_MR, "emojis_list": [Emoji.FOLLOWUP_MERGE_REQUEST]}),
        # A merged MR, and an MR without commits.
        ([vms_issue("In progress")], {**READY_MR, "state": "merged"}),
        ([vms_issue("Open")], {**DRAFT_MR, "commits_list": []}),
    ])
    def test_not_eligible(self, jira_status_rule, jira_server, mr_manager):
        """Follow-up, merged and empty MRs do not move their Issues: Jira is not asked."""
        result = jira_status_rule.execute(mr_manager)

        assert result == JiraStatusRule.ExecutionResult.not_eligible
        assert result  # Never blocks the merge.
        assert jira_server.issue_requests() == []

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # The MR names an Issue that Jira does not have.
        ([vms_issue("Open")], {"title": "VMS-999999: Draft work", "work_in_progress": True}),
    ])
    def test_jira_error_does_not_stop_the_mr(self, jira_status_rule, jira_server, mr_manager):
        """Jira answers 404 for the Issue: the error is only logged, and nothing moves."""
        result = jira_status_rule.execute(mr_manager)

        assert result == JiraStatusRule.ExecutionResult.rule_execution_successful
        assert ("GET", "/rest/api/2/issue/VMS-999999") in jira_server.requests
        assert jira_server.transitions_made == []

    @pytest.mark.parametrize("failure", [
        requests.exceptions.ConnectionError("Connection refused"),
        requests.exceptions.ReadTimeout("Read timed out"),
    ])
    @pytest.mark.parametrize(("jira_issues", "mr_state"), [([vms_issue("Open")], DRAFT_MR)])
    def test_jira_network_error_does_not_stop_the_mr(
            self, jira_status_rule, jira_server, mr_manager, failure):
        """Jira is not reachable: the jira library raises the requests error; it is only logged."""
        jira_server.failure = failure

        result = jira_status_rule.execute(mr_manager)

        assert result == JiraStatusRule.ExecutionResult.rule_execution_successful
        assert jira_server.requests  # The real jira library did try to reach Jira.
        assert jira_server.transitions_made == []

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        ([vms_issue("Open")],
         {"title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request attached to Jira Issue",
          "work_in_progress": True}),
    ])
    def test_workflow_rule_does_not_warn_after_the_moves(
            self, jira_status_rule, workflow_rule, jira_server, mr, mr_manager):
        """Draft, then ready: the Issue moves first, so the workflow rule finds no bad status."""
        rules = in_bot_order(workflow_rule, jira_status_rule)

        draft_results = {rule.identifier: rule.execute(mr_manager) for rule in rules}
        mr.work_in_progress = False  # The developer marks the MR as ready.
        ready_results = {rule.identifier: rule.execute(mr_manager) for rule in rules}

        assert draft_results["workflow"] == WorkflowCheckRule.ExecutionResult.work_in_progress
        assert ready_results["workflow"] == (
            WorkflowCheckRule.ExecutionResult.rule_execution_successful)
        assert jira_server.transitions_made == [VMS_START_DEVELOPMENT, VMS_READY_TO_REVIEW]
        assert jira_server.status(DEFAULT_JIRA_ISSUE_KEY) == "In Review"
        assert not any("has status" in comment for comment in mr.mock_comments())

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        ([vms_issue("Open")],
         {"title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request attached to Jira Issue"}),
    ])
    def test_workflow_rule_does_not_warn_on_a_ready_mr(
            self, jira_status_rule, workflow_rule, jira_server, mr, mr_manager):
        """Ready at once: in the same run, the Issue moves before the workflow rule checks it."""
        results = {
            rule.identifier: rule.execute(mr_manager)
            for rule in in_bot_order(workflow_rule, jira_status_rule)}

        assert results["workflow"] == WorkflowCheckRule.ExecutionResult.rule_execution_successful
        assert jira_server.transitions_made == [VMS_START_DEVELOPMENT, VMS_READY_TO_REVIEW]
        assert jira_server.status(DEFAULT_JIRA_ISSUE_KEY) == "In Review"
        assert not any("has status" in comment for comment in mr.mock_comments())


def task(key: str, status: str) -> dict[str, Any]:
    """A Task of another Jira Project, without Fix Versions, as Jira answers it."""
    project = key.partition("-")[0]
    return vms_issue(status, key, project={"key": project, "name": project},
                     issuetype={"name": "Task", "subtask": False}, fixVersions=[])


class TestProjectWorkflows:
    """The status names of each Jira Project (AUT-59): Robocat moves the Issues by these names."""

    @pytest.mark.parametrize(("jira_issues", "transition"), [
        ([task("SRE-2285", "Review")], SRE_DONE),  # SRE's own names: "Review" and "Done".
        ([task("INFRA-723", "In Review")], INFRA_CLOSE),  # The standard names, without QA.
    ])
    def test_merged_issue_goes_to_the_done_status_of_its_project(
            self, jira_accessor, jira_server, jira_issues, transition):
        """After the merge, the Issue moves by the transition to the done status of its Project."""
        key = jira_issues[0]["key"]

        assert jira_accessor.get_issue(key).try_finalize() is True

        assert jira_server.transitions_made == [transition]
        assert jira_server.status(key) == transition.status
        assert [issue_key for issue_key, _ in jira_server.comments] == [key]

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        ([task("NXUN-1604", "In Development")], {"title": "NXUN-1604: Ready work"}),
    ])
    def test_ready_mr_moves_the_issue_by_the_names_of_its_project(
            self, bot_config, project_manager, jira_accessor, jira_server, mr_manager):
        """NXUN calls its progress status "In Development": a ready MR moves the Issue on."""
        bot_config.jira.project_mapping["NXUN"] = "nx-connect-ui"  # As for dev/nx-connect-ui.

        JiraStatusRule(bot_config, project_manager, jira_accessor).execute(mr_manager)

        assert jira_server.transitions_made == [NXUN_READY_FOR_REVIEW]
        assert jira_server.status("NXUN-1604") == "In Review"
