import git
from pathlib import Path
import pytest
import re
from typing import List

import helpers.jira
import helpers.gitlab
import helpers.repo
import helpers.tests_config
import helpers.constants

import automation_tools.bot_info


class TestOpenSource:
    def test_one_bad_file(self, repo, branch, project, bot):
        updated_files = ["open/bad_file_1.cpp"]
        open_source_approvers = get_approvers_by_file_paths(
            bot._rule_open_source_check, updated_files)
        assert len(open_source_approvers) == 1, (
            f"Internal logic error: must have only one approver, got {open_source_approvers!r}")
        open_source_approver_username = open_source_approvers[0]

        file_data = helpers.constants.OPENSOURCE_FILES["test_one_bad_file"][0]
        (Path(repo.working_dir) / file_data["path"]).write_text(file_data["content"])

        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=updated_files,
            message=f"Test commit 1 ({branch})")

        mr = helpers.gitlab.create_merge_request(project, {
            "source_branch": branch,
            "target_branch": "master",
            "title": "Test MR 1",
            "approvals_before_merge": 1,
        })

        bot.run()
        helpers.gitlab.approve_mr_and_wait_pipeline(
            mr, exclude_approvers=[open_source_approver_username])
        bot.run()

        updated_mr = helpers.gitlab.update_mr_data(mr)
        assert updated_mr.state == "opened", f"The Merge Request state is {updated_mr.state}"

        approvals = updated_mr.approvals.get()
        assert approvals.approvals_left == 1, (
            f"Wrong number of approvals: {[a['user']['username'] for a in approvals.approved_by]}")

        helpers.gitlab.approve_mr_as_user(updated_mr, open_source_approver_username)
        bot.run()

        approved_mr = helpers.gitlab.update_mr_data(mr)
        approvals = approved_mr.approvals.get()
        assert approvals.approvals_left == 0, (
            f"Wrong number of approvals: {[a['user']['username'] for a in approvals.approved_by]}")

        notes = list(approved_mr.notes.list())
        assert len(notes) == 9, "Unexpected notes count: \n{}".format(
            "\n======\n".join([n.body for n in notes]))
        assert notes[-4].body.startswith(
            "### :stop_sign: Autocheck for open source changes failed"), (
            f"Unexpected auto-check failed note: {notes[-4].body}")
        assert notes[-5].body.startswith(
            "### :stop_sign: Autocheck for open source changes failed"), (
            f"Unexpected auto-check failed note: {notes[-5].body}")
        assert not approved_mr.blocking_discussions_resolved
        assert approved_mr.work_in_progress

        # "notes" and "discussions" are ordered in reverse order to each other.
        open_source_discussion_1 = approved_mr.discussions.list()[3]
        assert open_source_discussion_1.attributes["notes"][0]["id"] == notes[-4].id
        open_source_discussion_2 = approved_mr.discussions.list()[4]
        assert open_source_discussion_2.attributes["notes"][0]["id"] == notes[-5].id

        approved_mr.notes.create({'body': "/wip"})
        helpers.gitlab.resolve_discussion(mr, open_source_discussion_1.id)
        helpers.gitlab.resolve_discussion(mr, open_source_discussion_2.id)

        bot.run()

        merged_mr = helpers.gitlab.update_mr_data(approved_mr)
        assert merged_mr.state == "merged", f"The Merge Request state is {merged_mr.state}"

    def test_two_bad_files(self, repo, branch, project, bot):
        updated_files = ["open/bad_file_2.cpp", "open/bad_file.cpp"]
        open_source_approvers = get_approvers_by_file_paths(
            bot._rule_open_source_check, updated_files)
        assert len(open_source_approvers) == 1, (
            f"Internal logic error: must have only one approver, got {open_source_approvers!r}")
        open_source_approver = project.manager.gitlab.users.list(
            search=open_source_approvers[0])[0]

        file_data = helpers.constants.OPENSOURCE_FILES["test_two_bad_files"][0]
        (Path(repo.working_dir) / file_data["path"]).write_text(file_data["content"])

        with open(Path(repo.working_dir) / "open/bad_file.cpp", "a") as f:
            f.write("// Some good changes")

        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=updated_files,
            message=f"Test commit 1 ({branch})")

        mr = helpers.gitlab.create_merge_request(project, {
            "source_branch": branch,
            "target_branch": "master",
            "title": "Test MR 2",
            "assignee_ids": [open_source_approver.id],
        })

        bot.run()
        helpers.gitlab.wait_last_mr_pipeline_status(mr, ["success"])

        updated_mr = helpers.gitlab.update_mr_data(mr)
        assert updated_mr.state == "opened", f"The Merge Request state is {updated_mr.state}"

        approvals = updated_mr.approvals.get()
        assert approvals.approvals_left == approvals.approvals_required, (
            f"Wrong number of approvals: {[a['user']['username'] for a in approvals.approved_by]}")

        notes = list(updated_mr.notes.list())
        assert len(notes) == 5, "Unexpected notes count: \n{}".format(
            "\n======\n".join([n.body for n in notes]))
        assert notes[-3].body.startswith(
            "### :stop_sign: Autocheck for open source changes failed"), (
            f"Unexpected auto-check failed note: {notes[-3].body}")
        assert notes[-4].body.startswith(
            "### :stop_sign: Autocheck for open source changes failed"), (
            f"Unexpected auto-check failed note: {notes[-4].body}")
        assert notes[-4].body.startswith(
            "### :stop_sign: Autocheck for open source changes failed"), (
            f"Unexpected auto-check failed note: {notes[-5].body}")
        assert not updated_mr.blocking_discussions_resolved
        # Robocat doesn't move unapproved MRs to "WIP" status.
        assert not updated_mr.work_in_progress

        # "notes" and "discussions" are ordered in reverse order to each other.
        open_source_discussion_1 = updated_mr.discussions.list()[2]
        assert open_source_discussion_1.attributes["notes"][0]["id"] == notes[-3].id
        open_source_discussion_2 = updated_mr.discussions.list()[3]
        assert open_source_discussion_2.attributes["notes"][0]["id"] == notes[-4].id
        open_source_discussion_3 = updated_mr.discussions.list()[4]
        assert open_source_discussion_3.attributes["notes"][0]["id"] == notes[-5].id

        helpers.gitlab.resolve_discussion(mr, open_source_discussion_1.id)
        helpers.gitlab.resolve_discussion(mr, open_source_discussion_2.id)
        helpers.gitlab.resolve_discussion(mr, open_source_discussion_3.id)
        helpers.gitlab.approve_mr(mr)

        bot.run()

        merged_mr = helpers.gitlab.update_mr_data(updated_mr)
        assert merged_mr.state == "merged", f"The Merge Request state is {merged_mr.state}"

    def test_existing_file_good_changes(self, repo, branch, project, bot):
        with open(Path(repo.working_dir) / "open/good_file.cpp", "a") as f:
            f.write("// Some good changes")

        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=["open/good_file.cpp"],
            message=f"Test commit 1 ({branch})")

        mr = helpers.gitlab.create_merge_request(project, {
            "source_branch": branch,
            "target_branch": "master",
            "title": "Test MR 3",
        })

        bot.run()
        helpers.gitlab.approve_mr_and_wait_pipeline(mr)
        bot.run()

        updated_mr = helpers.gitlab.update_mr_data(mr)
        assert updated_mr.state == "merged", f"The Merge Request state is {updated_mr.state}"

        notes = list(updated_mr.notes.list())
        assert len(notes) == 7, "Unexpected notes count: \n{}".format(
            "\n======\n".join([n.body for n in notes]))
        assert notes[-3].body.startswith(
            "### :white_check_mark: Auto-check for open source changes passed"), (
            f"Unexpected auto-check pass note: {notes[-3].body}")

    def test_new_file_good_changes(self, repo, branch, project, bot):
        updated_files = ["open/good_file_1.cpp"]
        open_source_approvers = get_approvers_by_file_paths(
            bot._rule_open_source_check, updated_files)
        assert len(open_source_approvers) == 1, (
            f"Internal logic error: must have only one approver, got {open_source_approvers!r}")
        open_source_approver = project.manager.gitlab.users.list(
            search=open_source_approvers[0])[0]

        with open(Path(repo.working_dir) / "open/good_file.cpp", "a") as f:
            f.write("// Some good changes")

        file_data = helpers.constants.OPENSOURCE_FILES["test_new_file_good_changes"][0]
        (Path(repo.working_dir) / file_data["path"]).write_text(file_data["content"])

        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=updated_files,
            message=f"Test commit 1 ({branch})")

        mr = helpers.gitlab.create_merge_request(project, {
            "source_branch": branch,
            "target_branch": "master",
            "title": "Test MR 4",
            "assignee_ids": [open_source_approver.id]
        })

        bot.run()
        helpers.gitlab.approve_mr_and_wait_pipeline(mr)
        bot.run()

        updated_mr = helpers.gitlab.update_mr_data(mr)
        assert updated_mr.state == "opened", f"The Merge Request state is {updated_mr.state}"

        approvals = updated_mr.approvals.get()
        assert approvals.approvals_left == 0, (
            f"Wrong number of approvals: {[a['user']['username'] for a in approvals.approved_by]}")

        notes = list(updated_mr.notes.list())
        assert len(notes) == 7, "Unexpected notes count: \n{}".format(
            "\n======\n".join([n.body for n in notes]))
        assert notes[-3].body.startswith(
            "### :white_check_mark: Auto-check for open source changes passed"), (
            f"Unexpected auto-check pass note: {notes[-3].body}")
        assert not updated_mr.blocking_discussions_resolved
        assert updated_mr.work_in_progress

        # "notes" and "discussions" are ordered in reverse order to each other.
        open_source_discussion = updated_mr.discussions.list()[2]
        assert open_source_discussion.attributes["notes"][0]["id"] == notes[-3].id

        updated_mr.notes.create({'body': "/wip"})
        helpers.gitlab.resolve_discussion(mr, open_source_discussion.id)

        bot.run()

        merged_mr = helpers.gitlab.update_mr_data(updated_mr)
        assert merged_mr.state == "merged", f"The Merge Request state is {merged_mr.state}"


def get_approvers_by_file_paths(check_rule_object, file_paths: List[str]) -> List[str]:
    for rule in check_rule_object._approve_rules:
        for file_path in file_paths:
            if any([re.match(p, file_path) for p in rule.patterns]):
                return rule.approvers
    return []
