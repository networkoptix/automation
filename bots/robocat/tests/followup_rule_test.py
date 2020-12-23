import re
import pytest

from robocat.award_emoji_manager import AwardEmojiManager
from tests.common_constants import (
    DEFAULT_COMMIT,
    CONFLICTING_COMMIT_SHA,
    MERGED_TO_MASTER_MERGE_REQUESTS,
    MERGED_TO_4_1_MERGE_REQUESTS,
    MERGED_TO_4_2_MERGE_REQUESTS)
from tests.fixtures import *


class TestFollowupRule:
    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Don't create follow-up merge request for opened merge request.
        ([{"key": "VMS-666", "branches": ["master", "vms_4.1"]}], {
            "state": "opened",
        }),
        # Don't create follow-up merge request for follow-up merge requests.
        ([{"key": "VMS-666", "branches": ["master", "vms_4.1"]}], {
            "state": "merged",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI]
        }),
        # Don't create follow-up merge request for unknown issue.
        ([{"key": "VMS-666", "branches": ["master", "vms_4.1"]}], {
            "state": "merged",
            "squash_commit_sha": DEFAULT_COMMIT["sha"]
        }),
    ])
    def test_dont_create_followup(self, project, followup_rule, mr, mr_manager, jira):
        for _ in range(2):
            assert not followup_rule.execute(mr_manager)

            issue = jira._jira.issue("VMS-666")
            assert len(issue.fields.comment.comments) == 0, (
                f"Got Jira issue comments: {issue.fields.comment.comments}")

            assert len(mr.comments()) == 0, (
                f"Got merge request comments: {mr.comments()}")

            emojis = mr.awardemojis.list()
            assert not any(
                e for e in emojis if e.name == AwardEmojiManager.FOLLOWUP_CREATED_EMOJI), (
                'Hasn\'t "follow-up created" emoji.')

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Fail to create follow-up merge request if the target branch already exists.
        ([{"key": "VMS-666", "branches": ["master", "vms_4.1"]}], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
            "source_branch": "existing_branch",
        }),
        # Fail to create follow-up merge request if the merge request for the given source and
        # target branches already exists and is opened.
        ([{
            "key": "VMS-666",
            "branches": ["master", "vms_4.1"],
            "merge_requests": [MERGED_TO_4_1_MERGE_REQUESTS["opened"]["iid"]]
        }], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
            "source_branch": "feature",
        }),
    ])
    def test_failed_create_followup(self, project, followup_rule, mr, mr_manager, jira):
        # Init project state. TODO: Move project state to parameters.
        MergeRequestMock(
            project=project, source_branch="feature_vms_4.1",
            **MERGED_TO_4_1_MERGE_REQUESTS["opened"])
        project.branches.create({"branch": "existing_branch_vms_4.1", "ref": "vms_4.1"})

        assert not followup_rule.execute(mr_manager)

        issue = jira._jira.issue("VMS-666")
        assert len(issue.fields.comment.comments) == 1, (
            f"Got Jira issue comments: {issue.fields.comment.comments}")
        assert issue.fields.comment.comments[0].body.startswith(
            "An error occured while trying to execute follow-up actions for merge request ")

        assert len(mr.comments()) == 0
        emojis = mr.awardemojis.list()

        assert not any(
            e for e in emojis if e.name == AwardEmojiManager.FOLLOWUP_CREATED_EMOJI), (
            'Hasn\'t "follow-up created" emoji.')

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Squashed merge request (issue detection from the title).
        ([{"key": "VMS-666", "branches": ["master", "vms_4.1"]}], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
        # Three target branches.
        ([{"key": "VMS-666", "branches": ["master", "vms_4.1", "vms_4.2"]}], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
        # More than one commit.
        ([{"key": "VMS-666", "branches": ["master", "vms_4.1"]}], {
            "state": "merged",
            "title": "Test mr",
            "description": "blah blah blah Closes VMS-666",
            "commits_list": [
                {"sha": "a24", "message": "message 1"},
                {"sha": "a25", "message": "message 2"},
            ]
        }),
        # Conflicting merge request.
        ([{"key": "VMS-666", "branches": ["master", "vms_4.1"]}], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "squash_commit_sha": CONFLICTING_COMMIT_SHA,
            "target_branch": "master",  # "vms_4.1" is a branch to create follow-up merge request.
            "source_branch": "feature",
            "commits_list": [{"sha": CONFLICTING_COMMIT_SHA, "message": "message 1"}],
        }),
        # More than one commit, one is conflicting.
        ([{"key": "VMS-666", "branches": ["master", "vms_4.1"]}], {
            "state": "merged",
            "title": "Test mr",
            "description": "blah blah blah Closes VMS-666",
            "target_branch": "master",  # "vms_4.1" is a branch to create follow-up merge request.
            "source_branch": "feature",
            "commits_list": [
                {"sha": "a24", "message": "message 1"},
                {"sha": CONFLICTING_COMMIT_SHA, "message": "message 2"}
            ],
        }),
        # Has opened merge requests to follow-up branches.
        ([{
            "key": "VMS-666",
            "branches": ["master", "vms_4.1"],
            "merge_requests": [MERGED_TO_4_1_MERGE_REQUESTS["opened"]["iid"]],
        }], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
        # Has merged merge requests to follow-up branches.
        ([{
            "key": "VMS-666",
            "branches": ["master", "vms_4.1"],
            "merge_requests": [MERGED_TO_4_1_MERGE_REQUESTS["merged"]["iid"]]
        }], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
    ])
    def test_create_followup(self, project, followup_rule, mr, mr_manager, jira):
        # Init project state. TODO: Move project state to parameters.
        MergeRequestMock(project=project, **MERGED_TO_4_1_MERGE_REQUESTS["opened"])
        MergeRequestMock(project=project, **MERGED_TO_4_1_MERGE_REQUESTS["merged"])
        project.branches.create({"branch": "existing_branch_vms_4.1", "ref": "vms_4.1"})
        project.branches.mock_conflicts["feature_vms_4.1"] = {CONFLICTING_COMMIT_SHA}
        project.branches.mock_conflicts["existing_branch_vms_4.1"] = {CONFLICTING_COMMIT_SHA}

        before_mergrequests_count = len(project.mergerequests.list())

        assert followup_rule.execute(mr_manager)

        issue = jira._jira.issue("VMS-666")
        assert issue.fields.status.name != "Closed"
        assert len(issue.fields.comment.comments) == 1, (
            f"Got Jira issue comments: {issue.fields.comment.comments}")
        assert issue.fields.comment.comments[0].body.startswith(
            "Merge requests for cherry-picking changes were autocreated ")

        assert len(mr.comments()) == 1
        follow_up_created_comment_token = (
            f":{AwardEmojiManager.FOLLOWUP_CREATED_EMOJI}: Follow-up merge request added")
        assert follow_up_created_comment_token in mr.comments()[0]

        mrs = project.mergerequests.list()
        assert len(mrs) == before_mergrequests_count + 1

        new_mr = sorted(mrs, key=lambda mr: mr.iid)[-1]
        assert re.match(r"(VMS-666: )?\(vms_4.1\) ", new_mr.title)

        emojis = new_mr.awardemojis.list()
        assert any(
            e for e in emojis if e.name == AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI), (
            'Is follow-up merge request')

        new_comments = new_mr.comments()
        has_conflicts = mr.squash_commit_sha == CONFLICTING_COMMIT_SHA or any(
            mr for mr in mr.commits() if mr.sha == CONFLICTING_COMMIT_SHA)
        if has_conflicts:
            assert len(new_mr.commits()) == len(mr.commits()) - 1
            assert len(new_comments) == 2
            assert new_comments[1].startswith(
                f"### :{AwardEmojiManager.CHERRY_PICK_EMOJI}: Manual conflict resolution required")
        else:
            assert len(new_mr.commits()) == len(mr.commits())
            assert len(new_comments) == 1

        assert new_comments[0].startswith(
            f"### :{AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI}: Follow-up merge request")

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Has opened merge requests to follow-up branches, follow-up merge request just merged,
        # issue is in "good" state.
        ([{
            "key": "VMS-666",
            "branches": ["master", "vms_4.1"],
            "merge_requests": [MERGED_TO_4_1_MERGE_REQUESTS["opened"]["iid"]],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
        # Has one merged and one opened merge request to follow-up branches, follow-up merge
        # request just merged, issue is in "good" state.
        ([{
            "key": "VMS-666",
            "branches": ["master", "vms_4.1", "vms_4.2"],
            "merge_requests": [
                MERGED_TO_4_1_MERGE_REQUESTS["opened"]["iid"],
                MERGED_TO_4_2_MERGE_REQUESTS["merged"]["iid"]
            ],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        })
    ])
    def test_dont_close_jira_issue(self, project, followup_rule, mr, mr_manager, jira):
        # Init project state. TODO: Move project state to parameters.
        MergeRequestMock(project=project, **MERGED_TO_MASTER_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_4_1_MERGE_REQUESTS["opened"])
        MergeRequestMock(project=project, **MERGED_TO_4_2_MERGE_REQUESTS["merged"])

        mr_count_before = len(project.mergerequests.list())
        issue = jira._jira.issue("VMS-666")
        issue_state_before = issue.fields.status.name

        assert followup_rule.execute(mr_manager)
        assert len(mr.comments()) == 0
        assert len(project.mergerequests.list()) == mr_count_before

        issue = jira._jira.issue("VMS-666")
        assert issue.fields.status.name == issue_state_before
        assert len(issue.fields.comment.comments) == 0

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Has merged merge requests for all issue branches, follow-up merge request just merged,
        # issue is in uncloseable state.
        ([{
            "key": "VMS-666",
            "branches": ["master", "vms_4.1"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "Open",
        }], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_4.1",
        }),
    ])
    def test_failed_close_jira_issue(self, project, followup_rule, mr, mr_manager, jira):
        # Init project state. TODO: Move project state to parameters.
        MergeRequestMock(project=project, **MERGED_TO_MASTER_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_4_1_MERGE_REQUESTS["opened"])
        MergeRequestMock(project=project, **MERGED_TO_4_2_MERGE_REQUESTS["merged"])

        mr_count_before = len(project.mergerequests.list())
        issue = jira._jira.issue("VMS-666")
        issue_state_before = issue.fields.status.name

        assert not followup_rule.execute(mr_manager)
        assert len(mr.comments()) == 0
        assert len(project.mergerequests.list()) == mr_count_before

        issue = jira._jira.issue("VMS-666")
        assert issue.fields.status.name == issue_state_before
        assert len(issue.fields.comment.comments) == 1
        assert 'Cannot automatically close issue ' in issue.fields.comment.comments[0].body

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Has merged merge requests for all issue branches, follow-up merge request just merged,
        # issue is in "good" state.
        ([{
            "key": "VMS-666",
            "branches": ["master", "vms_4.1"],
            "merge_requests": [
                MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"],
                MERGED_TO_4_1_MERGE_REQUESTS["merged"]["iid"]
            ],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_4.1",
        }),
        # The same that preivous, but Jira issue has three branches.
        ([{
            "key": "VMS-666",
            "branches": ["master", "vms_4.1", "vms_4.2"],
            "merge_requests": [
                MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"],
                MERGED_TO_4_1_MERGE_REQUESTS["merged"]["iid"],
                MERGED_TO_4_2_MERGE_REQUESTS["merged"]["iid"],
            ],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_4.1",
        }),
        # Has merged merge requests for all issue branches, follow-up merge request just merged,
        # issue is in "good" state, follow-up state detection from description.
        ([{
            "key": "VMS-666",
            "branches": ["master", "vms_4.1"],
            "merge_requests": [
                MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"],
                MERGED_TO_4_1_MERGE_REQUESTS["merged"]["iid"]
            ],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "description": (
                "Blah blah blah\n"
                "(cherry picked from commit ca374322a8ce3f481d5d472ba27a394a69ffacea)"),
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_4.1",
        }),
        # The same that preivous, but follow-up state detection from commit messages.
        ([{
            "key": "VMS-666",
            "branches": ["master", "vms_4.1"],
            "merge_requests": [
                MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"],
                MERGED_TO_4_1_MERGE_REQUESTS["merged"]["iid"]
            ],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_4.1",
            "commits_list": [{
                "sha": "a26",
                "message": (
                    "Blah blah blah\n"
                    "(cherry picked from commit ca374322a8ce3f481d5d472ba27a394a69ffacea)"),
            }],
        }),
        # Closes more than one issue (detection from description).
        ([
            {
                "key": "VMS-666",
                "branches": ["master", "vms_4.1"],
                "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
                "state": "In Review",
            },
            {
                "key": "VMS-667",
                "branches": ["master", "vms_4.1"],
                "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
                "state": "In Review",
            }
        ], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "description": "Closes VMS-666, Closes VMS-667",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_4.1",
        }),
        # Closes more than one issue (detection from title).
        ([
            {
                "key": "VMS-666",
                "branches": ["master", "vms_4.1"],
                "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
                "state": "In Review",
            },
            {
                "key": "VMS-667",
                "branches": ["master", "vms_4.1"],
                "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
                "state": "In Review",
            }
        ], {
            "state": "merged",
            "title": "VMS-666, VMS-667: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_4.1",
        }),
        # Has merged merge requests for all issue branches, follow-up merge request just merged,
        # issue is in "In progress" state which is not right but bot can fix it.
        ([{
            "key": "VMS-666",
            "branches": ["master", "vms_4.1"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "In progress",
        }], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_4.1",
        }),
        # No unmerged branches in jira issue, primary merge request just merged, issue is in "good"
        # state.
        ([{"key": "VMS-666", "branches": ["master"], "state": "In Review"}], {
            "state": "merged",
            "title": "VMS-666: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        })
    ])
    def test_close_jira_issue(self, project, followup_rule, mr, mr_manager, jira):
        # Init project state. TODO: Move project state to parameters.
        MergeRequestMock(project=project, **MERGED_TO_MASTER_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_4_1_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_4_2_MERGE_REQUESTS["merged"])

        mr_count_before = len(project.mergerequests.list())

        assert followup_rule.execute(mr_manager)
        assert len(mr.comments()) == 0
        assert len(project.mergerequests.list()) == mr_count_before

        issue = jira._jira.issue("VMS-666")
        assert issue.fields.status.name == "Closed"
        assert len(issue.fields.comment.comments) == 1
        assert issue.fields.comment.comments[0].body.startswith("Issue closed")
