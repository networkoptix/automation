import pytest

from automation_tools.jira import JiraError
from automation_tools.tests.gitlab_constants import MERGED_TO_MASTER_MERGE_REQUESTS
from tests.fixtures import *


class TestProcessRelatedProjectIssuesRule:
    @pytest.mark.parametrize(("jira_issues", "mr_state", "expected_result"), [
        # Do not postprocess Open Merge Requests.
        ([], {
            "state": "opened",
            "title": "VMS-28944: Updates webadmin to 9877654"
        }, ProcessRelatedProjectIssuesRule.ExecutionResult.not_eligible
        ),
        # Do not postprocess Merge Requests with the title that does not match the pattern.
        ([], {
            "state": "merged",
            "title": "VMS-28944: (master -> vms_5.0) Updates webadmin to 9877654"
        }, ProcessRelatedProjectIssuesRule.ExecutionResult.no_applicable_rules
        ),
    ])
    def test_skip_mrs(self, process_related_projects_issues_rule, mr, mr_manager, expected_result):
        for _ in range(2):
            result = process_related_projects_issues_rule.execute(mr_manager)
            assert result == expected_result, f"Unexpected result: {result}"

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Fail if some of the mentioned Issues are Open.
        ([{
            "key": "CLOUD-1",
            "branches": ["master", "vms_5.0"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "Open",
        }, {
            "key": "CLOUD-2",
            "branches": ["master", "vms_5.0"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": "VMS-28944: Updates webadmin to 9877654",
            "description": "Changelog: CLOUD-1, VMS-999, CLOUD-2",
        }),
        # Fail if some of the mentioned Issues are In progress.
        ([{
            "key": "CLOUD-4",
            "branches": ["master", "vms_5.0"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "In progress",
        }], {
            "state": "merged",
            "title": "VMS-28944: Updates webadmin to 9877654",
            "description": "Changelog: CLOUD-4",
        }),
        # Fail if some of the mentioned Issues do not exist.
        ([], {
            "state": "merged",
            "title": "VMS-28944: Updates webadmin to 9877654",
            "description": "Changelog: CLOUD-5",
        }),
    ])
    def test_postprocessing_failed(self, process_related_projects_issues_rule, mr, mr_manager):
        expected_result = ProcessRelatedProjectIssuesRule.ExecutionResult.rule_execution_failed
        for _ in range(2):
            # Bad Issue status can result either in "rule_exception_failed" return value or in
            # specific JiraError exception.
            try:
                result = process_related_projects_issues_rule.execute(mr_manager)
                assert result == expected_result, f"Unexpected result: {result}"
            except JiraError as err:
                is_error_good = (
                    str(err).startswith("Cannot automatically move") or
                    str(err).startswith("Unable to obtain issue"))
                assert is_error_good, f"Bad JiraError: {err}"

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Process related Issues with "In Review" status.
        ([{
            "key": "CLOUD-11",
            "branches": ["master", "vms_5.0"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "Closed",
        }, {
            "key": "CLOUD-12",
            "branches": ["master", "vms_5.0"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "Waiting for QA",
        }], {
            "state": "merged",
            "title": "VMS-28944: Updates webadmin to 9877654",
            "description": "Changelog: CLOUD-11, VMS-999, CLOUD-12",
        }),
        # It is ok if no related Issues are found for the Merge Request.
        # Process related Issues with "In Review" status.
        ([], {
            "state": "merged",
            "title": "VMS-28944: Updates webadmin to 9877654",
            "description": "Changelog: VMS-999",
        }),
        # It is ok if some of the mentioned Issues have "Closed"/"Waiting for QA" status.
        ([{
            "key": "CLOUD-13",
            "branches": ["master", "vms_5.0"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "Closed",
        }, {
            "key": "CLOUD-14",
            "branches": ["master", "vms_5.0"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "Waiting for QA",
        }], {
            "state": "merged",
            "title": "VMS-28944: Updates webadmin to 9877654",
            "description": "Changelog: CLOUD-13, VMS-999, CLOUD-14",
        }),
    ])
    def test_postprocessing_ok(self, process_related_projects_issues_rule, mr, mr_manager):
        expected_result = (
            ProcessRelatedProjectIssuesRule.ExecutionResult.rule_execution_successful)
        for _ in range(2):
            result = process_related_projects_issues_rule.execute(mr_manager)
            assert result == expected_result, f"Unexpected result: {result}"
