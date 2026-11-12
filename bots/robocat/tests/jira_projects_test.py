## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

"""Every Jira Project of every Robocat repo: its Issues move after the merge (AUT-59)."""

from dataclasses import dataclass
from pathlib import Path

import automation_tools.jira
import pytest
from automation_tools.tests.fake_jira_server import (
    JIRA_URL,
    FakeJiraServer,
    Transition,
    jira_client_on,
)
from automation_tools.utils import merge_dicts, parse_config_file
from robocat.config import Config
from robocat.rule.post_processing_rule import PostProcessingRule

from tests.jira_status_rule_test import PROJECT_VERSIONS, TRANSITIONS, task

repo_configs = pytest.importorskip("robocat_config.repo_configs")  # Proprietary: no open source.
JIRA_PROJECT_CONFIGS = pytest.importorskip("robocat_config.jira_projects").JIRA_PROJECT_CONFIGS
GLOBAL_CONFIG = parse_config_file(Path(repo_configs.__file__).parents[1] / "config_template.yaml")
REPO_ROBOCAT_CONFIGS = {  # The config of each repo's Robocat: its entry over the global config.
    repo: Config(**dict(merge_dicts(GLOBAL_CONFIG, config)))
    for repo, config in repo_configs.REPO_CONFIGS.items()}


@dataclass(frozen=True)
class Workflow:
    """A Jira workflow when the MR is merged: the Issue status and the transitions from it."""

    name: str
    status: str
    transitions: tuple[Transition, ...]  # As Jira answered for a sample Issue on 2026-11-10.
    after_merge: str  # The status that Robocat moves the Issue to; `status`: Robocat leaves it.


STANDARD_BUG = Workflow(  # VMS-63404.
    "Bug or Task", "In Review", tuple(TRANSITIONS["VMS"]["In Review"]), "Waiting for QA")
INTERNAL = Workflow("Internal", "In Review", (  # VMS-61079: no QA step.
    Transition("91", "Back to development", "In progress"),
    Transition("71", "Close", "Closed"),
    Transition("81", "Stop development", "Open"),
), "Closed")
NCD_TASK = Workflow("Task", "In Review", (  # NCD-1293.
    Transition("91", "Back to development", "In progress"),
    Transition("71", "Close", "Closed"),
), "Closed")
INFRA = Workflow("Task", "In Review", tuple(TRANSITIONS["INFRA"]["In Review"]), "Closed")
AUT = Workflow("Bug", "In Review", (  # AUT-282.
    Transition("4", "Stop work", "Planned"),
    Transition("51", "Close", "Closed"),
), "Closed")
NXLIB = Workflow("Internal", "In Review", (  # NXLIB-549.
    Transition("11", "OPEN", "OPEN"),
    Transition("21", "Closed (1)", "Closed"),
    Transition("51", "back to development", "In Progress"),
), "Closed")
SRE = Workflow("Task", "Review", tuple(TRANSITIONS["SRE"]["Review"]), "Done")
NXUN = Workflow(  # No NXUN Issue was in "In Review" on 2026-11-10: its transitions are unknown.
    "Task", "In Development", tuple(TRANSITIONS["NXUN"]["In Development"]), "In Development")
NO_REVIEW = Workflow("No review", "In progress", (), "In progress")  # AIMP, NXMAPS, FT.
CLT = Workflow("No review", "In Progress", (), "In Progress")
DOCDB = Workflow("No review", "In progress", (), "In progress")

PROJECT_WORKFLOWS: dict[str, tuple[Workflow, ...]] = {  # The issue types seen in each Project.
    "VMS": (STANDARD_BUG, INTERNAL),
    "MOBILE": (STANDARD_BUG, INTERNAL),
    "CB": (STANDARD_BUG, INTERNAL),
    "CSS": (STANDARD_BUG, INTERNAL),
    "MDS": (STANDARD_BUG,),
    "SQ": (STANDARD_BUG,),  # No Issue visible: the standard workflow is assumed.
    "AMS": (STANDARD_BUG,),
    "CCS": (STANDARD_BUG,),
    "ANAS": (STANDARD_BUG,),
    "VMSDB": (STANDARD_BUG,),
    "CLOUD": (STANDARD_BUG,),
    "LIC": (STANDARD_BUG,),
    "CPS": (STANDARD_BUG,),
    "NCD": (NCD_TASK,),
    "INFRA": (INFRA,),
    "AUT": (AUT,),
    "NXLIB": (NXLIB,),
    "SRE": (SRE,),
    "NXUN": (NXUN,),
    "AIMP": (NO_REVIEW,),
    "NXMAPS": (NO_REVIEW,),
    "FT": (NO_REVIEW,),
    "CLT": (CLT,),
    "DOCDB": (DOCDB,),
}
REPO_PROJECT_WORKFLOWS = [  # Every Jira Project of every repo, with each of its workflows.
    pytest.param(project, workflow, id=f"{repo}:{project}:{workflow.name}")
    for repo, config in REPO_ROBOCAT_CONFIGS.items()
    for project in config.jira.project_mapping
    for workflow in PROJECT_WORKFLOWS.get(project, ())]


@pytest.mark.parametrize("repo", REPO_ROBOCAT_CONFIGS)
def test_repo_moves_the_issues_after_the_merge(repo):
    """Each repo's Robocat runs the rule that moves the Jira Issues after the merge."""
    assert PostProcessingRule.identifier in (REPO_ROBOCAT_CONFIGS[repo].enabled_rules or [])


@pytest.mark.parametrize("repo", REPO_ROBOCAT_CONFIGS)
def test_every_project_of_the_repo_has_its_names_and_workflows(repo):
    """Each Jira Project of the repo is in the dictionary of names and has a workflow here."""
    projects = list(REPO_ROBOCAT_CONFIGS[repo].jira.project_mapping)

    assert [project for project in projects if project not in JIRA_PROJECT_CONFIGS] == []
    assert [project for project in projects if project not in PROJECT_WORKFLOWS] == []


@pytest.mark.parametrize(("project", "workflow"), REPO_PROJECT_WORKFLOWS)
def test_merged_issue_moves_by_the_workflow_of_its_project(monkeypatch, project, workflow):
    """After the merge, Robocat moves the Issue by its Project's names and transitions."""
    key = f"{project}-1"
    server = FakeJiraServer(  # The versions of the other tests: Robocat caches one answer for all.
        [task(key, workflow.status)], {project: {workflow.status: list(workflow.transitions)}},
        PROJECT_VERSIONS)
    monkeypatch.setattr("jira.JIRA", jira_client_on(server))
    jira = automation_tools.jira.JiraAccessor(
        url=JIRA_URL, login="robocat", password="token", timeout=10, retries=0,
        project_keys=set(PROJECT_VERSIONS) | {project},
        custom_project_configs=JIRA_PROJECT_CONFIGS)

    jira.get_issue(key).try_finalize()

    assert server.status(key) == workflow.after_merge
