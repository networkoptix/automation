import pytest

from automation_tools.tests.fixtures import jira, repo_accessor
from automation_tools.tests.gitlab_constants import DEFAULT_MR_ID
from bots.workflow_police.tests.fixtures import (
    police_test_repo,
    workflow_checker,
    project,
    mr_states,
    workflow_enforcer)


class TestPoliceChecker:
    @pytest.mark.parametrize("jira_issues", [
        # Issues that are not ready for the check.
        [
            {"key": "VMS-1", "branches": ["master"], "state": "In Review", "resolution": None},
            {"key": "VMS-2", "branches": ["master"], "state": "In progress", "resolution": None},
        ],
        # "Hidden" issue.
        [{
            "key": "VMS-1",
            "branches": ["master"],
            "labels": ["hide_from_police"],
            "resolution": "Fixed",
        }],
        # Issues of non-checked type.
        [
            {"key": "VMS-1", "branches": ["master"], "typ": "New Feature", "resolution": "Fixed"},
            {"key": "VMS-2", "branches": ["master"], "typ": "Epic", "resolution": "Fixed"},
            {"key": "VMS-3", "branches": ["master"], "typ": "Func Spec", "resolution": "Fixed"},
            {"key": "VMS-4", "branches": ["master"], "typ": "Tech Spec", "resolution": "Fixed"},
        ],
        # Issues that are ignored for other reasons.
        [
            {"key": "NONEXISTENT-1", "branches": ["master"], "state": "Waiting for QA"},
        ],
        # Irrelevant branches for Issue that has related project.
        [
            {"key": "CLOUD-0", "branches": ["5.0"], "resolution": "Fixed"},
        ],
    ])
    def test_should_ignore_issue(self, jira, jira_issues, workflow_checker):
        for issue_data in jira_issues:
            issue_key = issue_data["key"]
            issue = jira.get_issue(issue_key)
            assert workflow_checker.should_ignore_issue(issue), (
                f'Issue "{issue_key}"" is not ignored')

    @pytest.mark.parametrize(("jira_issues", "mr_states"), [
        # Bad version set.
        ([
            {"key": "VMS-1", "branches": ["master", "vms_4.2"]}
        ], [
            {},
        ]),
        # Bad version set for another project.
        ([
            {"key": "MOBILE-1", "branches": ["master", "mobile_20.3"]},
        ], [
            {},
        ]),
        # Non-existing branch "vms_5.1_patch".
        ([
            {"key": "VMS-1", "branches": ["vms_5.1", "vms_4.2", "vms_4.2_patch", "master"]}
        ], [
            {},
        ]),
        # Commit is not found in branch "vms_4.2_patch".
        ([
            {"key": "VMS-2", "branches": ["master", "vms_4.2_patch"]}
        ], [
            {},
        ]),
        # No related Merge Request.
        ([{
            "key": "CLOUD-1",
            "branches": ["master", "21.1"]
        }], [
            {},
        ]),
        # Related Merge Request is not merged.
        ([{
            "key": "CLOUD-2",
            "branches": ["master", "21.1"],
            "merge_requests": [f"{DEFAULT_MR_ID}0"],
        }], [{
            "iid": int(f"{DEFAULT_MR_ID}0"),
        }]),
        # One related Merge Request is merged, other is not.
        ([{
            "key": "CLOUD-3",
            "branches": ["master", "vms_5.0", "21.1"],
            "merge_requests": [f"{DEFAULT_MR_ID}1", f"{DEFAULT_MR_ID}2"],
        }], [{
            "iid": int(f"{DEFAULT_MR_ID}1"),
            "target_branch": "master",
            "state": "merged",
        }, {
            "iid": int(f"{DEFAULT_MR_ID}2"),
            "target_branch": "vms_5.0",
            "state": "open",
        }]),
    ])
    def test_should_reopen_issue(self, jira, jira_issues, workflow_checker, mr_states):
        for issue_data in jira_issues:
            issue_key = issue_data["key"]
            issue = jira.get_issue(issue_key)
            assert workflow_checker.should_reopen_issue(issue), (
                f'Issue "{issue_key}" is not to be reopened')

    @pytest.mark.parametrize(("jira_issues", "mr_states"), [
        # "Good" issue.
        ([
            {"key": "VMS-1", "branches": ["master", "vms_5.1"], "resolution": "Fixed"},
        ], [
            {}
        ]),
        # "Good" issue for another project.
        ([{
            "key": "MOBILE-1",
            "branches": ["master", "mobile_22.5", "mobile_22.4"],
            "resolution": "Fixed",
        }], [
            {},
        ]),
        # And another one.
        ([
            {"key": "CB-1", "branches": ["master", "cloud_backend_20.1"], "resolution": "Fixed"},
        ], [
            {},
        ]),
        # Bad version set, but has "version_specific" label.
        ([{
            "key": "VMS-2",
            "branches": ["master", "vms_4.2"],
            "labels": ["version_specific"],
            "resolution": "Fixed",
        }], [
            {},
        ]),
        # Commit is not found in branch "master", but has "version_specific" label.
        ([{
            "key": "VMS-3",
            "branches": ["vms_4.2_patch"],
            "labels": ["version_specific"],
            "resolution": "Fixed"
        }], [
            {},
        ]),
        # The commit is not found in the branch "vms_4.2_patch" but has "already_in_4.2_patch"
        # label.
        ([{
            "key": "VMS-4",
            "branches": ["master", "vms_5.1"],
            "labels": ["already_in_5.1"],
            "resolution": "Fixed",
        }], [
            {}
        ]),
        # Commits for some branches are missing, but the label "done_externally" presents.
        ([{
            "key": "VMS-4",
            "branches": ["master", "vms_5.1"],
            "state": "Waiting for QA",
            "labels": ["done_externally"],
            "resolution": "Fixed",
        }], [
            {},
        ]),
        # Commits for master branch is missing, but the label "done_externally" presents.
        ([{
            "key": "VMS-NONEXISTENT",
            "branches": ["master"],
            "state": "Waiting for QA",
            "labels": ["done_externally"],
            "resolution": "Fixed",
        }], [
            {},
        ]),
        # Has related project but irrelevant branches.
        ([{
            "key": "CLOUD-11",
            "branches": ["5.0"],
            "resolution": "Fixed",
        }], [
            {}
        ]),
        # Has merged related Merge Request.
        ([{
            "key": "CLOUD-12",
            "branches": ["master", "vms_5.0", "21.1"],
            "merge_requests": [f"{DEFAULT_MR_ID}10", f"{DEFAULT_MR_ID}11"],
            "resolution": "Fixed",
        }], [{
            "iid": int(f"{DEFAULT_MR_ID}10"),
            "target_branch": "master",
            "state": "merged",
        }, {
            "iid": int(f"{DEFAULT_MR_ID}11"),
            "target_branch": "vms_5.0",
            "state": "merged",
        }]),
    ])
    def test_should_not_reopen_issue(self, jira, jira_issues, workflow_checker, mr_states):
        for issue_data in jira_issues:
            issue_key = issue_data["key"]
            issue = jira.get_issue(issue_key)
            result = workflow_checker.should_reopen_issue(issue)
            assert not result, f'Issue "{issue_key}" is to be reopened: "{result}"'
