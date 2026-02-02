## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from dataclasses import dataclass
from typing import Optional

from automation_tools.bot_info import revision as robocat_revision
from robocat.award_emoji_manager import AwardEmojiManager
from robocat.note import MessageId


@dataclass(frozen=True)
class Message:
    id: MessageId
    params: Optional[dict[str, str]] = None

    @property
    def text(self) -> str:
        return (bot_readable_comment[self.id].format(**self.params)
                if self.params
                else bot_readable_comment[self.id])

    @property
    def title(self) -> str:
        return (bot_readable_comment_title[self.id].format(self.params)
                if self.params
                else bot_readable_comment_title[self.id])

    @property
    def emoji(self) -> str:
        return AwardEmojiManager.EMOJI_BY_MESSAGE_ID.get(self.id, "")

    def format_body(self, data_text: Optional[str] = None) -> str:
        return format_body(
            title=self.title, message=self.text, emoji=self.emoji) + (data_text or "")


def format_body(title: str, message: str, emoji: str) -> str:
    return f"""### :{emoji}: {title}

{message}

---

###### Robocat rev. {robocat_revision()}. See its [documentation](https://github.com/networkoptix/automation/blob/master/bots/robocat/readme.md)
"""  # noqa


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

###### Robocat rev. {revision}. See its [documentation](https://github.com/networkoptix/automation/blob/master/bots/robocat/readme.md)
"""  # noqa


workflow_error_message = """Workflow violation detected:
{error}
"""


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

[Nx Submodule documentation](https://github.com/networkoptix/tools/blob/master/nx_submodule/readme.md)
"""  # noqa


nx_submodule_config_deleted = """Nx Submodule config file was deleted from the directory
`{nx_submodule_dir}`. This file must be restored to merge this Merge Request.

[Nx Submodule documentation](https://github.com/networkoptix/tools/blob/master/nx_submodule/readme.md)
"""  # noqa


nx_submodule_config_malformed = """Nx Submodule config file in the directory `{nx_submodule_dir}`
has wrong format. Fix this using `nx_submodule.py` utility or manually.

[Nx Submodule documentation](https://github.com/networkoptix/tools/blob/master/nx_submodule/readme.md)
"""  # noqa


unknown_nx_submodule_error = """An unknown error was found while auto-checking Nx Submodule(s)
changed by this Merge Request. **This must be an internal error of the Robocat - report
it to the support**.
"""


nx_submodule_bad_git_data = """Git error occurred while fetching subrepo `{subrepo_url}` at commit
`{subrepo_commit_sha}` for Nx submodule `{nx_submodule_dir}` (probably, because of an incorrect
value in `subrepo-url` or `commit-sha`): *{explanation}*.

[Nx Submodule documentation](https://github.com/networkoptix/tools/blob/master/nx_submodule/readme.md)
"""  # noqa


bot_readable_comment_title = {
    MessageId.CommandProcess: "User command action",
    MessageId.CommandRunPipeline: "User command action",
    MessageId.CommandFollowUp: "User command action",
    MessageId.CommandSetDraftFollowUpMode: "Follow-up mode set to \"Draft\"",
    MessageId.CommandUnknown: "Unknown command",
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
    MessageId.ExceptionOccurred: "Robocat failed to process this Merge Request",
    MessageId.CannotApproveAsUser: "Cannot approve",
    MessageId.FollowUpExistsForTheBranch: "Follow-up Merge Request already exists",
    MessageId.UnknownBranchWhenCreatingFollowUp: "Failed to create follow-up",
    MessageId.WorkflowNoJiraIssueInMr: "Jira workflow check failed",
    MessageId.WorkflowBadFixVersions: "Jira workflow check failed",
    MessageId.WorkflowInconsistentFixVersions: "Jira workflow check failed",
    MessageId.WorkflowBadTargetBranch: "Jira workflow check failed",
    MessageId.WorkflowDifferentJiraIssueSets: (
        "Merge request title/description does not comply with the rules"),
    MessageId.WorkflowDifferentCommitMessage: (
        "Merge request title/description does not comply with the rules"),
    MessageId.WorkflowParenthesesNotAllowed: (
        "Merge request title/description does not comply with the rules"),
    MessageId.WorkflowNoJiraIssueInCommitMessage: (
        "Merge request title/description does not comply with the rules"),
    MessageId.InconsistentAssigneesInJiraAndGitlab: "Possible workflow violation",
    MessageId.UnassignedJiraIssue: "Possible workflow violation",
    MessageId.SuspiciousJiraIssueStatus: "Possible workflow violation",
    MessageId.ManualResolutionRequired: "Manual conflict resolution required",
    MessageId.FailedMrMergedJiraComment: "Failed to add information to Jira Issue",
    MessageId.UnknownProjectWhenClosingIssue: "Failed to close Jira Issue",
    MessageId.RefuseRunPipelineMessage: "Pipeline was not started",
    MessageId.AuthorizedApproversAssigned: "Update assignee list",
    MessageId.RunPipelineMessage: "Pipeline started",
    MessageId.WaitingForCommits: "Waiting for commits",
    MessageId.WaitingForApproval: "Waiting for approvals",
    MessageId.WaitingForPipeline: "Waiting for pipeline",
    MessageId.MrMerged: "MR merged",
    MessageId.FollowUpCreationSuccessful: "Follow-up merge request added",
    MessageId.FollowUpCreationFailed: "Failed to add follow-up merge request",
    MessageId.WorkflowOk: "Workflow check passed",
    MessageId.CannotSquashLocally: "Cannot squash locally",
    MessageId.CannotRestoreApprovals: "Cannot restore approvals",
    MessageId.FollowUpIssueNotMovedToQA: "Issue was not moved to QA/Closed",
    MessageId.FollowUpInitialMessage: "Follow-up merge request",
}


bot_readable_comment = {
    MessageId.CommandProcess: "Re-checking Merge Request",
    MessageId.CommandRunPipeline: "Initiating pipeline run",
    MessageId.CommandFollowUp: "Executing follow-up actions",
    MessageId.CommandSetDraftFollowUpMode: """
Follow-up Merge Requests will be created in "Draft" status. To **restore the default behavior**,
remove **this** comment.
""",
    MessageId.CommandUnknown: "Command **{command!r}** is not recognized by Robocat.",
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
    MessageId.ExceptionOccurred: """
An exception occurred while Robocat was processing this Merge Request. Open "Details" for the
exception type and the stack trace.
""",
    MessageId.CannotApproveAsUser: "Cannot approve on behalf of @{username}.",
    MessageId.FollowUpExistsForTheBranch: """
Cannot create the follow-up for branch `{target_branch}` - there is already existing Merge Request
to this branch from branch `{source_branch}`.
""",
    MessageId.UnknownBranchWhenCreatingFollowUp: """
Cannot create the follow-up for version `{version}` - a branch corresponding to this version is not
defined. Check the description of the corresponging Release in Jira.
""",
    MessageId.WorkflowNoJiraIssueInMr: """
Merge Request must be related to at least one Jira Issue.
""",
    MessageId.WorkflowBadFixVersions: """
Bad `fixVersions` field in the related Jira Issue {issue_key}: {version_error_string}.
""",
    MessageId.WorkflowInconsistentFixVersions: """
{current_issue_key}: `fixVersions` is inconsistent with `fixVersions` of {first_found_issue_key}:
{current_issue_versions!r} != {first_found_issue_versions!r}.
""",
    MessageId.WorkflowBadTargetBranch: """
Target branch {target_branch!r} does not correspond to any `fixVersion` for Issue {issue_key!r}.
""",
    MessageId.WorkflowDifferentJiraIssueSets: """
Different Jira Issue sets in Merge Request title/description and commit messages are not allowed
for non-squashed Merge Requests. {actual_issue_keys} are mentioned in the Merge Request
title/description while {actual_commit_issue_keys} are mentioned in the commit messages."
""",
    MessageId.WorkflowDifferentCommitMessage: """
For non-squashed Merge Requests with one commit title/description of the Merge Request must be the
same that the commit message. Merge Request title/description is {expected_commit_message!r},
commit message is {first_commit_message!r}.
""",
    MessageId.WorkflowParenthesesNotAllowed: """
Parentheses right after the Jira Issue ref (or at the beginning, if no Jira Issue is mentioned) in
the title of the squashed follow-up Merge Request are not allowed.
""",
    MessageId.WorkflowNoJiraIssueInCommitMessage: """
In a non-squashed Merge Request, each commit message must contain a reference to at least one Jira
Issue.
""",
    MessageId.InconsistentAssigneesInJiraAndGitlab: """
The assignee of the Merge Request ({mr_assignee!r}) is different from the assignee of the related
Jira Issue {issue_key} ({jira_assignee!r}). This is not a problem by itself, but may be a sign that
the wrong Jira Issue was mentioned in the Merge Request title and/or description. Double-check the
Jira Issue(s) mentioned in the Merge Request and resolve this comment to continue the merging
process.
""",
    MessageId.UnassignedJiraIssue: """
The related Jira Issue {issue_key} has no assignee. This is not a problem by itself, but may be a
sign of an incomplete workflow. Double-check the Jira Issue(s) mentioned in the Merge Request and
resolve this comment to continue the merging process.
""",
    MessageId.SuspiciousJiraIssueStatus: """
The Issue {issue_key} has status {issue_status!r}. This is not a problem by itself, but may be a
sign that the wrong Jira Issue was mentioned in the Merge Request title and/or description.
Double-check the Jira Issue(s) mentioned in the Merge Request and resolve this comment to continue
the merging process.
""",
    MessageId.ManualResolutionRequired: """
Cherry-picking creates conflicts. Please, fetch `{branch}` branch and cherry-pick the following
commits manually:

`git cherry-pick -x {commits}`
""",
    MessageId.FailedMrMergedJiraComment: """
Failed to add information about the merged Merge Request to the Jira Issue {issue_key}:
```
{error}
```
. This may result in the Jira Issue **not being moved** to the QA state automatically; therefore,
most likely, you need to move it manually.
""",
    MessageId.UnknownProjectWhenClosingIssue: """
The branch specification `{branch}` does not contain explicit GitLab Project information, and the
default GitLab Project for Jira Project {project} is not specified in the bot configuration. Hence
the bot cannot check if the branch is merged. Please, process the Issue {issue} manually.

Consider fixing the Release descriptions for the Jira Project {project} to explicitly specify
GitLab Projects for all the branches.
""",
    MessageId.RefuseRunPipelineMessage: """
Refusing to run user-requested pipeline because the previous pipeline
([{pipeline_id}]({pipeline_url})) ran for the same commit (sha: {sha}).
""",
    MessageId.AuthorizedApproversAssigned: """
@{approvers} were assigned to this merge request because it contains new or renamed files in the
open-source part of the project.
""",
    MessageId.RunPipelineMessage: "Running pipeline [#{pipeline_id}]({pipeline_url}): {reason}.",
    MessageId.WaitingForCommits: """
There are no commits in MR. I won't do anything until commits arrive.
""",
    MessageId.WaitingForApproval: """
Not enough approvals, **{approvals_left} more** required. I will start merging process once all
approvals are collected.
""",
    MessageId.WaitingForPipeline: """
There is already [pipeline {pipeline_id}]({pipeline_url}) in progress. Let's wait until it
finishes.
""",
    MessageId.MrMerged: "Merge request was successfully merged into `{branch}` branch.",
    MessageId.FollowUpCreationSuccessful: """
Follow-up merge request {url} is created for merging changes added in this merge request into
`{branch}` branch.
""",
    MessageId.FollowUpCreationFailed: """
Failed to create follow-up merge request for merging changes added in this merge request into
`{branch}` branch: {comment}.
""",
    MessageId.WorkflowOk: "No workflow errors found.",
    MessageId.CannotSquashLocally: """
Failed to squash commits locally by git. See bot logs for details.
""",
    MessageId.CannotRestoreApprovals: """
Failed to restore approvals of some of the following users: {approvers}. Please, re-approve
manually.
""",
    MessageId.FollowUpIssueNotMovedToQA: """The Issue {issue_key} was not moved to the QA state
    because of its current status. Check the Issue status and fix in manually if necessary.
""",
    MessageId.FollowUpInitialMessage: """
This merge request is created as a follow-up for merging changes added in Merge Request
{original_mr_url} into `{branch}` branch.
"""
}
