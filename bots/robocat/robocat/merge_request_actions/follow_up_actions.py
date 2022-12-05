import logging

from automation_tools.jira import JiraAccessor
from robocat.merge_request_manager import MergeRequestManager, FollowUpCreationResult
from robocat.project_manager import ProjectManager

logger = logging.getLogger(__name__)


def create_follow_up_merge_requests(
        jira: JiraAccessor,
        project_manager: ProjectManager,
        mr_manager: MergeRequestManager,
        set_draft_flag: bool = False):
    original_target_branch = mr_manager.data.target_branch
    issue_branches_with_merged_mr = {original_target_branch}
    for issue in jira.get_issues(mr_manager.data.issue_keys):
        issue_branches = issue.branches(exclude_already_merged=True)
        if issue_branches == {original_target_branch}:
            continue
        current_issue_follow_up_branches = set()

        for target_branch in issue_branches:
            if target_branch in issue_branches_with_merged_mr:
                continue

            logger.debug(
                f"{mr_manager}: Trying to create follow-up merge requests for issue "
                f"{issue} (branch {target_branch}).")
            is_follow_up_created = create_follow_up_merge_request(
                project_manager=project_manager,
                mr_manager=mr_manager,
                target_branch=target_branch,
                set_draft_flag=set_draft_flag)

            if is_follow_up_created:
                issue_branches_with_merged_mr.add(target_branch)
                current_issue_follow_up_branches.add(target_branch)
            else:
                issue.add_already_in_version_label(target_branch)
        if current_issue_follow_up_branches:
            issue.add_follow_ups_created_comment(current_issue_follow_up_branches)


def create_follow_up_merge_request(
        project_manager: ProjectManager,
        mr_manager: MergeRequestManager,
        target_branch: str,
        set_draft_flag: bool = False) -> bool:
    new_mr = project_manager.create_follow_up_merge_request(
        target_branch=target_branch, original_mr_manager=mr_manager, set_draft_flag=set_draft_flag)

    if new_mr is None:
        return False

    new_mr_manager = MergeRequestManager(new_mr)
    mr_manager.add_follow_up_creation_comment(FollowUpCreationResult(
        branch=target_branch,
        url=new_mr_manager.data.url,
        successful=True))
    return True
