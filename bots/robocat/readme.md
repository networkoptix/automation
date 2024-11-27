# Workflow Robocat

// Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

_Workflow Robocat_ (or just _Robocat_) is a Gitlab Bot which is designated to automate the Merge
Request merging routine and enforce some workflow rules. _Robocat_ does the following things:

1. Rebase, merge and run pipelines for MRs.
2. Check compliance of the changes made to the open source part of the project, to the rules for
    such changes (no offensive words, correct copyright notice in each file, etc.).
3. Check the consistency of Nx Submodules found in the checked repository.
4. Check workflow rules (commit message conventions, sanity check of the `fixVersion` field of the
    Issue, etc).
5. Move corresponding **Jira Issues** to the _Development Completed_ state (`Waiting for QA` or
   `Closed` if the Issue doesn’t have Waiting for QA status in its workflow).
6. Creates "**follow-up**" Merge Requests.

Robocat only handles Merge Requests assigned to it. Note that any Merge Request assigned to Robocat
must mention (using MR Title/Description or commit messages) Issues from at least one of the
supported Projects. Supported Projects can be listed in the per-repo configuration file.

This bot relies on **webhooks** - it receives notification about changes in Merge Requests
(changing of title, target branch, Draft status, adding new commits, etc.), about adding
**comments** to the Merge Requests and about various **pipeline events**. This implies that if some
change relevant to the Merge Request is done outside of GitLab (for example, somebody changes
`fixVersion` field in the related Jira Issue), Robocat **is not able** to detect this change. To
process the affected Merge Request in this case, the user must manually ask the bot to check it.
Also, for proper working, the corresponding webhooks must be configured in GitLab settings.

## Short How-To

1. Set `In Review` status to the Jira Issues related to the changes included in the new Merge
    Request.
2. Create a Merge Request. Make sure, that at lease one Issue from one of the supported Projects is
    mentioned in the MR Title/Description or in the commit messages.
3. Collect all required approvals from reviewers.
4. Fix all the issues found by the bot.
5. Resolve all the Discussions if the Project settings mandate resolving them before merging an MR.
6. Remove the "Draft" status (if set).
7. After a while make sure the MR was successfully merged.
8. If the Issue has more than one version in its `fixVersions` field make sure that the follow-up
    Merge Requests were created - one for each branch mentioned in the version description.

Only the Issues that have `In review` status are moved to the _Development Completed_ state. The
only other valid status for the Issue related to the merged Merge Request is `In Progress`. For
such Issues, after merging the Merge Request, the comment notifying about the fact that the status
is not changed will be added to the Merge Request. Any other status of the Issue is considered as a
workflow violation and the appropriate comment will be added to the Jira Issue.

## Commit messages and MR Title/Description conventions

If the flag "**Squash**" of the Merge Request is checked, the Title and Description of the Merge
Request becomes the commit message of the commit in the target branch. In this case:

1. The Merge Request Title and Description **MUST** mention some of the Issues in one of the
    supported Project. This can be done either in Title with the format
    `<Issue_key_1>[, <Issue_key_2>[, ..., <Issue_key_N>]...]: <brief changes description>`, or in
    the Description in the format supported by GitLab (e.g.:
    `Closes <Issue_Key_1>, ..., <Issue_Key_N>` or
    `Fixed <Issue_Key_1> and also fixed <Issue_Key_2>` and etc).
2. The Merge Request Title **MUST NOT** contain parentheses right after the colon, separating Issue
    Keys from the brief changes description.
3. If there is exactly one commit in this Merge Request, its commit message MUST be the same with
    the Title and Description of the Merge Request (the Title corresponds to the first string of
    the commit message, while the Description - to everything after the two newlines). Otherwise
    (more than one commit) there are no additional requirements to the commit messages.

If the "**Squash**" flag of the Merge Request is NOT checked the following rules are applied:

1. Issues mentioned in the MR Title/Description MUST be a subset of the Issues, mention in the
    commit messages.
2. All the commit message MUST contain at least one mention of some Issue (it can be any Project,
    not just one of the supported).

## Using commands to control Robocat

Workflow Robocat can be controlled using Merge Request comments. To send the command to the bot,
add the comment in the following form:

```
1 @workflow-robocat <command> [<command parameters>]
2 [any text]
```

For now the following commands are supported:
- `process`: Force processing of the current Merge Request by Robocat.
- `run-pipeline`: Force pipeline run for the current MR.
- `follow-up`: Run follow-up actions (create follow-up Merge Requests and close the related Jira
    Issues if possible). This command make sense only for the already merged Merge Requests.
- `draft-follow-up`: For merged Merge Requests, this command works like `follow-up`, but the
    follow-up Merge Requests are created in the Draft mode. For unmerged Merge Requests, no
    immediate action takes place - the command just changes the mode of follow-up creation.

## Implementation details

### Pipelines

_Robocat_ automatically runs pipelines for the Merge Request in the following cases:

1. First run. Performed when no pipelines were previously run for this MR.
2. Manual run. Performed when the user asks the bot to do this by using run-pipeline command.
3. Re-run after new changes are introduced to the Merge Request via adding new commit, amending one
    of the existing commits or rebasing (only if the changes introduced by the rebasing affects the
    changes introduced by the MR commits). Such re-run occurs only when all of the following
    conditions are met:
        a. The Merge Request is not in the Draft state.
        b. The Merge Request has enough approvals.
        c. It is technically possible to merge this Merge Request (no conflicts with the target
            branch).

When the pipeline is run for any reason, Robocat tries to rebase the Merge Request to the last
commit in the target branch.

Note that "run pipeline" means "running all the jobs in the pipeline which have state `manual`". If
pipeline has jobs, that run automatically by GitLab, these jobs will run **always** and the logic
described above is not applicable. That means that when Robocat is added for a new repository, the
pipeline configuration is likely to be changed - it makes sense to fix the start conditions for at
least the most time-consuming jobs (make them manually started) to use benefits of using of
Robocat. If there is a need to have manual jobs which **should not be run by Robocat** , add
`:no-bot-start` suffix to these job names.

### Open-source checks

If the changes touch an open source part, _Robocat_ automatically checks the affected source files
for the compliance to the Open Source Rules. If it detects violation of some of these rules, it
creates **Discussions** , describing violations found, that should be resolved **only** by one of
the persons who are responsible for the open source code and adds some (depending on what files are
affected) of these persons to `Assignees`. Such Merge Requests MUST be approved by one of these
persons.

If the code is compliant with the rules AND at least one file was added to the open source part,
the bot creates **one** Discussion with the warning that this Merge Request touches open source and
should be reviewed by the authorized person. The same rules apply for the resolving of the
Discussion and approving the Merge Request as for the case when the violations were found.

If the code is compliant with the rules AND no new files were added to the open source part, the
bot creates a Comment informing that the open-source check is passed. No additional actions
required.

### Nx Submodule checks

If the changes touch directories containing some of the Nx Submodules, _Robocat_ performs a
validity check for them. If the check fails (the contents of the Nx Submodule directory is not
consistent with the contents of the corresponding directory in the subrepo) the bot creates
Discussions describing the problems found. Otherwise a Comment informing that the Nx Submodule
check passed is created. For more information about Nx Submodules see
[documentation](https://github.com/networkoptix/tools/blob/master/nx_submodule/readme.md).

### Workflow checks

_Robocat_ performs a sanity check of the fixVersions field of the Jira Issues mentioned in the
Merge Request in the manner described in **The fixVersion sanity check** section of this article.
If the check fails, a Comment describing the problem will be created. The Merge Request can not be
merged until this problem is not fixed.

Also, the bot checks the conventions concerning Merge Request Title/Description and commit messages
of the commit included in the Merge Request. If this check fails, _Robocat_ creates a Comment
describing the problems found. The Merge Request can not be merged until these problems are not
fixed. These conventions are described
[above](#commit-messages-and-mr-title-description-conventions).

### Follow-ups

After the Merge Request is merged, Robocat tries to create **follow-up** merge requests for this
Merge DoneRequest. The process is the following:

If the just merged Merge Request is **not follow-up** Merge Request, _Robocat_ checks the
`fixVersion` field of the **Jira Issues** , which are closed by this Merge Request. For all the
branches, corresponding to versions mentioned in this field, _Robocat_ automatically creates a new
Merge Request and tries to **cherry-pick** the changes introduced by the freshly merged Merge
Request. If some of the changes can’t be automatically cherry-picked, Robocat adds a Comment with
the suggestion for the user to cherry-pick these changes manually. Newly created Merge Requests
have two assignees (Workflow Robocat itself and the creator of the original Merge Request) and
approvals is optional for them.

_Robocat_ considers a Merge Request to be a follow-up Merge Request if it contains a special emoji
(`:fast-forward:`) or if the Merge Request Description or any commit message from this Merge
Request contains string like `(cherry-picked from commit <sha>)`.

### Closing Issues

After merging a Merge Request, Robocat creates a comment in all the related Issues, containing the
name of the target branch, against which the MR was merged. Then it checks for these Issues, if
there are such comments for all the branches mentioned in the Issue via the `fixVersions` field. If
this is true, Robocat tries to move this Jira Issue to the _Development Completed_ state.
