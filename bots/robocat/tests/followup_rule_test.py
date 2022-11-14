import re
import pytest

from automation_tools.tests.fixtures import jira, repo_accessor
from automation_tools.tests.mocks.git_mocks import RemoteMock
from robocat.award_emoji_manager import AwardEmojiManager
from robocat.bot import GitlabEventData, GitlabEventType
from automation_tools.tests.gitlab_constants import (
    DEFAULT_COMMIT,
    DEFAULT_NXLIB_COMMIT,
    DEFAULT_PROJECT_ID,
    FORK_PROJECT_ID,
    DEFAULT_JIRA_ISSUE_KEY,
    NXLIB_JIRA_ISSUE_KEY,
    CONFLICTING_COMMIT_SHA,
    MERGED_TO_MASTER_MERGE_REQUESTS,
    MERGED_TO_4_1_MERGE_REQUESTS,
    MERGED_TO_4_2_MERGE_REQUESTS,
    MERGED_TO_MASTER_MERGE_REQUESTS_MOBILE,
    MERGED_TO_21_1_MERGE_REQUESTS_MOBILE,
    MERGED_TO_MASTER_MERGE_REQUESTS_CB,
    MERGED_TO_20_1_MERGE_REQUESTS_CB)
from tests.fixtures import *


class TestFollowupRule:
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
    def test_dont_create_followup(
            self, project, followup_rule, mr, mr_manager, jira, repo_accessor):
        # Init git repo state. TODO: Move git repo state to parameters.

        project_remote = project.namespace["full_path"]
        repo_accessor.create_branch(
            target_remote=project_remote, new_branch="vms_5.1", source_branch="master")
        for c in mr.commits_list:
            repo_accessor.repo.add_mock_commit(c["sha"], c["message"])
        repo_accessor.repo.remotes[project_remote].mock_attach_gitlab_project(project)

        # Start tests.

        for _ in range(2):
            assert followup_rule.execute(mr_manager) in (
                followup_rule.ExecutionResult.rule_execution_successful,
                followup_rule.ExecutionResult.not_eligible)

            issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
            assert len(issue.fields.comment.comments) == 0, (
                f"Got Jira issue comments: {issue.fields.comment.comments}")

            assert len(mr.mock_comments()) == 0, (
                f"Got merge request comments: {mr.mock_comments()}")

            emojis = mr.awardemojis.list()
            assert not any(
                e for e in emojis if e.name == AwardEmojiManager.FOLLOWUP_CREATED_EMOJI), (
                'Hasn\'t "follow-up created" emoji.')

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Fail to create follow-up merge request if the target branch already exists.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
            "source_branch": "existing_branch",
        }),
        # Fail to create follow-up merge request if the merge request for the given source and
        # target branches already exists and is opened.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [MERGED_TO_4_1_MERGE_REQUESTS["opened"]["iid"]]
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
            "source_branch": "feature",
        }),
    ])
    def test_failed_create_followup(self, project, followup_rule, mr, mr_manager, jira):
        # Init project state. TODO: Move project state to parameters.
        MergeRequestMock(
            project=project, source_branch="feature_vms_5.1",
            **MERGED_TO_4_1_MERGE_REQUESTS["opened"])
        project.branches.create(
            {"branch": "existing_branch_vms_5.1", "ref": "vms_5.1"})

        assert not followup_rule.execute(mr_manager)

        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        assert len(issue.fields.comment.comments) == 1, (
            f"Got Jira issue comments: {issue.fields.comment.comments}")
        assert issue.fields.comment.comments[0].body.startswith(
            "An error occurred while trying to execute follow-up actions for merge request")

        assert len(mr.mock_comments()) == 0
        emojis = mr.awardemojis.list()

        assert not any(
            e for e in emojis if e.name == AwardEmojiManager.FOLLOWUP_CREATED_EMOJI), (
            'Hasn\'t "follow-up created" emoji.')

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Squashed merge request (issue detection from the title).
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
        # Three target branches.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1", "vms_4.2"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
        # More than one commit.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "description": f"blah blah blah Closes {DEFAULT_JIRA_ISSUE_KEY}",
            "commits_list": [
                {"sha": "a24", "message": "message 1"},
                {"sha": "a25", "message": "message 2"},
            ]
        }),
        # Conflicting merge request.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": CONFLICTING_COMMIT_SHA,
            # "vms_5.1" is a branch to create follow-up merge request.
            "target_branch": "master",
            "source_branch": "feature",
            "commits_list": [{"sha": CONFLICTING_COMMIT_SHA, "message": "message 1"}],
        }),
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
        }),
        # Has opened merge requests to follow-up branches.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [MERGED_TO_4_1_MERGE_REQUESTS["opened"]["iid"]],
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
        # Has merged merge requests to follow-up branches.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [MERGED_TO_4_1_MERGE_REQUESTS["merged"]["iid"]]
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
        # Merge request from the different project.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_5.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "source_project_id": FORK_PROJECT_ID,
            "target_branch": "master",
        }),
    ])
    def test_create_followup(self, project, followup_rule, mr, mr_manager, jira, repo_accessor):
        # Init project state. TODO: Move project state to parameters.

        MergeRequestMock(project=project, **MERGED_TO_4_1_MERGE_REQUESTS["opened"])
        MergeRequestMock(project=project, **MERGED_TO_4_1_MERGE_REQUESTS["merged"])
        project.branches.create({"branch": "existing_branch_vms_5.1"})

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
        repo_accessor.create_branch(
            target_remote=project_remote, new_branch="vms_4.2", source_branch="master")
        for c in mr.commits_list:
            repo_accessor.repo.add_mock_commit(c["sha"], c["message"])
        repo_accessor.repo.remotes[project_remote].mock_attach_gitlab_project(project)
        repo_accessor.repo.mock_add_gitlab_project(source_project)
        repo_accessor.repo.mock_cherry_pick_conflicts.append(CONFLICTING_COMMIT_SHA)

        # Start tests.

        before_mergrequests_count = len(project.mergerequests.list())
        assert followup_rule.execute(mr_manager)

        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        assert issue.fields.status.name != "Closed"
        assert len(issue.fields.comment.comments) == 1, (
            f"Got Jira issue comments: {issue.fields.comment.comments}")
        assert issue.fields.comment.comments[0].body.startswith(
            "Merge requests for cherry-picking changes were autocreated ")

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
        assert re.match(rf"({DEFAULT_JIRA_ISSUE_KEY}: )?\(master->vms_(5|4)\..+?\) ", new_mr.title)

        emojis = new_mr.awardemojis.list()
        assert any(
            e for e in emojis if e.name == AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI), (
            'Is follow-up merge request')

        new_comments = new_mr.mock_comments()
        has_conflicts = mr.squash_commit_sha == CONFLICTING_COMMIT_SHA or any(
            mr for mr in mr.commits() if mr.sha == CONFLICTING_COMMIT_SHA)
        if has_conflicts:
            assert len(new_mr.commits()) == len(mr.commits()) - 1
            assert len(new_comments) == 2
            assert new_comments[1].startswith(
                f"### :{AwardEmojiManager.CHERRY_PICK_EMOJI}: Manual conflict resolution required")
        else:
            assert len(new_mr.commits()) == len(mr.commits())
            assert not new_mr.work_in_progress, "New MR is in Draft state."
            assert len(new_comments) == 1

        assert new_comments[0].startswith(
            f"### :{AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI}: Follow-up merge request")

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
    def test_empty_followup(self, project, followup_rule, mr, mr_manager, jira, repo_accessor):
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
        assert followup_rule.execute(mr_manager)

        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        assert issue.fields.status.name == "Closed"
        assert len(issue.fields.comment.comments) == 1, (
            f"Got Jira issue comments: {issue.fields.comment.comments}")
        assert issue.fields.comment.comments[0].body.startswith("Issue closed")
        assert before_mergrequests_count == len(project.mergerequests.list()), (
            "New Merge Request was created")

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Has opened merge requests to follow-up branches, follow-up merge request just merged,
        # issue is in "good" state.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [MERGED_TO_4_1_MERGE_REQUESTS["opened"]["iid"]],
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
                MERGED_TO_4_1_MERGE_REQUESTS["opened"]["iid"],
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
    def test_dont_close_jira_issue(self, project, followup_rule, mr, mr_manager, jira):
        # Init project state. TODO: Move project state to parameters.
        MergeRequestMock(project=project, **MERGED_TO_MASTER_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_4_1_MERGE_REQUESTS["opened"])
        MergeRequestMock(project=project, **MERGED_TO_4_2_MERGE_REQUESTS["merged"])

        mr_count_before = len(project.mergerequests.list())
        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        issue_state_before = issue.fields.status.name

        assert followup_rule.execute(mr_manager)
        assert len(mr.mock_comments()) == 0
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
    def test_bad_jira_issue_status(self, project, followup_rule, mr, mr_manager, jira):
        # Init project state. TODO: Move project state to parameters.
        MergeRequestMock(project=project, **MERGED_TO_MASTER_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_4_1_MERGE_REQUESTS["opened"])
        MergeRequestMock(project=project, **MERGED_TO_4_2_MERGE_REQUESTS["merged"])

        mr_count_before = len(project.mergerequests.list())
        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        issue_state_before = issue.fields.status.name

        assert not followup_rule.execute(mr_manager)
        assert len(mr.mock_comments()) == 0
        assert len(project.mergerequests.list()) == mr_count_before

        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        assert issue.fields.status.name == issue_state_before
        assert len(issue.fields.comment.comments) == 1
        assert 'Cannot automatically move to QA or close ' in issue.fields.comment.comments[0].body

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
            self, project, followup_rule, mr, mr_manager, jira, jira_issues):
        # Init the Project state.
        # TODO: Move the Project state to parameters.
        MergeRequestMock(project=project, **MERGED_TO_MASTER_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_4_1_MERGE_REQUESTS["opened"])
        MergeRequestMock(project=project, **MERGED_TO_4_2_MERGE_REQUESTS["merged"])

        mr_count_before = len(project.mergerequests.list())
        issue = jira._jira.issue(jira_issues[0]["key"])
        issue_state_before = issue.fields.status.name

        assert followup_rule.execute(mr_manager)
        assert len(project.mergerequests.list()) == mr_count_before
        comments = mr.mock_comments()
        assert len(comments) == 1
        assert comments[0].startswith(f"### :{AwardEmojiManager.ISSUE_NOT_MOVED_TO_QA_EMOJI}:"), (
            f"Commenti s: {comments[0]}.")

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
    def test_finalized_jira_issue(self, project, followup_rule, mr, mr_manager, jira, jira_issues):
        # Init the Project state.
        # TODO: Move the Project state to parameters.
        MergeRequestMock(project=project, **MERGED_TO_MASTER_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_4_1_MERGE_REQUESTS["opened"])
        MergeRequestMock(project=project, **MERGED_TO_4_2_MERGE_REQUESTS["merged"])

        mr_count_before = len(project.mergerequests.list())
        issue = jira._jira.issue(jira_issues[0]["key"])
        issue_state_before = issue.fields.status.name

        assert followup_rule.execute(mr_manager)
        assert len(project.mergerequests.list()) == mr_count_before
        assert len(mr.mock_comments()) == 0

        issue = jira._jira.issue(jira_issues[0]["key"])
        assert issue.fields.status.name == issue_state_before
        assert len(issue.fields.comment.comments) == 1
        assert 'workflow violation ' in issue.fields.comment.comments[0].body

    @pytest.mark.parametrize(("jira_issues", "mr_state", "expected_status"), [
        # Has merged Merge Requests for all Issue branches, the follow-up Merge Request just
        # merged, the Issue has type "Internal" and is in a "good" state.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [
                MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"],
                MERGED_TO_4_1_MERGE_REQUESTS["merged"]["iid"]
            ],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_5.1",
        }, "Closed"),
        # Has merged Merge Requests for all Issue branches, the follow-up Merge Request just
        # merged, the Issue has type "Internal" and is in a "good" state.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [
                MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"],
                MERGED_TO_4_1_MERGE_REQUESTS["merged"]["iid"]
            ],
            "state": "In Review",
            "typ": "Task",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_5.1",
        }, "Waiting for QA"),
        # The same that the previous case, but the Jira Issue has status "Ready to Merge".
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [
                MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"],
                MERGED_TO_4_1_MERGE_REQUESTS["merged"]["iid"]
            ],
            "state": "Ready to Merge",
            "typ": "Task",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_5.1",
        }, "Waiting for QA"),
        # The same that the first case, but the Jira Issue has three branches.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1", "vms_4.2"],
            "merge_requests": [
                MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"],
                MERGED_TO_4_1_MERGE_REQUESTS["merged"]["iid"],
                MERGED_TO_4_2_MERGE_REQUESTS["merged"]["iid"],
            ],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_5.1",
        }, "Closed"),
        # The same that the first but for the different Jira project.
        ([{
            "key": "MOBILE-666",
            "branches": ["master", "mobile_21.1"],
            "merge_requests": [
                MERGED_TO_MASTER_MERGE_REQUESTS_MOBILE["merged"]["iid"],
                MERGED_TO_21_1_MERGE_REQUESTS_MOBILE["merged"]["iid"]
            ],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": "MOBILE-666: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": MERGED_TO_MASTER_MERGE_REQUESTS_MOBILE["merged"]["iid"],
            "target_branch": "mobile_21.1",
        }, "Closed"),
        # Different Jira Project.
        ([{
            "key": "CB-666",
            "branches": ["master", "cloud_backend_20.1"],
            "merge_requests": [
                MERGED_TO_MASTER_MERGE_REQUESTS_CB["merged"]["iid"],
                MERGED_TO_20_1_MERGE_REQUESTS_CB["merged"]["iid"]
            ],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": "CB-666: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": MERGED_TO_MASTER_MERGE_REQUESTS_CB["merged"]["iid"],
            "target_branch": "cloud_backend_20.1",
        }, "Closed"),
        # Jira Project with the custom status config.
        ([{
            "key": "NXLIB-666",
            "branches": ["master"],
            "merge_requests": [
                MERGED_TO_MASTER_MERGE_REQUESTS_CB["merged"]["iid"],
            ],
            "state": "IN REVIEW",
        }], {
            "state": "merged",
            "title": "NXLIB-666: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": MERGED_TO_MASTER_MERGE_REQUESTS_CB["merged"]["iid"],
            "target_branch": "master",
        }, "DONE"),
        # Has merged merge requests for all issue branches, follow-up merge request just merged,
        # issue is in "good" state, follow-up state detection from description.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [
                MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"],
                MERGED_TO_4_1_MERGE_REQUESTS["merged"]["iid"]
            ],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "description": (
                "Blah blah blah\n"
                "(cherry picked from commit ca374322a8ce3f481d5d472ba27a394a69ffacea)"),
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_5.1",
        }, "Closed"),
        # The same as the previous, but performing a follow-up state detection from the commit
        # messages.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_5.1"],
            "merge_requests": [
                MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"],
                MERGED_TO_4_1_MERGE_REQUESTS["merged"]["iid"]
            ],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_5.1",
            "commits_list": [{
                "sha": "a26",
                "message": (
                    "Blah blah blah\n"
                    "(cherry picked from commit ca374322a8ce3f481d5d472ba27a394a69ffacea)"),
            }],
        }, "Closed"),
        # Closes more than one issue.
        ([
            {
                "key": DEFAULT_JIRA_ISSUE_KEY,
                "branches": ["master", "vms_5.1"],
                "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
                "state": "In Review",
            },
            {
                "key": "VMS-667",
                "branches": ["master", "vms_5.1"],
                "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
                "state": "In Review",
            },
        ], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, VMS-667: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_5.1",
        }, "Closed"),
        # No unmerged branches in the Jira Issue, the primary Merge Request was just merged, the
        # Issue is in a "good" state.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"], "state": "In Review"}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }, "Closed"),
        # Closes Issues in different Projects.
        ([
            {
                "key": DEFAULT_JIRA_ISSUE_KEY,
                "branches": ["master", "vms_5.1"],
                "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
                "state": "In Review",
            },
            {
                "key": NXLIB_JIRA_ISSUE_KEY,
                "branches": ["master", "vms_5.1"],
                "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
                "state": "IN REVIEW",
            },
        ], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, {NXLIB_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_5.1",
        }, "Closed"),
    ])
    def test_finalize_jira_issue(
            self, project, followup_rule, mr, mr_manager, jira_issues, jira, expected_status):
        # Init project state. TODO: Move project state to parameters.
        MergeRequestMock(project=project, **MERGED_TO_MASTER_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_4_1_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_4_2_MERGE_REQUESTS["merged"])
        MergeRequestMock(project=project, **MERGED_TO_MASTER_MERGE_REQUESTS_MOBILE["merged"])
        MergeRequestMock(project=project, **MERGED_TO_21_1_MERGE_REQUESTS_MOBILE["merged"])
        MergeRequestMock(project=project, **MERGED_TO_MASTER_MERGE_REQUESTS_CB["merged"])
        MergeRequestMock(project=project, **MERGED_TO_20_1_MERGE_REQUESTS_CB["merged"])

        mr_count_before = len(project.mergerequests.list())

        assert followup_rule.execute(mr_manager)
        assert len(mr.mock_comments()) == 0
        assert len(project.mergerequests.list()) == mr_count_before

        issue = jira._jira.issue(jira_issues[0]["key"])
        assert issue.fields.status.name == expected_status
        assert len(issue.fields.comment.comments) == 1
        if expected_status in ["Closed", "DONE"]:
            expected_transition = "closed"
        else:
            expected_transition = "moved to QA"
        assert issue.fields.comment.comments[0].body.startswith(f"Issue {expected_transition}")

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
    def test_create_draft_followup(
            self, bot: Bot, project, followup_rule, mr, mr_manager, repo_accessor):
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

        event_data = GitlabEventData(
            mr_id=mr.iid,
            event_type=GitlabEventType.comment,
            added_comment=f"@{BOT_USERNAME} draft-follow-up")
        bot.process_event(event_data)
        mr_manager._mr.load_discussions()

        # If the Merge Request is already merged, the follow-ups should be created during
        # "draft-follow-up" command execution; otherwise merge this MR and run followup_rule.
        if mr.state != "merged":
            mr.merge()
            assert followup_rule.execute(mr_manager)

        mrs = project.mergerequests.list()
        assert len(mrs) == 2, "Follow-up Merge Request not created."

        new_mr = sorted(mrs, key=lambda mr: mr.iid)[-1]
        assert new_mr.work_in_progress, "New MR is not in Draft state."
