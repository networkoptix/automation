import git
from pathlib import Path
import pytest
import time

import helpers.jira
import helpers.gitlab
import helpers.repo
import helpers.tests_config

import automation_tools.bot_info


class TestNoOpenSource:
    def test_submodule_update_unsquashed_mr(self, repo, branch, project, bot):
        (Path(repo.working_dir) / "CMakeLists.txt").write_text(branch)
        (Path(repo.working_dir) / "conan_recipes").write_text(branch)
        helpers.repo.create_commit(
            repo, branch_name=branch,
            updated_files=["CMakeLists.txt", "conan_recipes"],
            message=f"Test commit 1 ({branch})")

        with pytest.raises(git.exc.GitError):
            helpers.repo.push(repo, branch_name=branch)

        helpers.repo.amend_last_commit(
            repo, branch_name=branch,
            message=f"Test commit 1 ({branch})\n\nUpdate submodule conan_recipes.")
        helpers.repo.push(repo, branch_name=branch)

        mr = helpers.gitlab.create_merge_request(project, {
            "source_branch": branch,
            "target_branch": "master",
            "title": "Test MR 1",
            "squash": False,
        })

        bot.run()
        helpers.gitlab.approve_mr_and_wait_pipeline(mr)
        bot.run()

        updated_mr = helpers.gitlab.update_mr_data(mr)
        assert updated_mr.state == "merged", f"The Merge Request state is {updated_mr.state}"

    def test_squashed_mr(self, repo, branch, project, bot):
        (Path(repo.working_dir) / "vms/file_2_1.cpp").write_text(branch)
        (Path(repo.working_dir) / "conan_recipes").write_text(branch)
        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=["vms/file_2_1.cpp", "conan_recipes"],
            message=f"Test commit 1 ({branch})\n\nUpdate submodule conan_recipes.")

        (Path(repo.working_dir) / "vms/file_2_2.cpp").write_text(branch)
        helpers.repo.create_and_push_commit(
            repo, branch_name=branch, updated_files=["vms/file_2_2.cpp"],
            message=f"Test commit 2 ({branch})")

        mr = helpers.gitlab.create_merge_request(project, {
            "source_branch": branch,
            "target_branch": "master",
            "title": "Test MR 2",
            "description": "Update submodule conan_recipes.",
        })

        updated_mr = helpers.gitlab.update_mr_data(mr)
        assert len(list(updated_mr.commits())) == 2, ("Expecting two commits; got\n{}".format(
            "\n".join([str(c) for c in updated_mr.commits()])))

        bot.run()
        helpers.gitlab.approve_mr_and_wait_pipeline(mr)
        bot.run()

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
    def test_jira_workflow(
            issue_descriptions, jira_handler, jira_issues, repo, branch, project, bot):
        (Path(repo.working_dir) / "vms/file_3_1.cpp").write_text(branch)
        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=["vms/file_3_1.cpp"],
            message=f"Test commit 1 ({branch})")

        issue_keys = ", ".join([issue.key for issue in jira_issues])
        mr = helpers.gitlab.create_merge_request(project, {
            "source_branch": branch,
            "target_branch": "master",
            "title": f"{issue_keys}: Test MR 3",
        })

        bot.run()
        helpers.gitlab.approve_mr_and_wait_pipeline(mr)
        bot.run()
        follow_up_mr = helpers.gitlab.get_last_opened_mr(project)
        assert follow_up_mr is not None, "Failed to create follow-up Merge Request"

        time.sleep(5)  # Give gitlab some time to do all the post-MR-creation magic.

        bot.run()
        helpers.gitlab.wait_last_mr_pipeline_status(follow_up_mr, ["success"])
        bot.run()

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
