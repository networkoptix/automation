import logging
import re
from typing import Generator, Set, List
from gitlab import GitlabCherryPickError, GitlabGetError

from robocat.project import Project
from robocat.merge_request import MergeRequest
from robocat.merge_request_manager import FollowupData
from robocat.award_emoji_manager import AwardEmojiManager
import robocat.comments

logger = logging.getLogger(__name__)


class ProjectManager:
    def __init__(self, gitlab_project, current_user, dry_run=False):
        self._current_user = current_user
        self._dry_run = dry_run
        self._project = Project(gitlab_project, dry_run=dry_run)

    def file_get_content(self, sha: str, file: str) -> str:
        return self._project.get_file_content(sha=sha, file=file)

    @property
    def project_name(self):
        return self._project.project_name

    def create_followup_merge_request(
            self, target_branch: str, followup_mr_data: FollowupData) -> MergeRequest:
        if self._dry_run:
            return None

        mr = self._create_empty_followup_mr(
            target_branch=target_branch, followup_mr_data=followup_mr_data)

        logger.info(
            f"Follow-up merge request {mr.title} (id: {mr.id}) for merge request "
            f"{followup_mr_data.title} has been created. Source branch: {mr.source_branch}, "
            f"target branch: {target_branch}.")

        commit_sha_list = followup_mr_data.commit_sha_list
        assert len(commit_sha_list) > 0, "No commits for cherry-pick"
        self._add_commits_to_followup_mr(merge_request=mr, commit_sha_list=commit_sha_list)

        return mr

    def _create_empty_followup_mr(
            self, target_branch: str, followup_mr_data: FollowupData) -> MergeRequest:
        branch_name = f"{followup_mr_data.original_source_branch}_{target_branch}"
        self._project.create_branch(branch=branch_name, from_branch=target_branch)

        title = re.sub(r'^(\w+-\d+:\s+)?', rf'\1({target_branch}) ', followup_mr_data.title)
        description = f"{followup_mr_data.description}\n\n" + "\n".join(
            f"(cherry picked from commit {sha})" for sha in followup_mr_data.commit_sha_list)
        raw_mr = self._project.create_merge_request(
            source_branch=branch_name,
            target_branch=target_branch,
            title=title,
            description=description,
            author=followup_mr_data.author_username)

        mr = MergeRequest(raw_mr, self._current_user, self._dry_run)
        mr.set_approvers_count(0)
        mr.award_emoji.create(AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI)
        mr.create_note(body=robocat.comments.template.format(
            title="Follow-up merge request",
            message=robocat.comments.followup_initial_message.format(
                branch=target_branch, original_mr_url=followup_mr_data.original_mr_url),
            emoji=AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI))

        return mr

    def _add_commits_to_followup_mr(self, merge_request: MergeRequest, commit_sha_list: List[str]):
        last_cherry_picked_commit_number = 0
        for commit_sha in commit_sha_list:
            try:
                self._project.cherry_pick_to_branch(merge_request.source_branch, commit_sha)
            except GitlabCherryPickError as error:
                logger.info(
                    f"Can't cherry-pick commit {commit_sha} to branch "
                    f"{merge_request.source_branch}: {error}")
                merge_request.create_note(body=robocat.comments.template.format(
                    title="Manual conflict resolution required",
                    message=robocat.comments.conflicting_commit_followup_message.format(
                        branch=merge_request.source_branch,
                        commits=" ".join(commit_sha_list[last_cherry_picked_commit_number:])),
                    emoji=AwardEmojiManager.CHERRY_PICK_EMOJI))
                return

            last_cherry_picked_commit_number += 1

    def get_next_open_merge_request(self) -> Generator[MergeRequest, None, None]:
        return self._get_next_merge_request(state='opened')

    def get_next_unfinished_merge_request(self) -> Generator[MergeRequest, None, None]:
        return self._get_next_merge_request(
            my_reaction_emoji=AwardEmojiManager.UNFINISHED_PROCESSING_EMOJI)

    def _get_next_merge_request(self, **kwargs) -> Generator[MergeRequest, None, None]:
        mrs = self._project.get_raw_mrs(as_list=False, **kwargs)
        for raw_mr in mrs:
            if self._current_user in (assignee["username"] for assignee in raw_mr.assignees):
                yield MergeRequest(raw_mr, self._current_user, self._dry_run)

    def get_merged_branches_by_mr_ids(self, mr_ids: Set[int]) -> Set[str]:
        branches_with_merged_mrs = set()
        branches_with_open_mrs = set()
        # Include target branch in the resulting set only if all merge requests to this target
        # branch are merged.
        for mr_id in sorted(mr_ids):
            try:
                mr = MergeRequest(self._project.get_raw_mr_by_id(mr_id), self._current_user)
                if mr.is_merged:
                    branches_with_merged_mrs.add(mr.target_branch)
                else:
                    branches_with_open_mrs.add(mr.target_branch)
            except GitlabGetError as error:
                logger.error(f"Can't obtain merge request with id {mr_id}: {error}")

        return branches_with_merged_mrs - branches_with_open_mrs
