from robocat.note import MessageId

_mark_as_ready_url = (
    "https://docs.gitlab.com/ee/user/project/merge_requests/work_in_progress_merge_requests.html"
    "#removing-the-draft-flag-from-a-merge-request")

merged_message = "Merge request was successfully merged into `{branch}` branch."
run_pipeline_message = "Running pipeline [#{pipeline_id}]({pipeline_url}): {reason}."
refuse_run_pipeline_message = """
Refusing to run user-requested pipeline becasue the previous pipeline
([{pipeline_id}]({pipeline_url})) ran for the same commit (sha: {sha}).
"""

commits_wait_message = """There are no commits in MR. I won't do anything until commits arrive."""
pipeline_wait_message = """There is already [pipeline {pipeline_id}]({pipeline_url}) in progress.
Lets wait until it finishes."""
approval_wait_message = """Not enough approvals, **{approvals_left} more** required.
I will start merging process once all approvals are collected."""

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

template = """### :{emoji}: {title}

{message}

---

###### Robocat rev. {revision}. See its [documentation](https://networkoptix.atlassian.net/wiki/spaces/SD/pages/1486749741/Automation+Workflow+Police+bot)
"""  # noqa

follow_up_merge_request_message = """Follow-up merge request {url} is created for merging changes
added in this merge request into `{branch}` branch.
"""

failed_follow_up_merge_request_message = """Failed to create follow-up merge request for merging
changes added in this merge request into `{branch}` branch: {comment}.
"""

follow_up_initial_message = """This merge request is created as a follow-up for merging changes
added in merge request {original_mr_url} into `{branch}` branch.
"""
conflicting_commit_follow_up_message = """Cherry-picking creates conflicts. Please, fetch
`{branch}` branch and cherry-pick the following commits manually:

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
    MessageId.CommandFollowUp: "User command action",
    MessageId.CommandSetDraftFollowUpMode: "Follow-up mode set to \"Draft\"",
    MessageId.JobStatusCheckNeedsApproval: "Manual check is needed",
    MessageId.JobStatusChecksPassed: "Job status checks passed",
    MessageId.CommandNotExecuted: "Command was not executed",
    MessageId.FailedCheckForSuccessfulPipeline: "Pipeline failed",
    MessageId.FailedCheckForConflictsWithTargetBranch: "Conflicts with target branch",
    MessageId.FailedCheckForUnresolvedThreads: "Unresolved threads",
    MessageId.FailedCheckForNoSupportedProject: "No supported project found",
    MessageId.InitialMessage: "Looking after this MR",
    MessageId.FollowUpNotNeeded: "Follow-up has not been created",
    MessageId.FailedJobNotification: "Pipeline job failed",
}
bot_readable_comment = {
    MessageId.CommandProcess: "Re-checking Merge Request",
    MessageId.CommandRunPipeline: "Initiating pipeline run",
    MessageId.CommandFollowUp: "Executing follow-up actions",
    MessageId.CommandSetDraftFollowUpMode: """
Follow-up Merge Requests will be created in "Draft" status. To **restore the default behavior**,
remove **this** comment.
""",
    MessageId.JobStatusCheckNeedsApproval: """
This merge request contains changes that **must be approved** by one of: @{approvers}. For the
details, see the results of `{job_name}` job in the pipeline.
""",
    MessageId.JobStatusChecksPassed: """"
Auto-check for job statuses passed successfully. The Merge Request can be merged once all other
criteria are met.
""",
    MessageId.CommandNotExecuted: "Command **{command}** is not executed: {explanation}.",
    MessageId.FailedCheckForSuccessfulPipeline: """
Pipeline [{last_pipeline_id}]({last_pipeline_web_url}) failed. The Merge Request can not be merged
until the errors are fixed. You may rebase or run a new pipeline manually if these errors are
resolved outside the MR.
""",
    MessageId.FailedCheckForConflictsWithTargetBranch: """
Can not merge due to the conflicts with the target branch. Do a manual rebase to continue the
merging process.
""",
    MessageId.FailedCheckForUnresolvedThreads: """
Can not merge due to the unresolved discussions. Resolve all the discussions to continue the
merging process.
""",
    MessageId.FailedCheckForNoSupportedProject: """
The Merge Request is not linked to any Jira Issue known to Robocat. Link this MR to Jira
Issue(s) from at least one of the supported Jira Projects ({jira_projects_list}) to continue the
merging process.
""",
    MessageId.InitialMessage: """
This message is added because Robocat the Automation Bot is assigned to this Merge Request. Robocat
will check that the Merge Request complies to all the necessary criteria and then merge it. After
the merge, Merge Requests with the same changes will be created automatically for all other target
branches determined by the `fixVersions` field of the Jira Issue.

You can ask the bot to perform some actions using comments to this Merge Request. To do this, add
the comment with the following format:
```
@{bot_gitlab_username} <command>
```
where "command" is one of:
- {command_list}

""",
    MessageId.FollowUpNotNeeded: """
This Merge Request seems to be a follow-up, so no follow-ups will be created for it. If for some
reason the follow-up(s) must be created, use the `@follow-up` user command.
""",
    MessageId.FailedJobNotification: """
Job `{job_name}` has failed. Please, investigate and fix the problem.
""",
}
