import pytest

from automation_tools.tests.gitlab_constants import OPEN_SOURCE_APPROVER_COMMON
from automation_tools.mr_data_structures import ApprovalRequirements
from tests.fixtures import *


class TestMergeRequestManager:
    @pytest.mark.parametrize(("mr_state", "requirements", "is_just_updated", "expected_result"), [
        [
            {"needed_approvers_number": 1, "approvers_list": {OPEN_SOURCE_APPROVER_COMMON}},
            ApprovalRequirements(authorized_approvers={OPEN_SOURCE_APPROVER_COMMON}),
            False,
            True,
        ],
        [
            {"needed_approvers_number": 1, "approvers_list": {OPEN_SOURCE_APPROVER_COMMON}},
            ApprovalRequirements(authorized_approvers={"somebody"}),
            False,
            False,
        ],
        [
            {"needed_approvers_number": 1, "approvers_list": {OPEN_SOURCE_APPROVER_COMMON}},
            ApprovalRequirements(approvals_left=0),
            False,
            True,
        ],
        [
            {"needed_approvers_number": 1, "approvers_list": {OPEN_SOURCE_APPROVER_COMMON}},
            ApprovalRequirements(approvals_left=0),
            True,
            False,
        ],
        [
            {"needed_approvers_number": 1},
            ApprovalRequirements(approvals_left=0),
            False,
            False,
        ],
        [
            {"needed_approvers_number": 1},
            ApprovalRequirements(approvals_left=1),
            False,
            True,
        ],
    ])
    def test_satisfy_approval_requirements(
            self, mr_manager, is_just_updated, requirements, expected_result):
        if is_just_updated is not None:
            mr_manager.is_revision_just_updated = is_just_updated
        assert mr_manager.satisfies_approval_requirements(requirements) == expected_result
