## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import re
import pytest

from robocat.award_emoji_manager import AwardEmojiManager
from robocat.bot import GitlabEventData, GitlabCommentEventData, GitlabEventType
from robocat.note import MessageId
from automation_tools.tests.gitlab_constants import (
    DEFAULT_COMMIT,
    DEFAULT_NXLIB_COMMIT,
    DEFAULT_PROJECT_ID,
    FORK_PROJECT_ID,
    DEFAULT_JIRA_ISSUE_KEY,
    NXLIB_JIRA_ISSUE_KEY,
    CONFLICTING_COMMIT_SHA,
    MERGED_TO_MASTER_MERGE_REQUESTS,
    MERGED_TO_5_1_MERGE_REQUESTS,
    MERGED_TO_4_2_MERGE_REQUESTS,
    BOT_USERNAME)
from tests.fixtures import *


class TestFollowUpRule:
    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Don't create follow-up merge request for opened merge request.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "opened",
        }),
        # Don't create follow-up merge request for follow-up merge requests.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "merged",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI]
        }),
    ])
    def test_dont_create_follow_up(
            self, project, follow_up_rule, mr, mr_manager, jira, repo_accessor):
        # Init git repo state. TODO: Move git repo state to parameters.

        project_remote = project.namespace["full_path"]
        repo_accessor.create_branch(
            target_remote=project_remote, new_branch="vms_5.1", source_branch="master")
        for c in mr.commits_list:
            repo_accessor.repo.add_mock_commit(c["sha"], c["message"])
        repo_accessor.repo.remotes[project_remote].mock_attach_gitlab_project(project)

        # Start tests.
        for repetition in range(2):
            assert follow_up_rule.execute(mr_manager) in (
                follow_up_rule.ExecutionResult.rule_execution_successful,
                follow_up_rule.ExecutionResult.not_eligible)

            issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
            assert len(issue.fields.comment.comments) == 0, (
                f"Got Jira issue comments: {issue.fields.comment.comments}")

            if mr_manager.data.is_merged:
                assert len(mr.mock_comments()) == repetition + 1, (
                    f"Got merge request comments: {mr.mock_comments()}")
                assert MessageId.FollowUpNotNeeded.value in mr.mock_comments()[-1], (
                    f"Last comment is: {mr.mock_comments()[-1]}")
            else:
                assert len(mr.mock_comments()) == 0, (
                    f"Got merge request comments: {mr.mock_comments()}")

            emojis = mr.awardemojis.list()
            assert not any(
                e for e in emojis if e.name == AwardEmojiManager.FOLLOWUP_CREATED_EMOJI), (
                'Hasn\'t "follow-up created" emoji.')

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Fail to create follow-up merge request if the merge request for the given source and
        # target branches already exists and is opened.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [MERGED_TO_5_1_MERGE_REQUESTS["opened"]["iid"]]
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
            "source_branch": "feature",
        }),
    ])
    def test_failed_create_follow_up(
            self, project, follow_up_rule, mr, mr_manager, jira, repo_accessor):
        # Init project state. TODO: Move project state to parameters.
        MergeRequestMock(
            project=project, source_branch="feature_vms_5.1",
            **MERGED_TO_5_1_MERGE_REQUESTS["opened"])
        repo_accessor.repo.mock_add_gitlab_project(project)
        repo_accessor.repo.add_mock_commit(DEFAULT_COMMIT["sha"], DEFAULT_COMMIT["message"])

        assert follow_up_rule.execute(mr_manager)

        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        assert len(issue.fields.comment.comments) == 0, (
            f"Got Jira issue comments: {issue.fields.comment.comments}")

        comments = mr.mock_comments()
        assert len(comments) == 1
        assert comments[0].startswith(
            f"### :{AwardEmojiManager.CHECK_FAIL_EXPLANATION_EMOJI}: "
            "Follow-up Merge Request already exists")

        emojis = mr.awardemojis.list()
        assert not any(
            e for e in emojis if e.name == AwardEmojiManager.FOLLOWUP_CREATED_EMOJI), (
            'Hasn\'t "follow-up created" emoji.')

    @pytest.mark.parametrize(("jira_issues", "mr_state", "robocat_approval"), [
        # Squashed merge request (issue detection from the title).
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }, False),
        # Same, but needs Robocat approval.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }, True),
        # More than one Issue in the title.
        ([
            {"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]},
            {"key": f"{DEFAULT_JIRA_ISSUE_KEY}1", "branches": ["master", "vms_5.1"]}
        ], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, {DEFAULT_JIRA_ISSUE_KEY}1: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }, False),
        # Three target branches.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1", "vms_4.2"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }, False),
        # More than one commit.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "description": f"blah blah blah Closes {DEFAULT_JIRA_ISSUE_KEY}",
            "commits_list": [
                {"sha": "a24", "message": "message 1"},
                {"sha": "a25", "message": "message 2"},
            ]
        }, False),
        # Has opened merge requests to follow-up branches.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [MERGED_TO_5_1_MERGE_REQUESTS["opened"]["iid"]],
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }, False),
        # Has merged merge requests to follow-up branches.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [MERGED_TO_5_1_MERGE_REQUESTS["merged"]["iid"]]
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }, False),
        # Merge request from the different project.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "source_project_id": FORK_PROJECT_ID,
            "target_branch": "master",
        }, False),
    ])
    def test_create_follow_up(
            self, project, follow_up_rule, mr, mr_manager, jira, repo_accessor, robocat_approval):
        # Init project state. TODO: Move project state to parameters.
        project.branches.create({"branch": "existing_branch_vms_5.1"})
        follow_up_rule._needs_robocat_approval = robocat_approval

        # Set the source project for the MR. If it is not default project, create it.

        if mr.source_project_id != DEFAULT_PROJECT_ID:
            source_project = ProjectMock(id=mr.source_project_id, manager=project.manager)
            for c in mr.commits_list:
                source_project.add_mock_commit("master", c["sha"], c["message"])
        else:
            source_project = project

        # Init git repo state. TODO: Move git repo state to parameters.

        project_remote = project.namespace["full_path"]
        repo_accessor.create_branch(
            target_remote=project_remote, new_branch="vms_5.1", source_branch="master")
        for c in mr.commits_list:
            repo_accessor.repo.add_mock_commit(c["sha"], c["message"])
        repo_accessor.repo.remotes[project_remote].mock_attach_gitlab_project(project)
        repo_accessor.repo.mock_add_gitlab_project(source_project)

        # Start tests.

        before_mergrequests_count = len(project.mergerequests.list())
        assert follow_up_rule.execute(mr_manager)

        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        assert issue.fields.status.name != "Closed"
        assert len(issue.fields.comment.comments) == 1, (
            f"Got Jira issue comments: {issue.fields.comment.comments}")
        assert issue.fields.comment.comments[0].body.startswith(
            "Merge requests for cherry-picking changes were autocreated")

        assert len(mr.mock_comments()) == len(issue.fields.fixVersions) - 1
        follow_up_created_comment_token = (
            f":{AwardEmojiManager.FOLLOWUP_CREATED_EMOJI}: Follow-up merge request added")
        assert follow_up_created_comment_token in mr.mock_comments()[0]

        source_project_branches = [b.name for b in source_project.branches.list()]
        assert f"{mr.source_branch}_vms_5.1" in source_project_branches, (
            f"New branch {mr.source_branch}_vms_5.1 is not created: "
            f"{source_project_branches}")

        if project != source_project:
            project_branches = [b.name for b in project.branches.branches]
            assert f"{mr.source_branch}_vms_5.1" not in project_branches, (
                f"Branch {mr.source_branch}_vms_5.1 created in the wrong project")

        mrs = project.mergerequests.list()
        assert len(mrs) == before_mergrequests_count + len(issue.fields.fixVersions) - 1

        new_mr = sorted(mrs, key=lambda mr: mr.iid)[-1]
        assert re.match(
            rf"({DEFAULT_JIRA_ISSUE_KEY}(, {DEFAULT_JIRA_ISSUE_KEY}1)?: )\(master->vms_\d+.+?\) ",
            new_mr.title)

        emojis = new_mr.awardemojis.list()
        assert any(
            e for e in emojis if e.name == AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI), (
            'Is follow-up merge request')

        new_comments = new_mr.mock_comments()

        assert len(new_mr.commits()) == len(mr.commits())
        assert len(new_comments) == 1
        assert not new_mr.work_in_progress, "New MR is in Draft state."
        assert new_mr.blocking_discussions_resolved, "Unresolved thread found"
        assert new_comments[0].startswith(
            f"### :{AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI}: Follow-up merge request")

        if robocat_approval:
            new_mr_approved_by = new_mr.approvals.get().approved_by
            assert any(
                u for u in new_mr_approved_by if u["user"]["username"] == BOT_USERNAME), (
                f"No {BOT_USERNAME} approval found in {new_mr_approved_by!r}")

    @pytest.mark.parametrize(
        ("jira_issues", "mr_state", "expected_mr_count", "creation_failed_message_fragment"),
        [
            # Create follow-up merge request if the fixVersions field contains Release without the
            # defined branch.
            ([
                {"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1", ""]},
            ], {
                "state": "merged",
                "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
                "squash_commit_sha": DEFAULT_COMMIT["sha"],
                "target_branch": "master",
            }, 2, 'Cannot create the follow-up for version `Unknown version`'),
        ])
    def test_create_follow_up_partially(
            self,
            project,
            follow_up_rule,
            mr,
            mr_manager,
            jira,
            repo_accessor,
            expected_mr_count,
            creation_failed_message_fragment):
        # Init git repo state.
        # TODO: Move git repo state to parameters.

        project_remote = project.namespace["full_path"]
        repo_accessor.create_branch(
            target_remote=project_remote, new_branch="vms_5.1", source_branch="master")
        for c in mr.commits_list:
            repo_accessor.repo.add_mock_commit(c["sha"], c["message"])
        repo_accessor.repo.remotes[project_remote].mock_attach_gitlab_project(project)
        repo_accessor.repo.mock_add_gitlab_project(project)

        # Start tests.

        assert follow_up_rule.execute(mr_manager)

        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        assert len(mr.mock_comments()) == len(issue.fields.fixVersions) - 1

        follow_up_created_comment_token = (
            f":{AwardEmojiManager.FOLLOWUP_CREATED_EMOJI}: Follow-up merge request added")
        assert follow_up_created_comment_token in mr.mock_comments()[0]
        assert creation_failed_message_fragment in mr.mock_comments()[1]

        mrs = project.mergerequests.list()
        assert len(mrs) == expected_mr_count

    @pytest.mark.parametrize(("jira_issues", "mr_state", "is_ready_to_merge"), [
        # Conflicting merge request.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": CONFLICTING_COMMIT_SHA,
            # "vms_5.1" is a branch to create follow-up merge request.
            "target_branch": "master",
            "source_branch": "feature",
            "commits_list": [{"sha": CONFLICTING_COMMIT_SHA, "message": "message 1"}],
        }, True),
        # More than one commit, one is conflicting.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "description": f"blah blah blah Closes {DEFAULT_JIRA_ISSUE_KEY}",
            # "vms_5.1" is a branch to create follow-up merge request.
            "target_branch": "master",
            "source_branch": "feature",
            "commits_list": [
                {"sha": "a24", "message": "message 1"},
                {"sha": CONFLICTING_COMMIT_SHA, "message": "message 2"}
            ],
        }, False),
    ])
    def test_create_follow_up_with_conflicts(
            self, project, follow_up_rule, mr, mr_manager, jira, repo_accessor, is_ready_to_merge):
        # TODO: Move project and repo state to parameters (create an appropriate fixture).

        # Init project state.
        project.branches.create({"branch": "existing_branch_vms_5.1"})

        # Init git repo state.
        project_remote = project.namespace["full_path"]
        repo_accessor.create_branch(
            target_remote=project_remote, new_branch="vms_5.1", source_branch="master")
        for c in mr.commits_list:
            repo_accessor.repo.add_mock_commit(c["sha"], c["message"])
        repo_accessor.repo.remotes[project_remote].mock_attach_gitlab_project(project)
        repo_accessor.repo.mock_add_gitlab_project(project)
        repo_accessor.repo.mock_cherry_pick_conflicts.append(CONFLICTING_COMMIT_SHA)

        # Enforce to check that Robocat does not approve conflicting MRs.
        follow_up_rule._needs_robocat_approval = True

        # Start tests.

        before_mergrequests_count = len(project.mergerequests.list())
        assert follow_up_rule.execute(mr_manager)

        mrs = project.mergerequests.list()
        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        assert len(mrs) == before_mergrequests_count + len(issue.fields.fixVersions) - 1

        new_mr = sorted(mrs, key=lambda mr: mr.iid)[-1]
        assert len(new_mr.commits()) == len(mr.commits()) - 1
        assert not new_mr.work_in_progress, "New MR is in Draft state."

        new_comments = new_mr.mock_comments()
        assert len(new_comments) == 2
        assert new_comments[0].startswith(
            f"### :{AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI}: Follow-up merge request")
        assert new_comments[1].startswith(
            f"### :{AwardEmojiManager.CHERRY_PICK_EMOJI}: Manual conflict resolution required")

        assert new_mr.blocking_discussions_resolved == is_ready_to_merge, (
            f"Should{'' if is_ready_to_merge else ' not'} be ready for merge")

        assert len(new_mr.approvals.get().approved_by) == 0, "Shouldn't be approved by Robocat"

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Squashed merge request (issue detection from the title).
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "state": "In Review"
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
    ])
    def test_empty_follow_up(self, project, follow_up_rule, mr, mr_manager, jira, repo_accessor):
        # Init git repo state. TODO: Move git repo state to parameters.

        project_remote = project.namespace["full_path"]
        repo_accessor.create_branch(
            target_remote=project_remote, new_branch="vms_5.1", source_branch="master")
        for c in mr.commits_list:
            repo_accessor.repo.add_mock_commit(c["sha"], c["message"])
        repo_accessor.repo.remotes[project_remote].mock_attach_gitlab_project(project)
        repo_accessor.repo.mock_changes_already_in_branch.append(DEFAULT_COMMIT["sha"])

        # Start tests.

        before_mergrequests_count = len(project.mergerequests.list())
        assert follow_up_rule.execute(mr_manager)

        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        assert issue.fields.status.name == "In Review"
        assert len(issue.fields.comment.comments) == 0, (
            f"Got Jira issue comments: {issue.fields.comment.comments}")
        assert before_mergrequests_count == len(project.mergerequests.list()), (
            "New Merge Request was created")

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Has opened merge requests to follow-up branches, follow-up merge request just merged,
        # issue is in "good" state.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [MERGED_TO_5_1_MERGE_REQUESTS["opened"]["iid"]],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
        # Has one merged and one opened merge request to follow-up branches, follow-up merge
        # request just merged, issue is in "good" state.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1", "vms_4.2"],
            "merge_requests": [
                MERGED_TO_5_1_MERGE_REQUESTS["opened"]["iid"],
                MERGED_TO_4_2_MERGE_REQUESTS["merged"]["iid"]
            ],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        })
    ])
    def test_dont_close_jira_issue(self, project, follow_up_rule, mr, mr_manager, jira):
        # Init project state. TODO: Move project state to parameters.
        MergeRequestMock(project=project, **MERGED_TO_MASTER_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_5_1_MERGE_REQUESTS["opened"])
        MergeRequestMock(project=project, **MERGED_TO_4_2_MERGE_REQUESTS["merged"])

        mr_count_before = len(project.mergerequests.list())
        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        issue_state_before = issue.fields.status.name

        assert follow_up_rule.execute(mr_manager)
        assert len(mr.mock_comments()) == 1
        assert MessageId.FollowUpNotNeeded.value in mr.mock_comments()[-1], (
            f"Last comment is: {mr.mock_comments()[-1]}")
        assert len(project.mergerequests.list()) == mr_count_before

        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        assert issue.fields.status.name == issue_state_before
        assert len(issue.fields.comment.comments) == 0

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Has merged merge requests for all issue branches, follow-up merge request just merged,
        # but the Issue has "Open" status.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "Open",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_5.1",
        }),
    ])
    def test_bad_jira_issue_status(self, project, follow_up_rule, mr, mr_manager, jira):
        # Init project state. TODO: Move project state to parameters.
        MergeRequestMock(project=project, **MERGED_TO_MASTER_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_5_1_MERGE_REQUESTS["opened"])
        MergeRequestMock(project=project, **MERGED_TO_4_2_MERGE_REQUESTS["merged"])

        mr_count_before = len(project.mergerequests.list())
        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        issue_state_before = issue.fields.status.name

        assert follow_up_rule.execute(mr_manager)
        assert len(mr.mock_comments()) == 1
        assert MessageId.FollowUpNotNeeded.value in mr.mock_comments()[-1], (
            f"Last comment is: {mr.mock_comments()[-1]}")
        assert len(project.mergerequests.list()) == mr_count_before

        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        assert issue.fields.status.name == issue_state_before
        assert len(issue.fields.comment.comments) == 0

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Has merged Merge Requests for all Issue branches, follow-up Merge Request was just
        # merged, but the Issue has "In progress" status.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "In progress",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_5.1",
        }),
        # The same that the previous but for the project with the custom status config.
        ([{
            "key": NXLIB_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "IN PROGRESS",
        }], {
            "state": "merged",
            "title": f"{NXLIB_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_NXLIB_COMMIT["sha"],
            "target_branch": "vms_5.1",
        }),
    ])
    def test_in_progress_jira_issue(
            self, project, follow_up_rule, mr, mr_manager, jira, jira_issues):
        # Init the Project state.
        # TODO: Move the Project state to parameters.
        MergeRequestMock(project=project, **MERGED_TO_MASTER_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_5_1_MERGE_REQUESTS["opened"])
        MergeRequestMock(project=project, **MERGED_TO_4_2_MERGE_REQUESTS["merged"])

        mr_count_before = len(project.mergerequests.list())
        issue = jira._jira.issue(jira_issues[0]["key"])
        issue_state_before = issue.fields.status.name

        assert follow_up_rule.execute(mr_manager)
        assert len(project.mergerequests.list()) == mr_count_before
        comments = mr.mock_comments()
        assert len(comments) == 1
        assert MessageId.FollowUpNotNeeded.value in comments[0], (
            f"First comment is: {comments[0]}")

        issue = jira._jira.issue(jira_issues[0]["key"])
        assert issue.fields.status.name == issue_state_before
        assert len(issue.fields.comment.comments) == 0

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Has merged Merge Requests for all Issue branches, follow-up Merge Request was just
        # merged, but the Issue has "Closed" status.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "Closed",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_5.1",
        }),
        # The same as previous, but the Issue has "Waiting for QA" status.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "Waiting for QA",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_5.1",
        }),
        # The same as the first, but for the project with the custom status config.
        ([{
            "key": NXLIB_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "DONE",
        }], {
            "state": "merged",
            "title": f"{NXLIB_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_NXLIB_COMMIT["sha"],
            "target_branch": "vms_5.1",
        }),
    ])
    def test_finalized_jira_issue(
            self, project, follow_up_rule, mr, mr_manager, jira, jira_issues):
        # Init the Project state.
        # TODO: Move the Project state to parameters.
        MergeRequestMock(project=project, **MERGED_TO_MASTER_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_5_1_MERGE_REQUESTS["opened"])
        MergeRequestMock(project=project, **MERGED_TO_4_2_MERGE_REQUESTS["merged"])

        mr_count_before = len(project.mergerequests.list())
        issue = jira._jira.issue(jira_issues[0]["key"])
        issue_state_before = issue.fields.status.name

        assert follow_up_rule.execute(mr_manager)
        assert len(project.mergerequests.list()) == mr_count_before
        assert len(mr.mock_comments()) == 1
        assert MessageId.FollowUpNotNeeded.value in mr.mock_comments()[0], (
            f"First comment is: {mr.mock_comments()[0]}")

        issue = jira._jira.issue(jira_issues[0]["key"])
        assert issue.fields.status.name == issue_state_before
        assert len(issue.fields.comment.comments) == 0

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Squashed merge request (issue detection from the title).
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "opened",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
    ])
    def test_create_draft_follow_up_mr(
            self, bot: Bot, project, follow_up_rule, mr, mr_manager, repo_accessor):
        # Init git repo state. TODO: Move git repo state to parameters.

        project_remote = project.namespace["full_path"]
        repo_accessor.create_branch(
            target_remote=project_remote, new_branch="vms_5.1", source_branch="master")
        for c in mr.commits_list:
            repo_accessor.repo.add_mock_commit(c["sha"], c["message"])
        repo_accessor.repo.remotes[project_remote].mock_attach_gitlab_project(project)
        repo_accessor.repo.mock_add_gitlab_project(project)
        repo_accessor.repo.mock_cherry_pick_conflicts.append(CONFLICTING_COMMIT_SHA)

        # Start tests

        # Set follow-up draft mode.
        payload = GitlabCommentEventData(
            mr_id=mr.iid, added_comment=f"@{BOT_USERNAME} draft-follow-up")
        event_data = GitlabEventData(
            payload=payload, event_type=GitlabEventType.comment)
        bot.process_event(event_data)
        mr_manager._mr.load_discussions()

        # If the Merge Request is already merged, the follow-ups should be created during
        # "draft-follow-up" command execution; otherwise merge this MR and run follow_up_rule.
        if mr.state != "merged":
            mr.merge()
            assert follow_up_rule.execute(mr_manager)

        mrs = project.mergerequests.list()
        assert len(mrs) == 2, "Follow-up Merge Request not created."

        new_mr = sorted(mrs, key=lambda mr: mr.iid)[-1]
        assert new_mr.work_in_progress, "New MR is not in Draft state."

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        ([], {
            # Assuming no JIRA issues are required for this test
            "title": "Raise webadmin version to e8caf7b085a3ef60e71651e65a6b4e8975746f88",
            "state": "merged",
        }),
    ])
    def test_skip_followup_for_webadmin_mr(self, jira_issues, follow_up_rule, mr_manager, jira):
        assert follow_up_rule.execute(mr_manager) == follow_up_rule.ExecutionResult.filtered_out
