_mark_as_ready_url = (
    "https://docs.gitlab.com/ee/user/project/merge_requests/work_in_progress_merge_requests.html"
    "#removing-the-draft-flag-from-a-merge-request")

initial_message = """Hi, I am Robocat and I will help you merging this MR.
Once the Merge Request is ready I will run the pipeline and automatically merge it.

Please note, I consider Merge Request ready when:
1. It's approved by reviewers *({approvals_left} more required at the moment)*
2. It's not in Draft status
3. It's assigned to me

P.S. You may set :construction_site: emoji on Merge Request and I will run the pipeline even if MR isn't ready."""

merged_message = "Merge request was successfully merged into `{branch}` branch."
run_pipeline_message = "Running pipeline {pipeline_id}: {reason}."

commits_wait_message = """There are no commits in MR. I won't do anything until commits arrive."""
pipeline_wait_message = """There is already [pipeline {pipeline_id}]({pipeline_url}) in progress.
Lets wait until it finishes."""
approval_wait_message = """Not enough approvals, **{approvals_left} more** required.
I will start merging process once all approvals are collected."""

unresolved_threads_message = f"""Merge request returned to development.
Please, resolve all discussions and [mark as Ready]({_mark_as_ready_url}) to continue merging process."""

conflicts_message = f"""Merge request returned to development.
Please, do manual rebase and [mark as Ready]({_mark_as_ready_url}) to continue merging process."""

has_good_changes_in_open_source = """No problems were revealed by the auto-check. This merge
request contains new or renamed files in the open source part of the project, so it **must be
approved** by one of: @{approvers}.
"""

has_unimportant_changes_in_open_source = """This merge request contains changes in the open source
part of the project. No problems were revealed by the auto-check.
"""

may_have_changes_in_open_source = """Unable to check whether this merge request contains
changes in the open source part of the project due to the huge amount of changes (gitlab
limitation), so it **must be approved** by one of: @{approvers}.
"""

check_changes_manually = """Unable to check whether this merge request contains changes in the open
source part of the project due to the huge amount of changes (gitlab limitation). Please, check it
manually for dangerous changes.
"""

has_bad_changes_in_open_source_optional_approval = """{error_message}

Auto-check of this merge request has failed. Fix all the issues, or ask one of @{approvers} to
approve this merge request. Otherwise, this merge request **will not be merged**.
"""

has_bad_changes_from_authorized_approver = """{error_message}

Auto-check of this merge request has failed. Please, check carefully all the issues and fix them if
needed.
"""

has_bad_changes_in_open_source = """{error_message}

Auto-check of this merge request has failed. Also, it contains new or renamed files in the
open-source part of the project, so it must be approved by one of: @{approvers}.
"""

bad_open_source_line = """Check failed at {position}: line is

`{actual}`

expected:

`{expected}`
"""

bad_open_source_license_word = "License word at {position}: **{word}**"

bad_open_source_trademark_word = "Trademark at {position}: **{word}**"

bad_open_source_offensive_word = "Bad word at {position}: **{word}**"

bad_open_source_file_type = "Unknown file type: **{file}**"

failed_pipeline_message = f"""Merge request returned to development.
Please, fix the errors and [mark as Ready]({_mark_as_ready_url}) to continue merging process.\n
You may rebase or run new pipeline manually if errors are resolved outside MR."""

template = """### :{emoji}: {title}

{message}

---

###### Robocat rev. {revision}. See its [documentation](https://networkoptix.atlassian.net/wiki/spaces/SD/pages/1486749741/Automation+Workflow+Police+bot)
"""  # noqa

followup_merge_request_message = """Follow-up merge request {url} is created for merging changes
added in this merge request into `{branch}` branch.
"""

failed_followup_merge_request_message = """Failed to create follow-up merge request for merging
changes added in this merge request into `{branch}` branch: {comment}.
"""

followup_initial_message = """This merge request is created as a follow-up for merging changes
added in merge request {original_mr_url} into `{branch}` branch.
"""
conflicting_commit_followup_message = """Cherry-picking creates conflicts. Please, fetch `{branch}`
branch and cherry-pick the following commits manually:

`git cherry-pick -x {commits}`
"""

bad_fix_versions_message = """Workflow violation detected for Jira Issue(s) closed by this Merge
Request:

> {errors}
"""

cannot_squash_locally = "Failed to squash commits locally by git. See bot logs for details."

cannot_restore_approvals = """Failed to restore approvals of some of the following users:
{approvers}. Please, re-approve manually."""

authorized_approvers_assigned = """@{approvers} were assinged to this merge request because it
contains new or renamed files in the open-source part of the project."""
