import git
from pathlib import Path
import pytest
import time

import helpers.jira
import helpers.gitlab
import helpers.repo
import helpers.tests_config


class TestNoOpenSource:
    @pytest.mark.parametrize("issue_descriptions", [
        [
            helpers.jira.IssueDescription(
                title="Test issue 1", issuetype=helpers.jira.IssueType.Bug,
                versions=["master"],
                status=helpers.jira.IssueStatus.InReview),
        ]
    ])
    def test_submodule_update_unsquashed_mr(self, repo, branch, project, bot, jira_issues):
        (Path(repo.working_dir) / "CMakeLists.txt").write_text(branch)
        (Path(repo.working_dir) / "conan_recipes").write_text(branch)

        issue_keys = ", ".join([issue.key for issue in jira_issues])

        helpers.repo.create_commit(
            repo, branch_name=branch,
            updated_files=["CMakeLists.txt", "conan_recipes"],
            message=f"{issue_keys}: Test case 1 ({branch})")

        with pytest.raises(git.exc.GitError):
            helpers.repo.push(repo, branch_name=branch)

        helpers.repo.amend_last_commit(
            repo, branch_name=branch,
            message=f"{issue_keys}: Test case 1 ({branch})\n\nUpdate submodule conan_recipes.")
        helpers.repo.push(repo, branch_name=branch)

        mr = helpers.gitlab.create_merge_request(project, {
            "source_branch": branch,
            "target_branch": "master",
            "title": f"{issue_keys}: Test case 1 ({branch})",
            "description": "Update submodule conan_recipes.",
            "squash": False,
        })

        helpers.gitlab.emulate_mr_approval(bot=bot, mr=mr)

        updated_mr = helpers.gitlab.update_mr_data(mr)
        assert updated_mr.state == "merged", f"The Merge Request state is {updated_mr.state}"

    @pytest.mark.parametrize("issue_descriptions", [
        [
            helpers.jira.IssueDescription(
                title="Test issue 1", issuetype=helpers.jira.IssueType.Bug,
                versions=["master"],
                status=helpers.jira.IssueStatus.InReview),
        ]
    ])
    def test_squashed_mr(self, repo, branch, project, bot, jira_issues):
        (Path(repo.working_dir) / "vms/file_2_1.cpp").write_text(branch)
        (Path(repo.working_dir) / "conan_recipes").write_text(branch)
        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=["vms/file_2_1.cpp", "conan_recipes"],
            message=f"Test commit 1 ({branch})\n\nUpdate submodule conan_recipes.",
            wait_after_push=False)
        (Path(repo.working_dir) / "vms/file_2_2.cpp").write_text(branch)

        issue_keys = ", ".join([issue.key for issue in jira_issues])

        helpers.repo.create_and_push_commit(
            repo, branch_name=branch, updated_files=["vms/file_2_2.cpp"],
            message=f"{issue_keys}: Test case 2 ({branch})")
        mr = helpers.gitlab.create_merge_request(project, {
            "source_branch": branch,
            "target_branch": "master",
            "title": f"{issue_keys}: Test case 2 ({branch})",
            "description": "Update submodule conan_recipes.",
        })

        updated_mr = helpers.gitlab.update_mr_data(mr)
        assert len(list(updated_mr.commits())) == 2, ("Expecting two commits; got\n{}".format(
            "\n".join([str(c) for c in updated_mr.commits()])))

        helpers.gitlab.emulate_mr_approval(bot=bot, mr=mr)

        updated_mr = helpers.gitlab.update_mr_data(mr)
        mr_commits = list(updated_mr.commits())
        assert len(mr_commits) == 1, ("Expecting one commit; got\n{}".format(
            "\n".join([str(c) for c in updated_mr.commits()])))
        assert updated_mr.state == "merged", f"The Merge Request state is {updated_mr.state}"
        assert mr_commits[0].id == str(bot._repo.repo.head.commit), (
            "Repo last commit differs from MR commit")

    @pytest.mark.parametrize("issue_descriptions", [
        [
            helpers.jira.IssueDescription(
                title="Test issue 1", issuetype=helpers.jira.IssueType.Bug,
                versions=["master", "4.2_patch"],
                status=helpers.jira.IssueStatus.InReview),
            helpers.jira.IssueDescription(
                title="Test issue 2", issuetype=helpers.jira.IssueType.Internal,
                versions=["master", "4.2_patch"],
                status=helpers.jira.IssueStatus.InProgress),
        ]
    ])
    def test_normal_jira_workflow(
            issue_descriptions, jira_handler, jira_issues, repo, branch, project, bot):
        (Path(repo.working_dir) / "vms/file_3_1.cpp").write_text(branch)

        issue_keys = ", ".join([issue.key for issue in jira_issues])

        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=["vms/file_3_1.cpp"],
            message=f"{issue_keys}: Test case 3 ({branch})")
        mr = helpers.gitlab.create_merge_request(project, {
            "source_branch": branch,
            "target_branch": "master",
            "title": f"{issue_keys}: Test case 3 ({branch})",
        })

        helpers.gitlab.emulate_mr_approval(bot=bot, mr=mr)

        follow_up_mr = helpers.gitlab.get_last_opened_mr(project)
        assert follow_up_mr is not None, "Failed to create follow-up Merge Request"

        time.sleep(helpers.tests_config.POST_MR_SLEEP_S)

        helpers.gitlab.emulate_mr_approval(bot=bot, mr=follow_up_mr)

        for issue in jira_issues:
            updated_issue = helpers.jira.update_issue_data(jira_handler, issue)
            new_status_name = updated_issue.fields.status.name
            if updated_issue.fields.issuetype.name == helpers.jira.IssueType.Bug.value:
                expected_status_name = helpers.jira.IssueStatus.WaitingForQa.value
            elif updated_issue.fields.issuetype.name == helpers.jira.IssueType.Internal.value:
                expected_status_name = helpers.jira.IssueStatus.Closed.value
            else:
                assert False, f"Unexpected issue type: {updated_issue.fields.issuetype.name!r}"
            assert new_status_name == expected_status_name, (
                f"Wrong issue status: {new_status_name!r}, expected: {expected_status_name!r}")

    @pytest.mark.parametrize("issue_descriptions", [
        [
            helpers.jira.IssueDescription(
                title="Test issue 4", issuetype=helpers.jira.IssueType.Bug,
                versions=["master", "4.2_patch"],
                status=helpers.jira.IssueStatus.InReview),
        ]
    ])
    def test_failed_jira_workflow(
            issue_descriptions, jira_handler, jira_issues, repo, branch, project, bot):
        (Path(repo.working_dir) / "vms/file_4_1.cpp").write_text(branch)

        issue_keys = ", ".join([issue.key for issue in jira_issues])

        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=["vms/file_4_1.cpp"],
            message=f"{issue_keys}: Test commit 4.1 ({branch})",
            wait_after_push=False)
        (Path(repo.working_dir) / "vms/file_4_2.cpp").write_text(branch)
        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=["vms/file_4_2.cpp"],
            message=f"{issue_keys}: Test commit 4.2 ({branch})")
        mr = helpers.gitlab.create_merge_request(project, {
            "squash": False,
            "source_branch": branch,
            "target_branch": "master",
            "title": f"{issue_keys}: Test case 4",
        })

        helpers.repo.hard_checkout(repo, "vms_4.2_patch")
        # Add the same file with different content to vms_4.2_patch to create a cherry-pick
        # conflict.
        (Path(repo.working_dir) / "vms/file_4_1.cpp").write_text(branch[::-1])
        helpers.repo.create_and_push_commit(
            repo, branch_name="vms_4.2_patch",
            updated_files=["vms/file_4_1.cpp"],
            message="Test commit 4 (vms_4.2_patch)")

        helpers.gitlab.emulate_mr_approval(bot=bot, mr=mr)

        follow_up_mr = helpers.gitlab.get_last_opened_mr(project)
        assert follow_up_mr is not None, "Failed to create follow-up Merge Request"

        time.sleep(helpers.tests_config.POST_MR_SLEEP_S)

        bot.run()
        updated_follow_up_mr = helpers.gitlab.get_last_opened_mr(project)

        mr_notes = updated_follow_up_mr.notes.list()
        assert len(mr_notes) == 6, (
            f"Wrong notes number ({len(mr_notes)}). Notes: {[n.body for n in mr_notes]!r}")
        assert mr_notes[3].body.startswith("### :cherries: Manual conflict resolution required"), (
            f"Wrong conflicts note: {mr_notes[3].body!r}")

        for issue in jira_issues:
            updated_issue = helpers.jira.update_issue_data(jira_handler, issue)
            new_status_name = updated_issue.fields.status.name
            expected_status_name = helpers.jira.IssueStatus.InReview.value
            assert new_status_name == expected_status_name, (
                f"Wrong issue status: {new_status_name!r}, expected: {expected_status_name!r}")

    @pytest.mark.parametrize("issue_descriptions", [
        [
            helpers.jira.IssueDescription(
                title="Test issue 5", issuetype=helpers.jira.IssueType.Bug,
                versions=["master", "4.2_patch"],
                status=helpers.jira.IssueStatus.InReview),
        ]
    ])
    def test_empty_followup_workflow(
            issue_descriptions, jira_handler, jira_issues, repo, branch, project, bot):

        # Delete everything left from the previous test runs. It is too costly to re-create gitlab
        # project for every new test.
        while mr := helpers.gitlab.get_last_opened_mr(project):
            mr.delete()

        issue_keys = ", ".join([issue.key for issue in jira_issues])

        (Path(repo.working_dir) / "vms/file_5_1.cpp").write_text(branch)
        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=["vms/file_5_1.cpp"],
            message=f"{issue_keys}: Test commit 5.1 ({branch})",
            wait_after_push=False)
        (Path(repo.working_dir) / "vms/file_5_2.cpp").write_text(branch)
        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=["vms/file_5_2.cpp"],
            message=f"{issue_keys}: Test commit 5.2 ({branch})")
        mr = helpers.gitlab.create_merge_request(project, {
            "squash": False,
            "source_branch": branch,
            "target_branch": "master",
            "title": f"{issue_keys}: Test case 5",
        })

        helpers.repo.hard_checkout(repo, "vms_4.2_patch")
        # Add the same files with the content to vms_4.2_patch to create an empty cherry-pick
        # result.
        (Path(repo.working_dir) / "vms/file_5_1.cpp").write_text(branch)
        (Path(repo.working_dir) / "vms/file_5_2.cpp").write_text(branch)
        helpers.repo.create_and_push_commit(
            repo, branch_name="vms_4.2_patch",
            updated_files=["vms/file_5_1.cpp", "vms/file_5_2.cpp"],
            message="Test commit 5 (vms_4.2_patch)")

        helpers.gitlab.emulate_mr_approval(bot=bot, mr=mr)

        follow_up_mr = helpers.gitlab.get_last_opened_mr(project)
        assert follow_up_mr is None, "Follow-up MR was created"

        for issue in jira_issues:
            updated_issue = helpers.jira.update_issue_data(jira_handler, issue)
            new_status_name = updated_issue.fields.status.name
            expected_status_name = helpers.jira.IssueStatus.WaitingForQa.value
            assert new_status_name == expected_status_name, (
                f"Wrong Issue status: {new_status_name!r}, expected: {expected_status_name!r}")
