import pytest

from automation_tools.tests.fixtures import jira, repo_accessor
from bots.workflow_police.tests.fixtures import police_test_repo, workflow_checker


class TestPoliceChecker:
    @pytest.mark.parametrize("jira_issues", [
        # Issues that are not ready for the check.
        [
            {"key": "VMS-1", "branches": ["master"], "state": "In Review"},
            {"key": "VMS-2", "branches": ["master"], "state": "In progress"},
        ],
        # "Hidden" issue.
        [{"key": "VMS-1", "branches": ["master"], "labels": ["hide_from_police"]}],
        # Issues of non-checked type.
        [
            {"key": "VMS-1", "branches": ["master"], "typ": "New Feature"},
            {"key": "VMS-2", "branches": ["master"], "typ": "Epic"},
            {"key": "VMS-3", "branches": ["master"], "typ": "Func Spec"},
            {"key": "VMS-4", "branches": ["master"], "typ": "Tech Spec"},
        ],
        # Issues that are ignored for other reasons.
        [
            {"key": "NONEXISTENT-1", "branches": ["master"], "state": "Waiting for QA"},
            {
                "key": "VMS-1",
                "branches": ["master"],
                "state": "Waiting for QA",
                "labels": ["done_externally"],
            }
        ],
    ])
    def test_should_ignore_issue(self, jira, jira_issues, workflow_checker):
        for issue_data in jira_issues:
            issue_key = issue_data["key"]
            issue = jira.get_issue(issue_key)
            assert workflow_checker.should_ignore_issue(issue), (
                f'Issue "{issue_key}"" is not ignored')

    @pytest.mark.parametrize("jira_issues", [
        # Bad version set.
        [{"key": "VMS-1", "branches": ["master", "vms_4.2"]}],
        # Bad version set for another project.
        [{"key": "MOBILE-1", "branches": ["master", "mobile_20.3"]}],
        # Non-existing branch "vms_4.1_patch".
        [{"key": "VMS-1", "branches": ["vms_4.1", "vms_4.2", "vms_4.2_patch", "master"]}],
        # Commit is not found in branch "vms_4.2_patch".
        [{"key": "VMS-2", "branches": ["master", "vms_4.2_patch"]}],
    ])
    def test_should_reopen_issue(self, jira, jira_issues, workflow_checker):
        for issue_data in jira_issues:
            issue_key = issue_data["key"]
            issue = jira.get_issue(issue_key)
            assert workflow_checker.should_reopen_issue(issue), (
                f'Issue "{issue_key}" is not to be reopened')

    @pytest.mark.parametrize("jira_issues", [
        # "Good" issue.
        [{"key": "VMS-1", "branches": ["master", "vms_4.2_patch"]}],
        # "Good" issue for another project.
        [{"key": "MOBILE-1", "branches": ["master", "mobile_21.1"]}],
        # And another one.
        [{"key": "CB-1", "branches": ["master", "cloud_backend_20.1"]}],
        # Bad version set, but has "version_specific" label.
        [{"key": "VMS-2", "branches": ["master", "vms_4.2"], "labels": ["version_specific"]}],
        # Commit is not found in branch "master", but has "version_specific" label.
        [{"key": "VMS-3", "branches": ["vms_4.2_patch"], "labels": ["version_specific"]}],
        # The commit is not found in the branch "vms_4.2_patch" but has "already_in_4.2_patch"
        # label.
        [{
            "key": "VMS-4",
            "branches": ["master", "vms_4.2_patch"],
            "labels": ["already_in_4.2_patch"],
        }],
    ])
    def test_should_not_reopen_issue(self, jira, jira_issues, workflow_checker):
        for issue_data in jira_issues:
            issue_key = issue_data["key"]
            issue = jira.get_issue(issue_key)
            result = workflow_checker.should_reopen_issue(issue)
            assert not result, f'Issue "{issue_key}" is to be reopened: "{result}"'
