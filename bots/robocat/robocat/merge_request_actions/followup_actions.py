import logging

from automation_tools.jira import JiraAccessor
from robocat.merge_request_manager import MergeRequestManager, FollowupCreationResult
from robocat.project_manager import ProjectManager

logger = logging.getLogger(__name__)


def create_followup_merge_requests(
        jira: JiraAccessor, project_manager: ProjectManager, mr_manager: MergeRequestManager):
    original_target_branch = mr_manager.data.target_branch
    issue_branches_with_merged_mr = {original_target_branch}
    for issue in jira.get_issues(mr_manager.data.issue_keys):
        issue_branches = issue.branches(exclude_already_merged=True)
        if issue_branches == {original_target_branch}:
            continue
        current_issue_followup_branches = set()

        for target_branch in issue_branches:
            if target_branch in issue_branches_with_merged_mr:
                continue

            logger.debug(
                f"{mr_manager}: Trying to create follow-up merge requests for issue "
                f"{issue} (branch {target_branch}).")
            is_followup_created = create_followup_merge_request(
                project_manager=project_manager,
                mr_manager=mr_manager,
                target_branch=target_branch)

            if is_followup_created:
                issue_branches_with_merged_mr.add(target_branch)
                current_issue_followup_branches.add(target_branch)
            else:
                issue.add_already_in_version_label(target_branch)
        if current_issue_followup_branches:
            issue.add_followups_created_comment(current_issue_followup_branches)


def create_followup_merge_request(
        project_manager: ProjectManager,
        mr_manager: MergeRequestManager,
        target_branch: str) -> bool:
    new_mr = project_manager.create_followup_merge_request(
        target_branch=target_branch, original_mr_manager=mr_manager)

    if new_mr is None:
        return False

    new_mr_manager = MergeRequestManager(new_mr)
    mr_manager.add_followup_creation_comment(FollowupCreationResult(
        branch=target_branch,
        url=new_mr_manager.data.url,
        successful=True))
    return True
