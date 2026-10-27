## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from dataclasses import dataclass
from enum import Enum, StrEnum, unique
from typing import Any

from automation_tools.bot_info import revision as robocat_revision


class Emoji(StrEnum):  # No @unique: names that share an emoji become aliases of the first.
    """The emoji that Robocat uses in comment titles and as reactions on the MR."""

    WAIT = "hourglass_flowing_sand"  # Also a reaction: Robocat waits for approvals or a pipeline.
    PIPELINE = "construction_site"
    NO_PIPELINE = "no_entry"
    INITIAL = "cat2"
    CHECK_FAIL_EXPLANATION = "exclamation"
    AUTOCHECK_FAILED = "stop_sign"
    AUTOCHECK_OK = "white_check_mark"
    MERGED = "white_check_mark"
    FOLLOWUP_CREATED = "arrow_heading_down"
    FOLLOWUP_CREATION_FAILED = "x"
    FOLLOWUP_MERGE_REQUEST = "fast_forward"  # Also a reaction: a follow-up MR made by Robocat.
    CHERRY_PICK = "cherries"
    AUTOCHECK_IMPOSSIBLE = "raised_back_of_hand"  # TODO: Remove with the check for a "huge diff".
    NEED_MANUAL_CHECK = "raised_back_of_hand"
    BAD_ISSUE = "beetle"  # Also a reaction: a workflow problem blocks the merge.
    SUSPICIOUS_ISSUE = "question"  # Also a reaction: a possible workflow problem.
    LOCAL_SQUASH_PROBLEMS = "warning"
    CANNOT_APPROVE = "warning"
    COMMAND_UNKNOWN = "warning"
    NOTIFICATION = "bell"
    ISSUE_NOT_MOVED_TO_QA = "point_up"
    COMMAND_NOT_EXECUTED = "no_entry"
    JOB_FAILED = "exclamation"
    EXCEPTION_OCCURRED = "exclamation"
    JIRA_COMMENT_FAILED = "exclamation"
    JIRA_ISSUE_NOT_CLOSED = "warning"
    MERGE_REJECTED = "warning"
    WATCHING = "eyes"  # Reaction: Robocat looks after the MR.
    UNFINISHED_POST_MERGING = "point_up"  # Reaction: the post-merge work is not done yet.

@dataclass(frozen=True)
class Message:
    """One comment to post: which comment it is, and the values for its text template."""

    id: "Comment"  # Defined below.
    params: dict[str, Any] | None = None

    @property
    def text(self) -> str:
        """The text with the params filled in."""
        text = self.id.value.text
        return text.format(**self.params) if self.params else text

    def format_body(self, data_text: str | None = None) -> str:
        """The note body: title, text, Robocat revision and the hidden data."""
        template = self.id.value
        return f"""### :{template.emoji}: {template.title}

{self.text}

---

###### Robocat rev. {robocat_revision()}.
""" + (data_text or "")  # noqa

@dataclass(frozen=True)
class CommentTemplate:
    """The visible parts of one Robocat comment: its title, emoji and text template."""

    title: str
    emoji: Emoji
    text: str


@unique  # Two equal members would silently become one: fail at import instead.
class Comment(Enum):
    """Every comment that Robocat posts. The member name is stored in the notes: never rename."""

    InitialMessage = CommentTemplate(
        title="Looking after this MR",
        emoji=Emoji.INITIAL,
        text="""
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

""")

    # Job status check.
    JobStatusCheckNeedsApproval = CommentTemplate(
        title="Manual check is needed",
        emoji=Emoji.NEED_MANUAL_CHECK,
        text="""
This merge request contains changes that **must be approved** by one of: @{approvers}. For the
details, see the results of `{job_name}` job in the pipeline.
""")
    JobStatusChecksPassed = CommentTemplate(
        title="Job status checks passed",
        emoji=Emoji.AUTOCHECK_OK,
        text=""""
Auto-check for job statuses passed successfully. The Merge Request can be merged once all other
criteria are met.
""")

    # Nx Submodule check.
    InconsistentNxSubmoduleChange = CommentTemplate(
        title="Autocheck for Nx Submodule integrity failed",
        emoji=Emoji.AUTOCHECK_FAILED,
        text="""The content of the directory `{nx_submodule_dir}` differs
from the content of the directory `{subrepo_dir}` in repository `{subrepo_url}` checked out at
commit `{subrepo_commit_sha}`: *{explanation}*. Fix this using `nx_submodule.py` utility or
manually.

[Nx Submodule documentation](https://github.com/networkoptix/tools/blob/master/nx_submodule/readme.md)


Auto-check of this merge request has failed. Fix all the issues, otherwise this merge request
**will not be merged**.
""")  # noqa: E501
    NxSubmoduleConfigDeleted = CommentTemplate(
        title="Autocheck for Nx Submodule integrity failed",
        emoji=Emoji.AUTOCHECK_FAILED,
        text="""Nx Submodule config file was deleted from the directory
`{nx_submodule_dir}`. This file must be restored to merge this Merge Request.

[Nx Submodule documentation](https://github.com/networkoptix/tools/blob/master/nx_submodule/readme.md)


Auto-check of this merge request has failed. Fix all the issues, otherwise this merge request
**will not be merged**.
""")  # noqa: E501
    NxSubmoduleConfigMalformed = CommentTemplate(
        title="Autocheck for Nx Submodule integrity failed",
        emoji=Emoji.AUTOCHECK_FAILED,
        text="""Nx Submodule config file in the directory `{nx_submodule_dir}`
has wrong format. Fix this using `nx_submodule.py` utility or manually.

[Nx Submodule documentation](https://github.com/networkoptix/tools/blob/master/nx_submodule/readme.md)


Auto-check of this merge request has failed. Fix all the issues, otherwise this merge request
**will not be merged**.
""")  # noqa: E501
    NxSubmoduleConfigBadGitData = CommentTemplate(
        title="Autocheck for Nx Submodule integrity failed",
        emoji=Emoji.AUTOCHECK_FAILED,
        text="""Git error occurred while fetching subrepo `{subrepo_url}` at commit
`{subrepo_commit_sha}` for Nx submodule `{nx_submodule_dir}` (probably, because of an incorrect
value in `subrepo-url` or `commit-sha`): *{explanation}*.

[Nx Submodule documentation](https://github.com/networkoptix/tools/blob/master/nx_submodule/readme.md)


Auto-check of this merge request has failed. Fix all the issues, otherwise this merge request
**will not be merged**.
""")  # noqa: E501
    NxSubmoduleCheckUnknownError = CommentTemplate(
        title="Autocheck for Nx Submodule integrity failed",
        emoji=Emoji.AUTOCHECK_FAILED,
        text="""An unknown error was found while auto-checking Nx Submodule(s)
changed by this Merge Request. **This must be an internal error of the Robocat - report
it to the support**.


Auto-check of this merge request has failed. Fix all the issues, otherwise this merge request
**will not be merged**.
""")
    NxSubmoduleCheckHugeDiffUncheckable = CommentTemplate(
        title="Impossible to autocheck Nx Submodules integrity",
        emoji=Emoji.AUTOCHECK_IMPOSSIBLE,
        text="""Unable to check Nx Submodule(s) changed
by this Merge Request due to the huge amount of changes (gitlab limitation). Please, double-check
it manually.
""")
    NxSubmoduleCheckPassed = CommentTemplate(
        title="Autocheck for Nx Submodules integrity passed",
        emoji=Emoji.AUTOCHECK_OK,
        text="""Auto-check for Nx Submodule(s) changed by this
Merge Request passed successfully. The Merge Request can be merged once all other criteria are met.
""")

    # Jira workflow check: the blockers stop the merge, the "Possible workflow violation" ones not.
    WorkflowBadFixVersions = CommentTemplate(
        title="Jira workflow check failed",
        emoji=Emoji.BAD_ISSUE,
        text="""Workflow violation detected:

Bad `fixVersions` field in the related Jira Issue {issue_key}: {version_error_string}.

""")
    WorkflowDifferentCommitMessage = CommentTemplate(
        title="Merge request title/description does not comply with the rules",
        emoji=Emoji.BAD_ISSUE,
        text="""Workflow violation detected:

For non-squashed Merge Requests with one commit title/description of the Merge Request must be the
same that the commit message. Merge Request title/description is {expected_commit_message!r},
commit message is {first_commit_message!r}.

""")
    WorkflowDifferentJiraIssueSets = CommentTemplate(
        title="Merge request title/description does not comply with the rules",
        emoji=Emoji.BAD_ISSUE,
        text="""Workflow violation detected:

Different Jira Issue sets in Merge Request title/description and commit messages are not allowed
for non-squashed Merge Requests. {actual_issue_keys} are mentioned in the Merge Request
title/description while {actual_commit_issue_keys} are mentioned in the commit messages."

""")
    WorkflowInconsistentFixVersions = CommentTemplate(
        title="Jira workflow check failed",
        emoji=Emoji.BAD_ISSUE,
        text="""Workflow violation detected:

{current_issue_key}: `fixVersions` is inconsistent with `fixVersions` of {first_found_issue_key}:
{current_issue_versions!r} != {first_found_issue_versions!r}.

""")
    WorkflowBadTargetBranch = CommentTemplate(
        title="Jira workflow check failed",
        emoji=Emoji.BAD_ISSUE,
        text="""Workflow violation detected:

Target branch {target_branch!r} does not correspond to any `fixVersion` for Issue {issue_key!r}.

""")
    WorkflowNoJiraIssueInCommitMessage = CommentTemplate(
        title="Merge request title/description does not comply with the rules",
        emoji=Emoji.BAD_ISSUE,
        text="""Workflow violation detected:

In a non-squashed Merge Request, each commit message must contain a reference to at least one Jira
Issue.

""")
    WorkflowNoJiraIssueInMr = CommentTemplate(
        title="Jira workflow check failed",
        emoji=Emoji.BAD_ISSUE,
        text="""Workflow violation detected:

Merge Request must be related to at least one Jira Issue.

""")
    WorkflowOk = CommentTemplate(
        title="Workflow check passed",
        emoji=Emoji.AUTOCHECK_OK,
        text="No workflow errors found.")
    WorkflowParenthesesNotAllowed = CommentTemplate(
        title="Merge request title/description does not comply with the rules",
        emoji=Emoji.BAD_ISSUE,
        text="""Workflow violation detected:

Parentheses right after the Jira Issue ref (or at the beginning, if no Jira Issue is mentioned) in
the title of the squashed follow-up Merge Request are not allowed.

""")
    InconsistentAssigneesInJiraAndGitlab = CommentTemplate(
        title="Possible workflow violation",
        emoji=Emoji.SUSPICIOUS_ISSUE,
        text="""
The assignee of the Merge Request ({mr_assignee!r}) is different from the assignee of the related
Jira Issue {issue_key} ({jira_assignee!r}). This is not a problem by itself, but may be a sign that
the wrong Jira Issue was mentioned in the Merge Request title and/or description. Double-check the
Jira Issue(s) mentioned in the Merge Request and resolve this comment to continue the merging
process.
""")
    UnassignedJiraIssue = CommentTemplate(
        title="Possible workflow violation",
        emoji=Emoji.SUSPICIOUS_ISSUE,
        text="""
The related Jira Issue {issue_key} has no assignee. This is not a problem by itself, but may be a
sign of an incomplete workflow. Double-check the Jira Issue(s) mentioned in the Merge Request and
resolve this comment to continue the merging process.
""")
    SuspiciousJiraIssueStatus = CommentTemplate(
        title="Possible workflow violation",
        emoji=Emoji.SUSPICIOUS_ISSUE,
        text="""
The Issue {issue_key} has status {issue_status!r}. This is not a problem by itself, but may be a
sign that the wrong Jira Issue was mentioned in the Merge Request title and/or description.
Double-check the Jira Issue(s) mentioned in the Merge Request and resolve this comment to continue
the merging process.
""")

    # Follow-up.
    FollowUpNotNeeded = CommentTemplate(
        title="Follow-up has not been created",
        emoji=Emoji.NOTIFICATION,
        text="""
This Merge Request seems to be a follow-up, so no follow-ups will be created for it. If for some
reason the follow-up(s) must be created, use the `@follow-up` user command.
""")
    FollowUpIssueNotMovedToQA = CommentTemplate(
        title="Issue was not moved to QA/Closed",
        emoji=Emoji.ISSUE_NOT_MOVED_TO_QA,
        text="""The Issue {issue_key} was not moved to the QA state
    because of its current status. Check the Issue status and fix in manually if necessary.
""")

    # Commit message check.
    BadCommitMessage = CommentTemplate(
        title="Commit message auto-check failed",
        emoji=Emoji.AUTOCHECK_FAILED,
        text="""{error_message}

Auto-check of this Merge Request has failed. Fix all the issues, or ask one of @{approvers} to
approve this Merge Request. Otherwise, this Merge Request **will not be merged**.
""")
    BadCommitMessageByKeeper = CommentTemplate(
        title="Commit message auto-check failed",
        emoji=Emoji.AUTOCHECK_FAILED,
        text="""{error_message}

Auto-check of this Merge Request has failed. Please, check carefully all the issues and fix them if
needed.
""")
    CommitMessageIsOk = CommentTemplate(
        title="Commit auto-check passed",
        emoji=Emoji.AUTOCHECK_OK,
        text="Commit message is ok.")

    # User commands.
    CommandProcess = CommentTemplate(
        title="User command action",
        emoji=Emoji.NOTIFICATION,
        text="Re-checking Merge Request")
    CommandRunPipeline = CommentTemplate(
        title="User command action",
        emoji=Emoji.NOTIFICATION,
        text="Initiating pipeline run")
    CommandFollowUp = CommentTemplate(
        title="User command action",
        emoji=Emoji.NOTIFICATION,
        text="Executing follow-up actions")
    CommandSetDraftFollowUpMode = CommentTemplate(
        title="Follow-up mode set to \"Draft\"",
        emoji=Emoji.NOTIFICATION,
        text="""
Follow-up Merge Requests will be created in "Draft" status. To **restore the default behavior**,
remove **this** comment.
""")
    CommandNotExecuted = CommentTemplate(
        title="Command was not executed",
        emoji=Emoji.COMMAND_NOT_EXECUTED,
        text="Command **{command}** is not executed: {explanation}.")
    CommandUnknown = CommentTemplate(
        title="Unknown command",
        emoji=Emoji.COMMAND_UNKNOWN,
        text="Command **{command!r}** is not recognized by Robocat.")

    # Merge checks.
    FailedCheckForSuccessfulPipeline = CommentTemplate(
        title="Pipeline failed",
        emoji=Emoji.CHECK_FAIL_EXPLANATION,
        text="""
Pipeline [{last_pipeline_id}]({last_pipeline_web_url}) failed. The Merge Request can not be merged
until the errors are fixed. You may rebase or run a new pipeline manually if these errors are
resolved outside the MR.
""")
    FailedCheckForConflictsWithTargetBranch = CommentTemplate(
        title="Conflicts with target branch",
        emoji=Emoji.CHECK_FAIL_EXPLANATION,
        text="""
Can not merge due to the conflicts with the target branch. Do a manual rebase to continue the
merging process.
""")
    FailedCheckForUnresolvedThreads = CommentTemplate(
        title="Unresolved threads",
        emoji=Emoji.CHECK_FAIL_EXPLANATION,
        text="""
Can not merge due to the unresolved discussions. Resolve all the discussions to continue the
merging process.
""")
    FailedCheckForNoSupportedProject = CommentTemplate(  # A workflow blocker.
        title="No supported project found",
        emoji=Emoji.BAD_ISSUE,
        text="""Workflow violation detected:

The Merge Request is not linked to any Jira Issue known to Robocat. Link this MR to Jira
Issue(s) from at least one of the supported Jira Projects ({jira_projects_list}) to continue the
merging process.

""")
    FailedJobNotification = CommentTemplate(
        title="Pipeline job failed",
        emoji=Emoji.JOB_FAILED,
        text="""
Job `{job_name}` has failed. Please, investigate and fix the problem.
""")
    ExceptionOccurred = CommentTemplate(
        title="Robocat failed to process this Merge Request",
        emoji=Emoji.EXCEPTION_OCCURRED,
        text="""
An exception occurred while Robocat was processing this Merge Request. Open "Details" for the
exception type and the stack trace.
""")
    CannotApproveAsUser = CommentTemplate(
        title="Cannot approve",
        emoji=Emoji.CANNOT_APPROVE,
        text="Cannot approve on behalf of @{username}.")

    # Follow-up creation.
    FollowUpExistsForTheBranch = CommentTemplate(
        title="Follow-up Merge Request already exists",
        emoji=Emoji.CHECK_FAIL_EXPLANATION,
        text="""
Cannot create the follow-up for branch `{target_branch}` - there is already existing Merge Request
to this branch from branch `{source_branch}`.
""")
    UnknownBranchWhenCreatingFollowUp = CommentTemplate(
        title="Failed to create follow-up",
        emoji=Emoji.CHECK_FAIL_EXPLANATION,
        text="""
Cannot create the follow-up for version `{version}` - a branch corresponding to this version is not
defined. Check the description of the corresponging Release in Jira.
""")
    ManualResolutionRequired = CommentTemplate(
        title="Manual conflict resolution required",
        emoji=Emoji.CHERRY_PICK,
        text="""
Cherry-picking creates conflicts. Please, fetch `{branch}` branch and cherry-pick the following
commits manually:

`git cherry-pick -x {commits}`
""")
    FailedMrMergedJiraComment = CommentTemplate(
        title="Failed to add information to Jira Issue",
        emoji=Emoji.JIRA_COMMENT_FAILED,
        text="""
Failed to add information about the merged Merge Request to the Jira Issue {issue_key}:
```
{error}
```
. This may result in the Jira Issue **not being moved** to the QA state automatically; therefore,
most likely, you need to move it manually.
""")
    UnknownProjectWhenClosingIssue = CommentTemplate(
        title="Failed to close Jira Issue",
        emoji=Emoji.JIRA_ISSUE_NOT_CLOSED,
        text="""
The branch specification `{branch}` does not contain explicit GitLab Project information, and the
default GitLab Project for Jira Project {project} is not specified in the bot configuration. Hence
the bot cannot check if the branch is merged. Please, process the Issue {issue} manually.

Consider fixing the Release descriptions for the Jira Project {project} to explicitly specify
GitLab Projects for all the branches.
""")

    # Pipeline and approvals.
    RefuseRunPipelineMessage = CommentTemplate(
        title="Pipeline was not started",
        emoji=Emoji.NO_PIPELINE,
        text="""
Refusing to run user-requested pipeline because the previous pipeline
([{pipeline_id}]({pipeline_url})) ran for the same commit (sha: {sha}).
""")
    AuthorizedApproversAssigned = CommentTemplate(
        title="Update assignee list",
        emoji=Emoji.NOTIFICATION,
        text="""
@{approvers} were assigned to this merge request because it contains new or renamed files in the
open-source part of the project.
""")
    CommitMessageAuthorizedApproversAssigned = CommentTemplate(
        title="Update assignee list",
        emoji=Emoji.NOTIFICATION,
        text="""
@{approvers} were assigned to this merge request because its commit message contains
licensing-related or other sensitive wording.
""")
    RunPipelineMessage = CommentTemplate(
        title="Pipeline started",
        emoji=Emoji.PIPELINE,
        text="Running pipeline [#{pipeline_id}]({pipeline_url}): {reason}.")

    # Waiting states.
    WaitingForCommits = CommentTemplate(
        title="Waiting for commits",
        emoji=Emoji.WAIT,
        text="""
There are no commits in MR. I won't do anything until commits arrive.
""")
    WaitingForApproval = CommentTemplate(
        title="Waiting for approvals",
        emoji=Emoji.WAIT,
        text="""
Not enough approvals, **{approvals_left} more** required. I will start merging process once all
approvals are collected.
""")
    WaitingForPipeline = CommentTemplate(
        title="Waiting for pipeline",
        emoji=Emoji.WAIT,
        text="""
There is already [pipeline {pipeline_id}]({pipeline_url}) in progress. Let's wait until it
finishes.
""")

    # Merge and follow-up results.
    MrMerged = CommentTemplate(
        title="MR merged",
        emoji=Emoji.MERGED,
        text="Merge request was successfully merged into `{branch}` branch.")
    MergeRejected = CommentTemplate(
        title="GitLab rejected the merge",
        emoji=Emoji.MERGE_REJECTED,
        text="""
GitLab refused to merge this Merge Request: {reason}.

To fix it, do what the merge box of this Merge Request shows: resolve conflicts or threads, fix
the pipeline or get the approvals. Then write `@{bot_gitlab_username} process` in a comment, and
Robocat tries again.
""")
    FollowUpCreationSuccessful = CommentTemplate(
        title="Follow-up merge request added",
        emoji=Emoji.FOLLOWUP_CREATED,
        text="""
Follow-up merge request {url} is created for merging changes added in this merge request into
`{branch}` branch.
""")
    FollowUpCreationFailed = CommentTemplate(
        title="Failed to add follow-up merge request",
        emoji=Emoji.FOLLOWUP_CREATION_FAILED,
        text="""
Failed to create follow-up merge request for merging changes added in this merge request into
`{branch}` branch: {comment}.
""")
    CannotSquashLocally = CommentTemplate(
        title="Cannot squash locally",
        emoji=Emoji.LOCAL_SQUASH_PROBLEMS,
        text="""
Failed to squash commits locally by git. See bot logs for details.
""")
    CannotRestoreApprovals = CommentTemplate(
        title="Cannot restore approvals",
        emoji=Emoji.LOCAL_SQUASH_PROBLEMS,
        text="""
Failed to restore approvals of some of the following users: {approvers}. Please, re-approve
manually.
""")
    FollowUpInitialMessage = CommentTemplate(
        title="Follow-up merge request",
        emoji=Emoji.FOLLOWUP_MERGE_REQUEST,
        text="""
This merge request is created as a follow-up for merging changes added in Merge Request
{original_mr_url} into `{branch}` branch.
""")
