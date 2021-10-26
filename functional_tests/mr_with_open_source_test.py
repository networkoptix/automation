from pathlib import Path
import re
from typing import List

import pytest

import helpers.jira
import helpers.gitlab
import helpers.repo
import helpers.tests_config
import helpers.constants
from robocat.app import Bot


class TestOpenSource:
    @pytest.mark.parametrize("issue_descriptions", [
        [
            helpers.jira.IssueDescription(
                title="Test issue 1", issuetype=helpers.jira.IssueType.Bug,
                versions=["master"],
                status=helpers.jira.IssueStatus.InReview),
        ]
    ])
    def test_one_bad_file(self, repo, branch, project, bot_config, jira_issues):
        def check_open_source_check_result(approved_mr) -> List:
            approvals = approved_mr.approvals.get()
            assert approvals.approvals_left == 0, (
                "Wrong number of approvals: "
                f"{[a['user']['username'] for a in approvals.approved_by]}")

            notes = list(approved_mr.notes.list())
            assert len(notes) == 11, "Unexpected notes count: \n{}".format(
                "\n======\n".join([n.body for n in notes]))
            for autochek_comment_number in [-6, -7]:
                assert notes[autochek_comment_number].body.startswith(
                    "### :stop_sign: Autocheck for open source changes failed"), (
                    f"Unexpected auto-check failed note: {notes[autochek_comment_number].body}")
            assert not approved_mr.blocking_discussions_resolved
            assert approved_mr.work_in_progress

            # "notes" and "discussions" are ordered in reverse order to each other.
            open_source_discussions = []
            for autochek_comment_number in [-6, -7]:
                open_source_discussions.append(
                    approved_mr.discussions.list()[-1-autochek_comment_number])
                discussion_note = open_source_discussions[-1].attributes["notes"][0]
                assert discussion_note["id"] == notes[autochek_comment_number].id

            return open_source_discussions

        bot_1 = Bot(bot_config, project.id)

        updated_files = ["open/bad_file_1.cpp"]
        open_source_approvers = get_approvers_by_file_paths(
            bot_1._rule_open_source_check, updated_files)
        assert len(open_source_approvers) == 1, (
            f"Internal logic error: must have only one approver, got {open_source_approvers!r}")
        open_source_approver_username = open_source_approvers[0]

        file_data = helpers.constants.OPENSOURCE_FILES["test_one_bad_file"][0]
        (Path(repo.working_dir) / file_data["path"]).write_text(file_data["content"])

        issue_keys = ", ".join([issue.key for issue in jira_issues])

        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=updated_files,
            message=f"{issue_keys}: Test case 1 ({branch})\n")
        mr = helpers.gitlab.create_merge_request(project, {
            "source_branch": branch,
            "target_branch": "master",
            "title": f"{issue_keys}: Test case 1 ({branch})",
            "approvals_before_merge": 1,
        })

        helpers.gitlab.emulate_mr_approval(
            bot=bot_1, mr=mr, exclude_approvers=[open_source_approver_username])

        updated_mr = helpers.gitlab.update_mr_data(mr)
        assert updated_mr.state == "opened", f"The Merge Request state is {updated_mr.state}"

        approvals = updated_mr.approvals.get()
        assert approvals.approvals_left == 1, (
            f"Wrong number of approvals: {[a['user']['username'] for a in approvals.approved_by]}")

        helpers.gitlab.approve_mr_as_user(updated_mr, open_source_approver_username)

        bot_1.run()
        approved_mr_1 = helpers.gitlab.update_mr_data(mr)
        check_open_source_check_result(approved_mr_1)

        # Check that re-creating of the Bot object (simulation of Robocat restart) doesn't affect
        # the result of the check of the Merge Request.
        bot_2 = Bot(bot_config, project.id)
        bot_2.run()
        approved_mr_2 = helpers.gitlab.update_mr_data(mr)
        open_source_discussions = check_open_source_check_result(approved_mr_2)

        approved_mr_2.notes.create({'body': "/draft"})
        for open_source_discussion in open_source_discussions:
            helpers.gitlab.resolve_discussion(mr, open_source_discussion.id)

        bot_2.run()

        merged_mr = helpers.gitlab.update_mr_data(approved_mr_2)
        assert merged_mr.state == "merged", f"The Merge Request state is {merged_mr.state}"

    @pytest.mark.parametrize("issue_descriptions", [
        [
            helpers.jira.IssueDescription(
                title="Test issue 1", issuetype=helpers.jira.IssueType.Bug,
                versions=["master"],
                status=helpers.jira.IssueStatus.InReview),
        ]
    ])
    def test_two_bad_files(self, repo, branch, project, bot, jira_issues):
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

        issue_keys = ", ".join([issue.key for issue in jira_issues])

        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=updated_files,
            message=f"{issue_keys}: Test case 2 ({branch})")
        mr = helpers.gitlab.create_merge_request(project, {
            "source_branch": branch,
            "target_branch": "master",
            "title": f"{issue_keys}: Test case 2 ({branch})",
            "assignee_ids": [open_source_approver.id],
        })

        helpers.gitlab.wait_last_mr_pipeline_status(mr, ["manual"])
        bot.run()
        helpers.gitlab.wait_last_mr_pipeline_status(mr, ["success"])

        updated_mr = helpers.gitlab.update_mr_data(mr)
        assert updated_mr.state == "opened", f"The Merge Request state is {updated_mr.state}"

        approvals = updated_mr.approvals.get()
        assert approvals.approvals_left == approvals.approvals_required, (
            f"Wrong number of approvals: {[a['user']['username'] for a in approvals.approved_by]}")

        notes = list(updated_mr.notes.list())
        assert len(notes) == 6, "Unexpected notes count: \n{}".format(
            "\n======\n".join([n.body for n in notes]))
        for autochek_comment_number in [-4, -5, -6]:
            assert notes[autochek_comment_number].body.startswith(
                "### :stop_sign: Autocheck for open source changes failed"), (
                f"Unexpected auto-check failed note: {notes[autochek_comment_number].body}")
        assert not updated_mr.blocking_discussions_resolved
        # Robocat doesn't move unapproved MRs to "WIP" status.
        assert not updated_mr.work_in_progress

        # "notes" and "discussions" are ordered in reverse order to each other.
        open_source_discussions = updated_mr.discussions.list()[3:6]
        for i, open_source_discussion in enumerate(open_source_discussions):
            discussion_note = open_source_discussion.attributes["notes"][0]
            assert discussion_note["id"] == notes[-4-i].id
            helpers.gitlab.resolve_discussion(mr, open_source_discussion.id)

        helpers.gitlab.approve_mr(mr)

        bot.run()

        merged_mr = helpers.gitlab.update_mr_data(updated_mr)
        assert merged_mr.state == "merged", f"The Merge Request state is {merged_mr.state}"

    @pytest.mark.parametrize("issue_descriptions", [
        [
            helpers.jira.IssueDescription(
                title="Test issue 1", issuetype=helpers.jira.IssueType.Bug,
                versions=["master"],
                status=helpers.jira.IssueStatus.InReview),
        ]
    ])
    def test_existing_file_good_changes(self, repo, branch, project, bot, jira_issues):
        with open(Path(repo.working_dir) / "open/good_file.cpp", "a") as f:
            f.write("// Some good changes")

        issue_keys = ", ".join([issue.key for issue in jira_issues])

        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=["open/good_file.cpp"],
            message=f"{issue_keys}: Test case 3 ({branch})")
        mr = helpers.gitlab.create_merge_request(project, {
            "source_branch": branch,
            "target_branch": "master",
            "title": f"{issue_keys}: Test case 3 ({branch})",
        })

        helpers.gitlab.emulate_mr_approval(bot=bot, mr=mr)

        updated_mr = helpers.gitlab.update_mr_data(mr)
        assert updated_mr.state == "merged", f"The Merge Request state is {updated_mr.state}"

        notes = list(updated_mr.notes.list())
        assert len(notes) == 8, "Unexpected notes count: \n{}".format(
            "\n======\n".join([n.body for n in notes]))
        assert notes[-4].body.startswith(
            "### :white_check_mark: Auto-check for open-source changes passed"), (
            f"Unexpected auto-check pass note: {notes[-4].body}")

    @pytest.mark.parametrize("issue_descriptions", [
        [
            helpers.jira.IssueDescription(
                title="Test issue 1", issuetype=helpers.jira.IssueType.Bug,
                versions=["master"],
                status=helpers.jira.IssueStatus.InReview),
        ]
    ])
    def test_new_file_good_changes(self, repo, branch, project, bot, jira_issues):
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

        issue_keys = ", ".join([issue.key for issue in jira_issues])

        helpers.repo.create_and_push_commit(
            repo, branch_name=branch,
            updated_files=updated_files,
            message=f"{issue_keys}: Test case 4 ({branch})")
        mr = helpers.gitlab.create_merge_request(project, {
            "source_branch": branch,
            "target_branch": "master",
            "title": f"{issue_keys}: Test case 4 ({branch})",
            "assignee_ids": [open_source_approver.id]
        })

        helpers.gitlab.emulate_mr_approval(bot=bot, mr=mr)

        updated_mr = helpers.gitlab.update_mr_data(mr)
        assert updated_mr.state == "opened", f"The Merge Request state is {updated_mr.state}"

        approvals = updated_mr.approvals.get()
        assert approvals.approvals_left == 0, (
            f"Wrong number of approvals: {[a['user']['username'] for a in approvals.approved_by]}")

        notes = list(updated_mr.notes.list())
        assert len(notes) == 8, "Unexpected notes count: \n{}".format(
            "\n======\n".join([n.body for n in notes]))
        assert notes[-4].body.startswith(
            "### :white_check_mark: Auto-check for open-source changes passed"), (
            f"Unexpected auto-check pass note: {notes[-4].body}")
        assert not updated_mr.blocking_discussions_resolved
        assert updated_mr.work_in_progress

        # "notes" and "discussions" are ordered in reverse order to each other.
        open_source_discussion = updated_mr.discussions.list()[3]
        assert open_source_discussion.attributes["notes"][0]["id"] == notes[-4].id

        updated_mr.notes.create({'body': "/draft"})
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
