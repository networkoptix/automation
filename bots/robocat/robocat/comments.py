_wip_url = ("https://docs.gitlab.com/ee/user/project/merge_requests/work_in_progress_merge_requests.html"
            "#removing-the-draft-flag-from-a-merge-request")

initial_message = """Hi, I am Robocat and I will help you merging this MR.
Once the Merge Request is ready I will run the pipeline and automatically merge it.

Please note, I consider Merge Request ready when:
1. It's approved by reviewers *({approvals_left} more required at the moment)*
2. It's not in Draft/WIP status
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
Please, resolve all discussions and [remove WIP]({_wip_url}) to continue merging process."""

conflicts_message = f"""Merge request returned to development.
Please, do manual rebase and [remove WIP]({_wip_url}) to continue merging process."""

has_good_changes_in_open_source = """This merge request contains changes in open source part of the
project. No problems were revealed during autocheck.

**ATTENTION**: This thread should be resolved only by @{approver}.
"""

may_have_changes_in_open_source = """It is impossible to check if this merge request contains
changes in open source part of the project due to the huge amount of changes in it. Please, check
possible changes in open source part manually.

**ATTENTION**: This thread should be resolved only by @{approver}.
"""

has_bad_changes_in_open_source = """{error_message}

**ATTENTION**: This thread should be resolved only by @{approver}.
"""

incorrect_mpl = """MPL check failed: line is:

`{line}`

expected:

`{expected}`
"""

missing_mpl = """MPL check failed: line is empty, expected:

`{expected}`
"""

unknown_license = "License word: **{word}** at line {line_number}"

trademark_violation = "Trademark: **{word}** at line {line_number}"

politeness_violation = "Bad word: **{word}** at line {line_number}"

missing_empty_line = "Line is `{line}`, expected to be empty"

unexpected_shebang = """Shebang is:

`{line}`

expected:

`{shebang}`
"""

unknown_file_type = "Unknown file type: **{file}**"

failed_pipeline_message = f"""Merge request returned to development.
Please, fix the errors and [remove WIP]({_wip_url}) to continue merging process.\n
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
