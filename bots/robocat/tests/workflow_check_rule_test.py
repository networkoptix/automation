import pytest
import re

from robocat.rule.workflow_check_rule import WorkflowCheckRule
from robocat.award_emoji_manager import AwardEmojiManager
from tests.fixtures import *
from automation_tools.tests.gitlab_constants import DEFAULT_JIRA_ISSUE_KEY, DEFAULT_COMMIT

import automation_tools.checkers.config
from automation_tools.tests.fixtures import jira
from automation_tools.tests.mocks.resources import Version


class TestWorkflowCheckRule:
    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Commit without Jira Issue references in its title.
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
            assert execution_result == WorkflowCheckRule.ExecutionResult.no_commits

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Commit without Jira Issue references in its title.
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
            assert execution_result == WorkflowCheckRule.ExecutionResult.merged

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Commit without Jira Issue references in its title.
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
            assert execution_result == WorkflowCheckRule.ExecutionResult.work_in_progress

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Merge Request is attached to one good Jira Issue.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"],
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request attached to Jira Issue"
        }),
        # Merge Request in "Draft" state is attached to one good Jira Issue.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"],
        }], {
            "title": f"Draft: {DEFAULT_JIRA_ISSUE_KEY}: Merge request attached to Jira Issue"
        }),
        # Merge request is attached to one good Jira Issue (2)
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]
        }, {
            "key": "VMS-667", "branches": ["master", "vms_5.1"]
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Also fix VMS-667",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: Also fix VMS-667",
                "files": {},
            }],
        }),
        # Merge request is attached to two good Jira Issue.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]
        }, {
            "key": "VMS-667", "branches": ["master", "vms_5.1"]
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
            "key": "VMS-667", "branches": ["master", "vms_5.0_patch", "vms_5.1"]
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
            {"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]},
            {"key": "VMS-667", "branches": ["master", "vms_5.1"]},
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
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request title",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit title\n",
                "files": {},
            }],
        }),
        # Jira Issues in Merge Request title/description differs from Jira Issues from the commit
        # message for squashed Merge Request.
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
        # Jira Issues in Merge Request title/description is subset of Jira Issues from the commit
        # messages for non-squashed Merge Request.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"],
        }, {
            "key": f"{DEFAULT_JIRA_ISSUE_KEY}1", "branches": ["master"],
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request attached to Jira Issues",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit 1 title\n",
                "files": {},
            }, {
                "sha": f"{DEFAULT_COMMIT['sha']}abc",
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}1: commit 2 title\n",
                "files": {},
            }],
            "squash": False,
        }),
        # Merge Request title/description differs from the commit message for non-squashed Merge
        # Request, but Merge Request is follow-up.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"],
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request attached to Jira Issue",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit 1 title\n",
                "files": {},
            }],
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash": False,
        }),
        # One of the commit messages doesn't commit Jira Issue reference in squashed MR.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request title",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit 1 title\n",
                "files": {},
            }, {
                "sha": f"{DEFAULT_COMMIT['sha']}abc",
                "message": "commit 2 title",
                "files": {},
            }],
            "squash": True,
        }),
    ])
    def test_jira_issues_are_ok(self, workflow_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            result = workflow_rule.execute(mr_manager)
            assert result == WorkflowCheckRule.ExecutionResult.rule_execution_successful

            emojis = mr.awardemojis.list()
            assert not any(e for e in emojis if e.name == AwardEmojiManager.BAD_ISSUE_EMOJI)

            comments = mr.mock_comments()
            assert len(comments) == 0, f"Got comments: {comments}"

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
        assert execution_result == WorkflowCheckRule.ExecutionResult.rule_execution_successful

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
        # Merge Request is attached to good Jira Issues with different fixVersions.
        ([
            {"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.0_patch", "vms_5.1"]},
            {"key": "VMS-667", "branches": ["master", "vms_5.1"]},
        ], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, VMS-667: Multiple Jira Issues"
        }),
    ])
    def test_has_bad_or_inconsistent_version_set(self, workflow_rule, mr, mr_manager, jira):
        initial_comments_number = None
        for _ in range(2):  # State must not change after any number of rule executions.
            assert not workflow_rule.execute(mr_manager)

            emojis = mr.awardemojis.list()
            assert any(e for e in emojis if e.name == AwardEmojiManager.BAD_ISSUE_EMOJI)

            if initial_comments_number is None:
                initial_comments_number = len(mr.mock_comments())
                assert len(mr.mock_comments()) >= 1, f"Got comments: {mr.mock_comments()}"
            else:
                assert len(mr.mock_comments()) == initial_comments_number, (
                    f"Got comments: {mr.mock_comments()}")
            for comment in mr.mock_comments():
                has_bad_jira_issue_token = (
                    f':{AwardEmojiManager.BAD_ISSUE_EMOJI}: Jira workflow check failed')
                assert has_bad_jira_issue_token in comment
                condition = (
                    re.search(r"VMS-66[6|7|8]: `fixVersions` is inconsistent", comment) or
                    re.search(r"Bad `fixVersions` .+ VMS-66[7|8]: Version set", comment))
                assert condition, f"Error string is not found in {comment}"

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Jira Issue in Merge Request title differs from Jira Issue from commit message for
        # non-squashed Merge Request.
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
            "squash": False,
        }),
        # No commit for one of the Jira Issues in the Merge Request title for non-squashed Merge
        # Request.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]
        }, {
            "key": "VMS-667", "branches": ["master", "vms_5.1"]
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, VMS-667: Multiple Jira Issues",
            "squash": False,
        }),
        # Different commit message and title for non-squashed Merge Request with one commit.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request title",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit title\n",
                "files": {},
            }],
            "squash": False,
        }),
        # Squashed follow-up with parethesis in the begining of the title.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: (master->vms_5.0) Merge request title",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit title\n",
                "files": {},
            }],
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash": True,
        }),
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]
        }], {
            "title": f"(master->vms_5.0) Merge request title",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit title\n",
                "files": {},
            }],
            "description": f"Closes {DEFAULT_JIRA_ISSUE_KEY}",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash": True,
        }),
        # One of the commit messages doesn't commit Jira Issue reference in non-squashed MR.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request title",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit 1 title\n",
                "files": {},
            }, {
                "sha": f"{DEFAULT_COMMIT['sha']}abc",
                "message": "commit 2 title",
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
            assert len(comments) == 1, f"Got comments: {comments}"

            expected_title = (
                f"### :{AwardEmojiManager.BAD_ISSUE_EMOJI}: "
                "Merge request title/description does not comply with the rules")
            assert comments[0].startswith(expected_title), f"Unexpected comment: {comments[0]!r}"

            mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"],
        }, {
            "key": f"{DEFAULT_JIRA_ISSUE_KEY}1", "branches": ["vms_4.2"],
        }], {
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Merge request attached to Jira Issue",
            "commits_list": [{
                "sha": DEFAULT_COMMIT["sha"],
                "message": f"{DEFAULT_JIRA_ISSUE_KEY}: commit 1 title\n",
                "files": {},
            }],
            "squash": False,
        }),
    ])
    def test_comment_updates(self, workflow_rule, mr, mr_manager):
        def _check_mr(
                successfull: bool,
                comments_count: str,
                expected_comment_title: str,
                new_mr_title: str = None):
            if new_mr_title is not None:
                mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.
                mr.title = new_mr_title

            assert successfull == bool(workflow_rule.execute(mr_manager))

            emojis = mr.awardemojis.list()
            has_bad_issue_emoji = any(
                e for e in emojis if e.name == AwardEmojiManager.BAD_ISSUE_EMOJI)
            assert successfull != has_bad_issue_emoji

            comments_after_fix = mr.mock_comments()
            assert len(comments_after_fix) == comments_count, f"Got comments: {comments_after_fix}"
            assert comments_after_fix[-1].startswith(expected_comment_title), (
                f"Unexpected comment: {comments_after_fix[-1]!r}")

        expected_comment_title = (
            f"### :{AwardEmojiManager.BAD_ISSUE_EMOJI}: "
            "Merge request title/description does not comply with the rules")
        _check_mr(
            successfull=False,
            comments_count=1,
            expected_comment_title=expected_comment_title)

        # Fix the error - the emoji must be unset, no new comments added.
        expected_comment_title = (
            f"### :{AwardEmojiManager.AUTOCHECK_OK_EMOJI}: Workflow errors are fixed")
        _check_mr(
            successfull=True,
            comments_count=2,
            expected_comment_title=expected_comment_title,
            new_mr_title=f"{DEFAULT_JIRA_ISSUE_KEY}: commit 1 title")

        # Add the same error - the emoji must be set, new comment added.
        expected_comment_title = (
            f"### :{AwardEmojiManager.BAD_ISSUE_EMOJI}: "
            "Merge request title/description does not comply with the rules")
        _check_mr(
            successfull=False,
            comments_count=3,
            expected_comment_title=expected_comment_title,
            new_mr_title=f"{DEFAULT_JIRA_ISSUE_KEY}: some bad name")

        # Add a new error - the emoji must be set, another comment added.
        expected_comment_title = (
            f"### :{AwardEmojiManager.BAD_ISSUE_EMOJI}: "
            "Jira workflow check failed\n\nWorkflow violation detected:\n\nBad `fixVersions`")
        _check_mr(
            successfull=False,
            comments_count=4,
            expected_comment_title=expected_comment_title,
            new_mr_title=f"{DEFAULT_JIRA_ISSUE_KEY}1: some bad name")
