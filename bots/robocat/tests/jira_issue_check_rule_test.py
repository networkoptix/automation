import pytest

from jira.exceptions import JIRAError

from robocat.rule.jira_issue_check_rule import JiraIssueCheckRuleExecutionResult
from robocat.award_emoji_manager import AwardEmojiManager
from tests.fixtures import *

import automation_tools.checkers.config
from automation_tools.tests.fixtures import jira, repo_accessor
from automation_tools.tests.mocks.resources import Version


class TestJiraIssueCheckRule:
    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Commit without Jira Issue referencees in its title.
        ([{
            "key": "VMS-666", "branches": ["master"],
        }], {
            "title": "Merge request without commits",
            "commits_list": [],
        }),
    ])
    def test_no_commits(self, jira_issue_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            execution_result = jira_issue_rule.execute(mr_manager)
            assert execution_result == JiraIssueCheckRuleExecutionResult.no_commits

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Commit without Jira Issue referencees in its title.
        ([{
            "key": "VMS-666", "branches": ["master"],
        }], {
            "title": "Merged merge request",
            "state": "merged",
        }),
    ])
    def test_merged(self, jira_issue_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            execution_result = jira_issue_rule.execute(mr_manager)
            assert execution_result == JiraIssueCheckRuleExecutionResult.merged

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Commit without Jira Issue referencees in its title.
        ([{
            "key": "VMS-666", "branches": ["master"],
        }], {
            "title": "WIP",
            "work_in_progress": True,
        }),
    ])
    def test_wip(self, jira_issue_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            execution_result = jira_issue_rule.execute(mr_manager)
            assert execution_result == JiraIssueCheckRuleExecutionResult.work_in_progress

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Merge request is attached to one good Jira Issue.
        ([{
            "key": "VMS-666", "branches": ["master"],
        }], {
            "title": "VMS-666: Merge request attached to Jira Issue"
        }),
        # Merge request is attached to two good Jira Issue.
        ([{
            "key": "VMS-666", "branches": ["master"]
        }, {
            "key": "VMS-667", "branches": ["master", "vms_4.2_patch"]
        }], {
            "title": "VMS-666, VMS-667: Merge request attached to multiple Jira Issues"
        }),
        # Merge request is attached to bad Jira Issue but ignored because of the label (1).
        ([{
            "key": "VMS-666",
            "branches": ["vms_4.2"],
            "labels": [automation_tools.checkers.config.VERSION_SPECIFIC_LABEL]
        }], {
            "title": "VMS-666: Merge request attached to bad Jira Issue"
        }),
        # Merge request is attached to bad Jira Issue but ignored because of the label (2).
        ([{
            "key": "VMS-666",
            "branches": ["vms_4.2"],
            "labels": [automation_tools.checkers.config.IGNORE_LABEL]
        }], {
            "title": "VMS-666: Merge request attached to bad Jira Issue"
        }),
        # Merge request is ignored because it is attached to the unsupported project.
        ([{
            "key": "CI-123", "branches": ["master"],
        }], {
            "title": "CI-123: Commit to CI"
        }),
        # Merge request is attached to one good Jira Issue and to one bad Jira Issue which is
        # ignored because of the label.
        ([{
            "key": "VMS-666",
            "branches": ["vms_4.2"],
            "labels": [automation_tools.checkers.config.IGNORE_LABEL]
        }, {
            "key": "VMS-667", "branches": ["master", "vms_4.2", "vms_4.2_patch"]
        }], {
            "title": "VMS-666, VMS-667: Merge request attached to multiple Jira Issues"
        }),
    ])
    def test_jira_issues_are_ok(self, jira_issue_rule, mr, mr_manager):
        for _ in range(2):  # State must not change after any number of rule executions.
            execution_result = jira_issue_rule.execute(mr_manager)
            assert execution_result == JiraIssueCheckRuleExecutionResult.rule_execution_successfull

            emojis = mr.awardemojis.list()
            assert not any(e for e in emojis if e.name == AwardEmojiManager.BAD_ISSUE_EMOJI)

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Merge request is initially attached to bad Jira Issue.
        ([{
            "key": "VMS-666", "branches": ["vms_4.2"],
        }], {
            "title": "VMS-666: Merge request attached to Jira Issue"
        }),
        # Merge request is initially attached to one good and one bad Jira Issue.
        ([{
            "key": "VMS-666", "branches": ["vms_4.2"],
        }, {
            "key": "VMS-667", "branches": ["master", "vms_4.2_patch"],
        }], {
            "title": "VMS-666, VMS-667: Merge request attached to Jira Issue"
        }),
    ])
    def test_remove_bad_issue_token(self, jira_issue_rule, mr, mr_manager, jira):
        execution_result = jira_issue_rule.execute(mr_manager)
        assert execution_result == JiraIssueCheckRuleExecutionResult.rule_execution_failed

        emojis = mr.awardemojis.list()
        assert any(e for e in emojis if e.name == AwardEmojiManager.BAD_ISSUE_EMOJI)

        issue = jira._jira.issue("VMS-666")
        issue.fields.fixVersions = [
            Version("master", "<master> Major release with a lot of tech debt")]

        execution_result = jira_issue_rule.execute(mr_manager)
        assert execution_result == JiraIssueCheckRuleExecutionResult.rule_execution_successfull

        emojis = mr.awardemojis.list()
        assert not any(e for e in emojis if e.name == AwardEmojiManager.BAD_ISSUE_EMOJI)

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Commit without Jira Issue references in its title.
        ([{
            "key": "VMS-666", "branches": ["master"],
        }], {
            "title": "Merge request without Jira Issue"
        }),
        # Merge request is attached to bad Jira Issue.
        ([{
            "key": "VMS-667", "branches": ["vms_4.2"],
        }], {
            "title": "VMS-667: Merge request attached to Jira Issue"
        }),
        # Merge request is attached to one good and two bad Jira Issues.
        ([
            {"key": "VMS-666", "branches": ["master"]},
            {"key": "VMS-667", "branches": ["vms_4.2_patch"]},
            {"key": "VMS-668", "branches": ["vms_4.2"]},
        ], {
            "title": "VMS-666, VMS-667, VMS-668: Merge request attached to multiple Jira Issues"
        }),
    ])
    def test_has_jira_issue_problems(self, jira_issue_rule, mr, mr_manager, jira):
        for _ in range(2):  # State must not change after any number of rule executions.
            execution_result = jira_issue_rule.execute(mr_manager)
            assert execution_result == JiraIssueCheckRuleExecutionResult.rule_execution_failed

            emojis = mr.awardemojis.list()
            assert any(e for e in emojis if e.name == AwardEmojiManager.BAD_ISSUE_EMOJI)

            assert len(mr.mock_comments()) == 1
            first_comment = mr.mock_comments()[0]
            has_bad_jira_issue_token = (
                f':{AwardEmojiManager.BAD_ISSUE_EMOJI}: Jira workflow check failed')
            assert has_bad_jira_issue_token in first_comment
            assert 'VMS-666' not in first_comment

            try:
                jira._jira.issue("VMS-667")
                assert 'VMS-667' in first_comment
            except JIRAError:
                pass

            # Check "VMS-668" error message only if we have VMS-668 issue in the test parameters.
            try:
                jira._jira.issue("VMS-668")
                assert 'VMS-668' in first_comment
            except JIRAError:
                pass
