## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import pytest

from automation_tools.tests.gitlab_constants import (
    DEFAULT_COMMIT,
    DEFAULT_JIRA_ISSUE_KEY,
    DEFAULT_CLOUD_ISSUE_KEY,
    MR_MERGED_COMMENT_TEMPLATE_LEGACY,
    MR_MERGED_COMMENT_TEMPLATE)
from robocat.award_emoji_manager import AwardEmojiManager
from robocat.rule.post_processing_rule import PostProcessingRule
from tests.fixtures import *


class TestPostProcessingRule:
    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Opened MR.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "state": "In Review"
        }], {
            "state": "opened",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
        }),
        # No Jira Issues MR.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "state": "In Review"
        }], {
            "state": "merged",
            "title": f"Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
        }),
    ])
    def test_ignore_mr(self, project, post_processing_rule, mr, mr_manager):
        assert (post_processing_rule.execute(mr_manager) ==
                PostProcessingRule.ExecutionResult.not_eligible)

    @pytest.mark.parametrize(("jira_issues", "mr_state", "expected_comment_count"), [
        # Merged to all issue branches, but the Issue has "Open" status.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "state": "Open",
            "comments_list": [
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master"),
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:vms_5.1"),
            ],
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
        }, 3),
        # Same, but the Issue has "In progress" status.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "state": "In progress",
            "comments_list": [
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master"),
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:vms_5.1"),
            ],
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
        }, 2),
        # Issue is "In Review" status, but merged only to one branch.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "state": "In Review",
            "comments_list": [MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master")],
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
        }, 1),
        # Issue is "In Review" status, but merged to the wrong branches.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "state": "In Review",
            "comments_list": [
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master"),
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:vms_5.2"),
            ],
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
        }, 2),
        # Issue is "In Review" status, merged branches have the right names, but one of them has
        # incorrect project_name.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "state": "In Review",
            "comments_list": [
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master"),
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="cloud_portal:vms_5.1"),
            ],
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
        }, 2),
        # Merged to all issue branches, Issue has "In Review" status, Issue type is "Internal", but
        # one branch is merged with wrong original MR id.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "state": "In Review",
            "comments_list": [
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master"),
                MR_MERGED_COMMENT_TEMPLATE.format(branch="nx:vms_5.1", original_mr_id=123),
            ],
            "typ": "Internal",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "mock_original_mr_id": 321,
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
        }, 2),
    ])
    def test_fail_to_finalize_issues(
            self, project, post_processing_rule, mr, mr_manager, jira, expected_comment_count):
        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        issue_state_before = issue.fields.status.name

        assert (post_processing_rule.execute(mr_manager) ==
                PostProcessingRule.ExecutionResult.rule_execution_failed)

        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        assert issue.fields.status.name == issue_state_before
        assert len(issue.fields.comment.comments) == expected_comment_count

    # TODO: Use MR_MERGED_COMMENT_TEMPLATE instead of MR_MERGED_COMMENT_TEMPLATE_LEGACY after some
    # time, when all Jira Issues will have comments in the new format.
    @pytest.mark.parametrize(
        ("jira_issues", "mr_state", "expected_comment_count", "expected_status"),
        [
            # Merged to all issue branches, Issue has "In Review" status, Issue type is "Internal".
            ([{
                "key": DEFAULT_JIRA_ISSUE_KEY,
                "branches": ["master", "vms_5.1"],
                "state": "In Review",
                "comments_list": [
                    MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master"),
                    MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:vms_5.1"),
                ],
                "typ": "Internal",
            }], {
                "state": "merged",
                "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
                "squash_commit_sha": DEFAULT_COMMIT["sha"],
            }, 3, "Closed"),
            # Same, but Issue type is "Task".
            ([{
                "key": DEFAULT_JIRA_ISSUE_KEY,
                "branches": ["master", "vms_5.1"],
                "state": "In Review",
                "comments_list": [
                    MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master"),
                    MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:vms_5.1"),
                ],
                "typ": "Task",
            }], {
                "state": "merged",
                "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
                "squash_commit_sha": DEFAULT_COMMIT["sha"],
            }, 3, "Waiting for QA"),
            # Same, MR has arbitrary target_branch.
            ([{
                "key": DEFAULT_JIRA_ISSUE_KEY,
                "branches": ["master", "vms_5.1"],
                "state": "In Review",
                "comments_list": [
                    MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master"),
                    MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:vms_5.1"),
                ],
                "typ": "Task",
            }], {
                "state": "merged",
                "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
                "squash_commit_sha": DEFAULT_COMMIT["sha"],
                "target_branch": "vms_5.2",
            }, 3, "Waiting for QA"),
            # Same, MR is follow-up.
            ([{
                "key": DEFAULT_JIRA_ISSUE_KEY,
                "branches": ["master", "vms_5.1"],
                "state": "In Review",
                "comments_list": [
                    MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master"),
                    MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:vms_5.1"),
                ],
                "typ": "Task",
            }], {
                "state": "merged",
                "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
                "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
                "squash_commit_sha": DEFAULT_COMMIT["sha"],
                "target_branch": "vms_5.2",
            }, 3, "Waiting for QA"),
            # Merged to all issue branches, Issue has "In Review" status, Issue type is
            # "Security Issue".
            ([{
                "key": DEFAULT_JIRA_ISSUE_KEY,
                "branches": ["master", "vms_5.1"],
                "state": "In Review",
                "comments_list": [
                    MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master"),
                    MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:vms_5.1"),
                ],
                "typ": "Security Issue",
            }], {
                "state": "merged",
                "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
                "squash_commit_sha": DEFAULT_COMMIT["sha"],
            }, 3, "Pending Verification"),
            # Merged to all issue branches, Issue has "In Review" status, Issue type is "Internal".
            # The Issue has "merged to branch" comments in the new format.
            ([{
                "key": DEFAULT_JIRA_ISSUE_KEY,
                "branches": ["master", "vms_5.1"],
                "state": "In Review",
                "comments_list": [
                    MR_MERGED_COMMENT_TEMPLATE.format(branch="nx:master", original_mr_id=123),
                    MR_MERGED_COMMENT_TEMPLATE.format(branch="nx:vms_5.1", original_mr_id=123),
                ],
                "typ": "Internal",
            }], {
                "iid": 123,
                "state": "merged",
                "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
                "squash_commit_sha": DEFAULT_COMMIT["sha"],
            }, 3, "Closed"),
            # Same, but MR is follow-up with the right original MR id.
            ([{
                "key": DEFAULT_JIRA_ISSUE_KEY,
                "branches": ["master", "vms_5.1"],
                "state": "In Review",
                "comments_list": [
                    MR_MERGED_COMMENT_TEMPLATE.format(branch="nx:master", original_mr_id=123),
                    MR_MERGED_COMMENT_TEMPLATE.format(branch="nx:vms_5.1", original_mr_id=123),
                ],
                "typ": "Internal",
            }], {
                "state": "merged",
                "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
                "squash_commit_sha": DEFAULT_COMMIT["sha"],
                "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
                "mock_original_mr_id": 123,
            }, 3, "Closed"),

        ])
    def test_finalize_one_issue(
            self,
            project,
            post_processing_rule,
            mr,
            mr_manager,
            jira,
            expected_comment_count,
            expected_status):
        assert (post_processing_rule.execute(mr_manager) ==
                PostProcessingRule.ExecutionResult.rule_execution_successful)

        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        assert issue.fields.status.name == expected_status
        assert len(issue.fields.comment.comments) == expected_comment_count

    @pytest.mark.parametrize(("jira_issues", "mr_state", "expected_comment_counts"), [
        # Issues from the same project.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "state": "In Review",
            "comments_list": [
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master"),
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:vms_5.1"),
            ],
        }, {
            "key": f"{DEFAULT_JIRA_ISSUE_KEY}1",
            "branches": ["master", "vms_5.2"],
            "state": "In Review",
            "comments_list": [
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master"),
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:vms_5.2"),
            ],
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, {DEFAULT_JIRA_ISSUE_KEY}1: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
        }, {DEFAULT_JIRA_ISSUE_KEY: 3, f"{DEFAULT_JIRA_ISSUE_KEY}1": 3}),
        # Issues from different projects with legacy "merged to branch" comments.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "state": "In Review",
            "comments_list": [
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master"),
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:vms_5.1"),
            ],
        }, {
            "key": DEFAULT_CLOUD_ISSUE_KEY,
            "branches": ["cloud_portal:develop", "nx:master"],
            "state": "In Review",
            "comments_list": [
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="nx:master"),
                MR_MERGED_COMMENT_TEMPLATE_LEGACY.format(branch="cloud_portal:develop"),
            ],
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, {DEFAULT_CLOUD_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
        }, {DEFAULT_JIRA_ISSUE_KEY: 3, DEFAULT_CLOUD_ISSUE_KEY: 3}),
        # Issues from different projects.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "state": "In Review",
            "comments_list": [
                MR_MERGED_COMMENT_TEMPLATE.format(branch="nx:master", original_mr_id=123),
                MR_MERGED_COMMENT_TEMPLATE.format(branch="nx:vms_5.1", original_mr_id=123),
            ],
        }, {
            "key": DEFAULT_CLOUD_ISSUE_KEY,
            "branches": ["cloud_portal:develop", "nx:master"],
            "state": "In Review",
            "comments_list": [
                MR_MERGED_COMMENT_TEMPLATE.format(branch="nx:master", original_mr_id=123),
                # For Issue from "cloud_portal" project original MR id is different, but it should
                # not affect the post-processing (do not check original MR id for different
                # projects).
                MR_MERGED_COMMENT_TEMPLATE.format(
                    branch="cloud_portal:develop", original_mr_id=321),
            ],
        }], {
            "iid": 123,
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, {DEFAULT_CLOUD_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
        }, {DEFAULT_JIRA_ISSUE_KEY: 3, DEFAULT_CLOUD_ISSUE_KEY: 3}),
    ])
    def test_finalize_server_issues(
            self,
            jira_issues,
            project,
            post_processing_rule,
            mr,
            mr_manager,
            jira,
            expected_comment_counts):
        assert (post_processing_rule.execute(mr_manager) ==
                PostProcessingRule.ExecutionResult.rule_execution_successful)

        for issue_description in jira_issues:
            issue_key = issue_description["key"]
            issue = jira._jira.issue(issue_key)
            assert issue.fields.status.name == "Closed"
            assert len(issue.fields.comment.comments) == expected_comment_counts[issue_key]
