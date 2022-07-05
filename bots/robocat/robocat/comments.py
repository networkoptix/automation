from robocat.note import MessageId

_mark_as_ready_url = (
    "https://docs.gitlab.com/ee/user/project/merge_requests/work_in_progress_merge_requests.html"
    "#removing-the-draft-flag-from-a-merge-request")

initial_message = """Hi, I am Robocat and I will help you merging this MR.
Once the Merge Request is ready I will run the pipeline and automatically merge it.

Please note, I consider Merge Request ready when:
1. It's approved by reviewers *({approvals_left} more required at the moment)*
2. It's not in Draft status
3. It's assigned to me

P.S. You may set :construction_site: emoji on Merge Request and I will run the pipeline even if MR
isn't ready."""

merged_message = "Merge request was successfully merged into `{branch}` branch."
run_pipeline_message = "Running pipeline {pipeline_id}: {reason}."
refuse_run_pipeline_message = """
Refusing to run user-requested pipeline becasue the previous pipeline
([{pipeline_id}]({pipeline_url})) ran for the same commit (sha: {sha}).
"""

commits_wait_message = """There are no commits in MR. I won't do anything until commits arrive."""
pipeline_wait_message = """There is already [pipeline {pipeline_id}]({pipeline_url}) in progress.
Lets wait until it finishes."""
approval_wait_message = """Not enough approvals, **{approvals_left} more** required.
I will start merging process once all approvals are collected."""

unresolved_threads_message = f"""Merge Request returned to development.
Please, resolve all discussions and [mark as Ready]({_mark_as_ready_url}) to continue merging
process."""

no_supported_jira_projects = f"""
Merge Request returned to development. Please, link this Merge Request to the Jira Issues from at
least one of the supported Jira Projects (%s) and [mark as Ready]({_mark_as_ready_url}) to
continue the merge process.
"""

conflicts_message = f"""Merge Request returned to development.
Please, do manual rebase and [mark as Ready]({_mark_as_ready_url}) to continue merging process."""

has_new_files_in_open_source = """This merge request contains new or renamed files in the
open-source part of the project, so it **must be approved** by one of: @{approvers}.
"""

bad_commit_message = """{error_message}

Auto-check of this Merge Request has failed. Fix all the issues, or ask one of @{approvers} to
approve this Merge Request. Otherwise, this Merge Request **will not be merged**.
"""

bad_commit_message_from_authorized_approver = """{error_message}

Auto-check of this Merge Request has failed. Please, check carefully all the issues and fix them if
needed.
"""

commit_message_is_ok = "Commit message is ok."

failed_pipeline_message = f"""Merge Request returned to development.
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

workflow_error_message = """Workflow violation detected:

{error}
"""

workflow_no_errors_message = "No workflow errors found."

cannot_squash_locally = "Failed to squash commits locally by git. See bot logs for details."

cannot_restore_approvals = """Failed to restore approvals of some of the following users:
{approvers}. Please, re-approve manually."""

authorized_approvers_assigned = """@{approvers} were assigned to this merge request because it
contains new or renamed files in the open-source part of the project."""

has_invalid_changes = """{error_message}

Auto-check of this merge request has failed. Fix all the issues, otherwise this merge request
**will not be merged**.
"""

nx_submodule_autocheck_passed = """Auto-check for Nx Submodule(s) changed by this
Merge Request passed successfully. The Merge Request can be merged once all other criteria are met.
"""

nx_submodule_autocheck_impossible = """Unable to check Nx Submodule(s) changed
by this Merge Request due to the huge amount of changes (gitlab limitation). Please, double-check
it manually.
"""

inconsistent_nx_submodule_change = """The content of the directory `{nx_submodule_dir}` differs
from the content of the directory `{subrepo_dir}` in repository `{subrepo_url}` checked out at
commit `{subrepo_commit_sha}`: *{explanation}*. Fix this using `nx_submodule.py` utility or
manually.
"""

nx_submodule_config_deleted = """Nx Submodule config file was deleted from the directory
`{nx_submodule_dir}`. This file must be restored to merge this Merge Request.
"""

nx_submodule_config_malformed = """Nx Submodule config file in the directory `{nx_submodule_dir}`
has wrong format. Fix this using `nx_submodule.py` utility or manually.
"""

unknown_nx_submodule_error = """An unknown error was found while auto-checking Nx Submodule(s)
changed by this Merge Request. **This must be an internal error of the Robocat - report
it to the support**.
"""

nx_submodule_bad_git_data = """Git error occurred while fetching subrepo `{subrepo_url}` at commit
`{subrepo_commit_sha}` for Nx submodule `{nx_submodule_dir}` (probably, because of an incorrect
value in `subrepo-url` or `commit-sha`): *{explanation}*.
"""

issue_is_not_finalized = """The Issue {issue_key} was not moved to the QA state because of its
current status. Check the Issue status and fix in manually if necessary."""

bot_readable_comment_title = {
    MessageId.CommandProcess: "User command action",
    MessageId.CommandRunPipeline: "User command action",
    MessageId.OpenSourceNeedApproval: "Manual check is needed",
}
bot_readable_comment = {
    MessageId.CommandProcess: "Re-checking Merge Request",
    MessageId.CommandRunPipeline: "Initiating pipeline run",
    MessageId.OpenSourceNeedApproval: """
This merge request contains new or renamed files in the open-source part of the project, so it
**must be approved** by one of: @{approvers}.
""",
}
