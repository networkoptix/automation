import pytest
import re

from jira.exceptions import JIRAError

from robocat.rule.workflow_check_rule import WorkflowCheckRuleExecutionResult
from robocat.award_emoji_manager import AwardEmojiManager
from tests.fixtures import *
from tests.robocat_constants import DEFAULT_JIRA_ISSUE_KEY, DEFAULT_COMMIT

import automation_tools.checkers.config
from automation_tools.tests.fixtures import jira
from automation_tools.tests.mocks.resources import Version


class TestWorkflowCheckRule:
    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Commit without Jira Issue referencees in its title.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"],
        }], {
            "title": "Merge request without commits",
            "commits_list": [],
        }),
    ])
    def test_no_commits(self, workflow_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            execution_result = workflow_rule.execute(mr_manager)
            assert execution_result == WorkflowCheckRuleExecutionResult.no_commits

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Commit without Jira Issue referencees in its title.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"],
        }], {
            "title": "Merged merge request",
            "state": "merged",
        }),
    ])
    def test_merged(self, workflow_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            execution_result = workflow_rule.execute(mr_manager)
            assert execution_result == WorkflowCheckRuleExecutionResult.merged

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Commit without Jira Issue referencees in its title.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"],
        }], {
            "title": "WIP",
            "work_in_progress": True,
        }),
    ])
    def test_wip(self, workflow_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            execution_result = workflow_rule.execute(mr_manager)
            assert execution_result == WorkflowCheckRuleExecutionResult.work_in_progress

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Merge request is attached to one good Jira Issue.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"],
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request attached to Jira Issue"
        }),
        # Merge request is attached to two good Jira Issue.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.2_patch"]
        }, {
            "key": "VMS-667", "branches": ["master", "vms_4.2_patch"]
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, VMS-667: Multiple Jira Issues",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit 1 title\n",
                "files": {},
            }, {
                "sha": f"{DEFAULT_COMMIT['sha']}abc",
                "message": "VMS-667: commit 2 title",
                "files": {},
            }],
        }),
        # Merge request is attached to bad Jira Issue but ignored because of the label (1).
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["vms_4.2"],
            "labels": [automation_tools.checkers.config.VERSION_SPECIFIC_LABEL]
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request attached to bad Jira Issue"
        }),
        # Merge request is attached to bad Jira Issue but ignored because of the label (2).
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["vms_4.2"],
            "labels": [automation_tools.checkers.config.IGNORE_LABEL]
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request attached to bad Jira Issue"
        }),
        # Merge request is ignored because it is attached to the unsupported project.
        ([{
            "key": "CI-123", "branches": ["master"],
        }], {
            "title": "CI-123: Commit to CI",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": "CI-123: commit 1 title\n",
                "files": {},
            }],
        }),
        # Merge request is attached to one good Jira Issue and to one bad Jira Issue which is
        # ignored because of the label.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["vms_4.2"],
            "labels": [automation_tools.checkers.config.IGNORE_LABEL]
        }, {
            "key": "VMS-667", "branches": ["master", "vms_4.2", "vms_4.2_patch"]
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, VMS-667: Multiple Jira Issues",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit 1 title\n",
                "files": {},
            }, {
                "sha": f"{DEFAULT_COMMIT['sha']}abc",
                "message": "VMS-667: commit 2 title",
                "files": {},
            }],
        }),
        # Merge Request is attached to good Jira Issues from different projects with different
        # fixVersions.
        ([
            {"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.0"]},
            {"key": "VMS-667", "branches": ["master", "vms_5.0"]},
            {"key": "CB-1", "branches": ["master", "cloud_backend_20.1"]},
        ], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, VMS-667, CB-1: Multiple Jira Issues",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit 1 title\n",
                "files": {},
            }, {
                "sha": f"{DEFAULT_COMMIT['sha']}abc",
                "message": "VMS-667: commit 2 title",
                "files": {},
            }, {
                "sha": f"{DEFAULT_COMMIT['sha']}cde",
                "message": "CB-1: commit 2 title",
                "files": {},
            }],
        }),
        # Different commit message and title for squashed Merge Request with one commit.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.2_patch"]
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request title",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit title\n",
                "files": {},
            }],
        }),
    ])
    def test_jira_issues_are_ok(self, workflow_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            execution_result = workflow_rule.execute(mr_manager)
            assert execution_result == WorkflowCheckRuleExecutionResult.rule_execution_successfull

            emojis = mr.awardemojis.list()
            assert not any(e for e in emojis if e.name == AwardEmojiManager.BAD_ISSUE_EMOJI)

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Merge request is initially attached to bad Jira Issue.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["vms_4.2"],
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request attached to Jira Issue"
        }),
        # Merge request is initially attached to one good and one bad Jira Issue.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["vms_4.2"],
        }, {
            "key": "VMS-667", "branches": ["master"],
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, VMS-667: Merge request attached to Jira Issue",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit 1 title\n",
                "files": {},
            }, {
                "sha": f"{DEFAULT_COMMIT['sha']}abc",
                "message": "VMS-667: commit 2 title",
                "files": {},
            }],
        }),
    ])
    def test_remove_bad_issue_token(self, workflow_rule, mr, mr_manager, jira):
        assert not workflow_rule.execute(mr_manager)

        emojis = mr.awardemojis.list()
        assert any(e for e in emojis if e.name == AwardEmojiManager.BAD_ISSUE_EMOJI)

        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        issue.fields.fixVersions = [
            Version("master", "<master> Major release with a lot of tech debt")]

        execution_result = workflow_rule.execute(mr_manager)
        assert execution_result == WorkflowCheckRuleExecutionResult.rule_execution_successfull

        emojis = mr.awardemojis.list()
        assert not any(e for e in emojis if e.name == AwardEmojiManager.BAD_ISSUE_EMOJI)

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Merge request is attached to bad Jira Issue.
        ([{
            "key": "VMS-667", "branches": ["vms_4.2"],
        }], {
            "title": "VMS-667: Merge request attached to Jira Issue"
        }),
        # Merge request is attached to one good and two bad Jira Issues.
        ([
            {"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"]},
            {"key": "VMS-667", "branches": ["vms_4.2_patch"]},
            {"key": "VMS-668", "branches": ["vms_4.2"]},
        ], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, VMS-667, VMS-668: Multiple Jira Issues"
        }),
    ])
    def test_has_bad_version_set(self, workflow_rule, mr, mr_manager, jira):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not workflow_rule.execute(mr_manager)

            emojis = mr.awardemojis.list()
            assert any(e for e in emojis if e.name == AwardEmojiManager.BAD_ISSUE_EMOJI)

            assert len(mr.mock_comments()) == 1
            first_comment = mr.mock_comments()[0]
            has_bad_jira_issue_token = (
                f':{AwardEmojiManager.BAD_ISSUE_EMOJI}: Jira workflow check failed')
            assert has_bad_jira_issue_token in first_comment
            assert re.search(r"Bad `fixVersions` .+ VMS-66[7|8]: Version set", first_comment), (
                f"Error string is not found in {first_comment}")

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Merge Request is attached to good Jira Issues with different fixVersions.
        ([
            {"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.0", "vms_4.2_patch"]},
            {"key": "VMS-667", "branches": ["master", "vms_5.0"]},
        ], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, VMS-667: Multiple Jira Issues"
        }),
    ])
    def test_has_inconsistent_version_set(self, workflow_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not workflow_rule.execute(mr_manager)

            emojis = mr.awardemojis.list()
            assert any(e for e in emojis if e.name == AwardEmojiManager.BAD_ISSUE_EMOJI)

            assert len(mr.mock_comments()) == 1
            first_comment = mr.mock_comments()[0]
            has_bad_jira_issue_token = (
                f":{AwardEmojiManager.BAD_ISSUE_EMOJI}: Jira workflow check failed")
            assert has_bad_jira_issue_token in first_comment
            assert re.search(r"VMS-66[6|7]: `fixVersions` is inconsistent", first_comment), (
                f"Error string is not found in {first_comment}")

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Jira Issue in Merge Request title differs from Jira Issue from commit message.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"],
        }, {
            "key": f"{DEFAULT_JIRA_ISSUE_KEY}1", "branches": ["master"],
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request attached to Jira Issue",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}1: commit 1 title\n",
                "files": {},
            }],
        }),
        # No commit for one of the Jira Issues in the Merge Request title.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.2_patch"]
        }, {
            "key": "VMS-667", "branches": ["master", "vms_4.2_patch"]
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, VMS-667: Multiple Jira Issues",
        }),
        # Different commit message and title for non-squashed Merge Request with one commit.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.2_patch"]
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request title",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit title\n",
                "files": {},
            }],
            "squash": False,
        }),
    ])
    def test_commit_messages_are_not_ok(self, workflow_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not workflow_rule.execute(mr_manager)

            emojis = mr.awardemojis.list()
            assert any(e for e in emojis if e.name == AwardEmojiManager.BAD_ISSUE_EMOJI)

            comments = mr.mock_comments()
            assert len(comments) == 1
            messages = [
                f"### :{AwardEmojiManager.BAD_ISSUE_EMOJI}: Commit message check failed",
                f"### :{AwardEmojiManager.BAD_ISSUE_EMOJI}: Bad commit title",
            ]
            assert comments[0].startswith(messages[0]) or comments[0].startswith(messages[1]), (
                f"Unexpected comment: {comments[0]!r}")
