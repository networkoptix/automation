import re
import pytest

from automation_tools.tests.fixtures import jira, repo_accessor
from automation_tools.tests.mocks.git_mocks import RemoteMock
from robocat.award_emoji_manager import AwardEmojiManager
from robocat.rule.followup_rule import FollowupRuleExecutionResult
from tests.robocat_constants import (
    DEFAULT_COMMIT,
    DEFAULT_PROJECT_ID,
    FORK_PROJECT_ID,
    DEFAULT_JIRA_ISSUE_KEY,
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
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.1"]}], {
            "state": "opened",
        }),
        # Don't create follow-up merge request for follow-up merge requests.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.1"]}], {
            "state": "merged",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI]
        }),
    ])
    def test_dont_create_followup(
            self, project, followup_rule, mr, mr_manager, jira, repo_accessor):
        # Init git repo state. TODO: Move git repo state to parameters.

        project_remote = project.namespace["full_path"]
        RemoteMock.add(repo=repo_accessor.repo, name=project_remote, url="")
        repo_accessor.create_branch(
            target_remote=project_remote, new_branch="vms_4.1", source_branch="master")
        for c in mr.commits_list:
            repo_accessor.repo.add_mock_commit(c["sha"], c["message"])
        repo_accessor.repo.remotes[project_remote].mock_attach_gitlab_project(project)

        # Start tests.

        for _ in range(2):
            assert followup_rule.execute(mr_manager) in (
                FollowupRuleExecutionResult.rule_execution_successfull,
                FollowupRuleExecutionResult.not_eligible)

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
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.1"]}], {
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
            "branches": ["master", "vms_4.1"],
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
            project=project, source_branch="feature_vms_4.1",
            **MERGED_TO_4_1_MERGE_REQUESTS["opened"])
        project.branches.create({"branch": "existing_branch_vms_4.1", "ref": "vms_4.1"})

        assert not followup_rule.execute(mr_manager)

        issue = jira._jira.issue(DEFAULT_JIRA_ISSUE_KEY)
        assert len(issue.fields.comment.comments) == 1, (
            f"Got Jira issue comments: {issue.fields.comment.comments}")
        assert issue.fields.comment.comments[0].body.startswith(
            "An error occured while trying to execute follow-up actions for merge request ")

        assert len(mr.mock_comments()) == 0
        emojis = mr.awardemojis.list()

        assert not any(
            e for e in emojis if e.name == AwardEmojiManager.FOLLOWUP_CREATED_EMOJI), (
            'Hasn\'t "follow-up created" emoji.')

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Squashed merge request (issue detection from the title).
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
        # Three target branches.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.1", "vms_4.2"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
        # More than one commit.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "description": f"blah blah blah Closes {DEFAULT_JIRA_ISSUE_KEY}",
            "commits_list": [
                {"sha": "a24", "message": "message 1"},
                {"sha": "a25", "message": "message 2"},
            ]
        }),
        # Conflicting merge request.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": CONFLICTING_COMMIT_SHA,
            "target_branch": "master",  # "vms_4.1" is a branch to create follow-up merge request.
            "source_branch": "feature",
            "commits_list": [{"sha": CONFLICTING_COMMIT_SHA, "message": "message 1"}],
        }),
        # More than one commit, one is conflicting.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.1"]}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "description": f"blah blah blah Closes {DEFAULT_JIRA_ISSUE_KEY}",
            "target_branch": "master",  # "vms_4.1" is a branch to create follow-up merge request.
            "source_branch": "feature",
            "commits_list": [
                {"sha": "a24", "message": "message 1"},
                {"sha": CONFLICTING_COMMIT_SHA, "message": "message 2"}
            ],
        }),
        # Has opened merge requests to follow-up branches.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_4.1"],
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
            "branches": ["master", "vms_4.1"],
            "merge_requests": [MERGED_TO_4_1_MERGE_REQUESTS["merged"]["iid"]]
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        }),
        # Merge request from the different project.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master", "vms_4.1"]}], {
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
        project.branches.create({"branch": "existing_branch_vms_4.1"})

        # Set the source project for the MR. If it is not default project, create it.

        if mr.source_project_id != DEFAULT_PROJECT_ID:
            source_project = ProjectMock(id=mr.source_project_id, manager=project.manager)
            for c in mr.commits_list:
                source_project.add_mock_commit("master", c["sha"], c["message"])
        else:
            source_project = project

        # Init git repo state. TODO: Move git repo state to parameters.

        project_remote = project.namespace["full_path"]
        RemoteMock.add(repo=repo_accessor.repo, name=project_remote, url="")
        repo_accessor.create_branch(
            target_remote=project_remote, new_branch="vms_4.1", source_branch="master")
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
        assert f"{mr.source_branch}_vms_4.1" in source_project_branches, (
            f"New branch {mr.source_branch}_vms_4.1 is not created: {source_project_branches}")

        if project != source_project:
            project_branches = [b.name for b in project.branches.branches]
            assert f"{mr.source_branch}_vms_4.1" not in project_branches, (
                f"Branch {mr.source_branch}_vms_4.1 created in the wrong project")

        mrs = project.mergerequests.list()
        assert len(mrs) == before_mergrequests_count + len(issue.fields.fixVersions) - 1

        new_mr = sorted(mrs, key=lambda mr: mr.iid)[-1]
        assert re.match(rf"({DEFAULT_JIRA_ISSUE_KEY}: )?\(master->vms_4\.(1|2)\) ", new_mr.title)

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
            assert len(new_comments) == 1

        assert new_comments[0].startswith(
            f"### :{AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI}: Follow-up merge request")

    @pytest.mark.parametrize(("jira_issues", "mr_state"), [
        # Squashed merge request (issue detection from the title).
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_4.1"],
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
        RemoteMock.add(repo=repo_accessor.repo, name=project_remote, url="")
        repo_accessor.create_branch(
            target_remote=project_remote, new_branch="vms_4.1", source_branch="master")
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
            "branches": ["master", "vms_4.1"],
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
            "branches": ["master", "vms_4.1", "vms_4.2"],
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
        # issue is in uncloseable state.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_4.1"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "Open",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
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
        # Has merged merge requests for all issue branches, follow-up merge request just merged,
        # issue is in "good" state.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_4.1"],
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
            "target_branch": "vms_4.1",
        }),
        # The same that preivous, but Jira issue has three branches.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_4.1", "vms_4.2"],
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
            "target_branch": "vms_4.1",
        }),
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
        }),
        # Another Jira project.
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
        }),

        # Has merged merge requests for all issue branches, follow-up merge request just merged,
        # issue is in "good" state, follow-up state detection from description.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_4.1"],
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
            "target_branch": "vms_4.1",
        }),
        # The same that preivous, but follow-up state detection from commit messages.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_4.1"],
            "merge_requests": [
                MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"],
                MERGED_TO_4_1_MERGE_REQUESTS["merged"]["iid"]
            ],
            "state": "In Review",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_4.1",
            "commits_list": [{
                "sha": "a26",
                "message": (
                    "Blah blah blah\n"
                    "(cherry picked from commit ca374322a8ce3f481d5d472ba27a394a69ffacea)"),
            }],
        }),
        # Closes more than one issue.
        ([
            {
                "key": DEFAULT_JIRA_ISSUE_KEY,
                "branches": ["master", "vms_4.1"],
                "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
                "state": "In Review",
            },
            {
                "key": "VMS-667",
                "branches": ["master", "vms_4.1"],
                "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
                "state": "In Review",
            },
        ], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}, VMS-667: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_4.1",
        }),
        # Has merged merge requests for all issue branches, follow-up merge request just merged,
        # issue is in "In progress" state which is not right but bot can fix it.
        ([{
            "key": DEFAULT_JIRA_ISSUE_KEY,
            "branches": ["master", "vms_4.1"],
            "merge_requests": [MERGED_TO_MASTER_MERGE_REQUESTS["merged"]["iid"]],
            "state": "In progress",
        }], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "emojis_list": [AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI],
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "vms_4.1",
        }),
        # No unmerged branches in jira issue, primary merge request just merged, issue is in "good"
        # state.
        ([{"key": DEFAULT_JIRA_ISSUE_KEY, "branches": ["master"], "state": "In Review"}], {
            "state": "merged",
            "title": f"{DEFAULT_JIRA_ISSUE_KEY}: Test mr",
            "squash_commit_sha": DEFAULT_COMMIT["sha"],
            "target_branch": "master",
        })
    ])
    def test_close_jira_issue(self, project, followup_rule, mr, mr_manager, jira_issues, jira):
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
        assert issue.fields.status.name == "Closed"
        assert len(issue.fields.comment.comments) == 1
        assert issue.fields.comment.comments[0].body.startswith("Issue closed")
