## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import pytest

from automation_tools.tests.gitlab_constants import OPEN_SOURCE_APPROVER_COMMON
from automation_tools.mr_data_structures import ApprovalRequirements
from tests.fixtures import *
from robocat.note import MessageId
import robocat.comments

class TestMergeRequestManager:
    @pytest.mark.parametrize(("mr_state", "requirements", "expected_result"), [
        # Nobody has approved the MR yet - ensure that approvals_left is the same that
        # needed_approvers_number.
        [
            {"needed_approvers_number": 1},
            ApprovalRequirements(approvals_left=1),
            True,
        ],
        # Ensure that if the list of approvers is right, than the requirements are satisfied.
        [
            {"needed_approvers_number": 1, "approvers_list": {OPEN_SOURCE_APPROVER_COMMON}},
            ApprovalRequirements(authorized_approvers={OPEN_SOURCE_APPROVER_COMMON}),
            True,
        ],
        # Ensure that if the list of approvers is NOT right, than the requirements are NOT
        # satisfied.
        [
            {"needed_approvers_number": 1, "approvers_list": {OPEN_SOURCE_APPROVER_COMMON}},
            ApprovalRequirements(authorized_approvers={"somebody"}),
            False,
        ],
        # MR is approved by more users than necessary - requirements satisfied.
        [
            {"needed_approvers_number": 1, "approvers_list": {OPEN_SOURCE_APPROVER_COMMON}},
            ApprovalRequirements(approvals_left=0),
            True,
        ],
        # "approvers_left" is 0, but "approved" boolean field is False - there is an
        # inconsistency, which means that the requirements are not satisfied.
        [
            {
                "needed_approvers_number": 1,
                "approvers_list": {OPEN_SOURCE_APPROVER_COMMON},
                "mock_force_unapproved": True,
            },
            ApprovalRequirements(approvals_left=0),
            False,
        ],
    ])
    def test_satisfy_approval_requirements(self, mr_manager, requirements, expected_result):
        assert mr_manager.satisfies_approval_requirements(requirements) == expected_result

    @pytest.mark.parametrize(("mr_state", "previous_base_sha", "is_just_rebased"), [
        [
            {"mock_base_commit_sha": "abcdef12345"},
            "abcdef12345",
            False,
        ],
        [
            {"mock_base_commit_sha": "abcdef12345"},
            "00000000000",
            True,
        ]
    ])
    def test_update_merge_base(self, mr_manager, previous_base_sha, is_just_rebased):
        mr_manager.add_comment(
            message=robocat.comments.Message(
                id=MessageId.InitialMessage,
                params={
                    "bot_gitlab_username": mr_manager._current_user,
                    "bot_revision": automation_tools.bot_info.revision(),
                    "command_list": "\n- ".join(
                        cls.description() for cls in robocat.commands.parser.command_classes()),
                }),
            message_data={"base_sha": previous_base_sha})
        mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.
        initial_base_sha = mr_manager.notes()[0].additional_data["base_sha"]

        mr_manager.update_merge_base()
        mr_manager._mr.load_discussions()  # Update notes in MergeRequest object.
        new_base_sha = mr_manager.notes()[0].additional_data["base_sha"]

        assert mr_manager.is_just_rebased == is_just_rebased
        if mr_manager.is_just_rebased:
            assert new_base_sha != initial_base_sha, "Base sha has not been changed after rebase"
        else:
            assert new_base_sha == initial_base_sha, "Base sha has been changed without rebase"
        assert mr_manager._mr.latest_diff().base_commit_sha == new_base_sha
