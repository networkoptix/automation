from pathlib import Path
import pytest

import helpers.merge_request
import helpers.repo
import helpers.tests_config


class TestOpenSource:
    def test_ideal_mr(self, repo, project, bot):
        (Path(repo.working_dir) / "CMakeLists.txt").write_text("1")
        (Path(repo.working_dir) / "vms/file.cpp").write_text("2")
        helpers.repo.create_branch(repo, "test_branch")
        helpers.repo.create_and_push_commit(
            repo, branch_name="test_branch", updated_files=["CMakeLists.txt", "vms/file.cpp"],
            message="Test commit")
        mr = helpers.merge_request.create_merge_request(project, {
            "source_branch": "test_branch",
            "target_branch": "master",
            "title": "Test MR",
        })

        bot.run()

        helpers.merge_request.wait_last_mr_pipeline_status(mr, ["running"])

        helpers.merge_request.approve_mr_as_user(mr, helpers.tests_config.APPROVERS[0])
        helpers.merge_request.approve_mr_as_user(mr, helpers.tests_config.APPROVERS[1])

        helpers.merge_request.wait_last_mr_pipeline_status(mr, ["success"])

        bot.run()

        updated_mr = helpers.merge_request.update_mr_data(mr)
        assert updated_mr.state == "merged", f"The Merge Request state is {updated_mr.state}"
