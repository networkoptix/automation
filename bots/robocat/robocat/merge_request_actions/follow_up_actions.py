## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import logging

from automation_tools.jira import JiraAccessor, JiraIssue, GitlabBranchDescriptor
from automation_tools.jira_comments import JiraComment, JiraMessageId
from robocat.merge_request_manager import MergeRequestManager
from robocat.note import MessageId
from robocat.project_manager import EmptyFollowUpError, ProjectManager
from robocat.project import MergeRequestAlreadyExistsError
import robocat.comments

logger = logging.getLogger(__name__)


def create_follow_up_merge_requests(
        jira: JiraAccessor,
        project_manager: ProjectManager,
        mr_manager: MergeRequestManager,
        set_draft_flag: bool = False,
        approve_by_robocat: bool = False,
        default_branch_project_mapping: dict[str, str] = None):
    original_target_branch = mr_manager.data.target_branch
    created_follow_up_branches = set()
    for issue in jira.get_issues(mr_manager.data.issue_keys):
        branch_names = {str(b) for b in issue.branches()}
        logger.info(
            f"{mr_manager}: The following branches are the candidates for the follow-up MR "
            f"creation: {[branch_names]!r}")

        for version, branches in issue.versions_to_branches_map.items():
            if not branches:
                logger.warning(
                    f"{mr_manager}: The target branch for the version {version!r} in Issue "
                    f"{issue} is unknown. Skipping the follow-up MR creation.")
                mr_manager.add_comment(robocat.comments.Message(
                    id=MessageId.UnknownBranchWhenCreatingFollowUp,
                    params={'version': version}))
                continue

            for target_branch in branches:
                # Workaround for legacy target branch definitions (the ones without the project
                # path).
                if target_branch.project_path is None:
                    target_branch = GitlabBranchDescriptor(
                        branch_name=target_branch.branch_name,
                        project_path=default_branch_project_mapping.get(issue.project, 'UNKNOWN'))

                if _create_follow_up_merge_request_for_branch(
                        mr_manager=mr_manager,
                        project_manager=project_manager,
                        issue=issue,
                        created_follow_up_branches=created_follow_up_branches,
                        original_target_branch=original_target_branch,
                        version=version,
                        target_branch=target_branch,
                        set_draft_flag=set_draft_flag,
                        approve_by_robocat=approve_by_robocat):
                    created_follow_up_branches.add(target_branch.branch_name)

        current_issue_follow_up_branches = created_follow_up_branches.intersection(branch_names)
        if current_issue_follow_up_branches:
            issue.add_comment(JiraComment(
                message_id=JiraMessageId.FollowUpMrsCreated,
                params={"branches": "\n* ".join(current_issue_follow_up_branches)}))


def _create_follow_up_merge_request_for_branch(
        mr_manager: MergeRequestManager,
        project_manager: ProjectManager,
        issue: JiraIssue,
        created_follow_up_branches: set[str],
        original_target_branch: str,
        version: str,
        target_branch: GitlabBranchDescriptor,
        set_draft_flag: bool,
        approve_by_robocat: bool) -> bool:
    if (target_branch.project_path != project_manager.data.path):
        logger.info(
            f"{mr_manager}: The target branch for the issue {issue} is in a different project "
            f"({target_branch.project_path}). Skipping the follow-up MR creation.")
        return False

    target_branch_name = target_branch.branch_name
    if target_branch_name in (created_follow_up_branches | {original_target_branch}):
        return False

    logger.info(
        f"{mr_manager}: Trying to create follow-up merge requests for issue {issue} (branch "
        f"{target_branch_name!r}).")
    return create_follow_up_merge_request(
        issue=issue,
        project_manager=project_manager,
        mr_manager=mr_manager,
        target_branch=target_branch_name,
        set_draft_flag=set_draft_flag,
        approve_by_robocat=approve_by_robocat)


def create_follow_up_merge_request(
        issue: JiraIssue,
        project_manager: ProjectManager,
        mr_manager: MergeRequestManager,
        target_branch: str,
        set_draft_flag: bool = False,
        approve_by_robocat: bool = False) -> bool:
    try:
        new_mr = project_manager.create_follow_up_merge_request(
            target_branch=target_branch,
            original_mr_manager=mr_manager,
            set_draft_flag=set_draft_flag)
    except EmptyFollowUpError:
        # EmptyFollowUpError means that cherry-picking commits resulted in an empty diff, i.e.
        # all the changes are already merged to the target branch.
        issue.add_already_in_version_label(
            branch_name=target_branch, project_path=project_manager.data.name)
        return False
    except MergeRequestAlreadyExistsError:
        return False

    new_mr_manager = MergeRequestManager(new_mr)
    mr_manager.add_follow_up_creation_comment(
        branch=target_branch, url=new_mr_manager.data.url, successful=True)

    if approve_by_robocat:
        logger.debug(f"{mr_manager}: Adding Robocat approval to the follow-up MR.")
        needs_manual_resolution = any(
            n
            for n in new_mr_manager.notes()
            if n.message_id == MessageId.ManualResolutionRequired)
        if not needs_manual_resolution:
            new_mr_manager.add_robocat_approval()

    return True
