import logging
import dataclasses
import re

from git import GitCommandError
from gitlab import GitlabGetError
from typing import Generator, Set, List

from robocat.project import Project
from robocat.merge_request import MergeRequest
from robocat.merge_request_manager import MergeRequestManager, MergeRequestData
from robocat.award_emoji_manager import AwardEmojiManager
import robocat.comments
import robocat.gitlab
import automation_tools.bot_info

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class ProjectData:
    name: str
    namespace: str
    ssh_url: str


class EmptyFollowupError(RuntimeError):
    pass


class ProjectManager:
    def __init__(self, gitlab_project, current_user, repo):
        self._current_user = current_user
        self._project = Project(gitlab_project)
        self._gitlab = robocat.gitlab.Gitlab(gitlab_project.manager.gitlab)
        self._repo = repo

    @property
    def data(self) -> ProjectData:
        return ProjectData(
            **{f.name: getattr(self._project, f.name) for f in dataclasses.fields(ProjectData)})

    def file_get_content(self, sha: str, file: str) -> str:
        return self._project.get_file_content(sha=sha, file=file)

    def create_followup_merge_request(
            self, target_branch: str, original_mr_manager: MergeRequestManager) -> MergeRequest:
        commits = original_mr_manager.get_merged_commits()
        assert len(commits) > 0, "No commits for cherry-pick"

        original_mr_data = original_mr_manager.data
        followup_mr_source_branch = f"{original_mr_data.source_branch}_{target_branch}"
        source_project = self._gitlab.get_project(
            original_mr_data.source_branch_project_id, lazy=False)
        self._create_new_branch(
            new_branch=followup_mr_source_branch,
            base_branch=target_branch,
            project=source_project)

        try:
            cherry_picked_commit_count = self._add_commits_to_branch(
                branch=followup_mr_source_branch, remote=source_project.namespace, commits=commits)
        except EmptyFollowupError:
            logger.info(
                f"Seems that all the changes from '{original_mr_manager}' are already in branch "
                f"{target_branch}. Follow-up merge request is not created.")
            return None

        mr = self._create_followup_mr_from_branch(
            source_branch=followup_mr_source_branch,
            target_branch=target_branch,
            original_mr_data=original_mr_data,
            source_project=source_project,
            commits=commits,
            cherry_picked_commit_count=cherry_picked_commit_count)

        return mr

    def _create_new_branch(self, new_branch: str, base_branch: str, project: Project):
        logger.debug(
            f"Creating branch '{new_branch}' in '{project.namespace}' ({project.ssh_url}) "
            f"from '{base_branch}' in '{self._project.namespace}' ({self._project.ssh_url})")
        self._repo.add_remote(project.namespace, project.ssh_url)
        self._repo.create_branch(
            new_branch=new_branch,
            target_remote=project.namespace,
            source_branch=base_branch,
            source_remote=self._project.namespace)

    def _add_commits_to_branch(self, branch: str, remote: str, commits: List[str]) -> int:
        cherry_picked_commit_count = 0
        for sha in commits:
            try:
                # cherry-pick command can fail for two reasons:
                # 1. Conflict with the target branch.
                # 2. Nothing to cherry-pick (incoming changes are already in the target branch).
                #
                # In the first case cherry_pick() throws an exception, because we have to stop the
                # cherry-picking process. In the second case we can procede, but we must be aware
                # of the fact that no changes were picked, so cherry_pick() returns "False".
                cherry_pick_result = self._repo.cherry_pick(sha=sha, branch=branch, remote=remote)
                if cherry_pick_result:
                    cherry_picked_commit_count += 1
                    self._repo.push_current_branch(remote)
            except GitCommandError as error:
                logger.warning(f"Can't cherry-pick commit {sha} to branch {branch}: {error}")
                return cherry_picked_commit_count

        # No error occured but nothing was cherry-picked, thus no neeed to create the follow-up MR.
        if not cherry_picked_commit_count:
            raise EmptyFollowupError

        return cherry_picked_commit_count

    def _create_followup_mr_from_branch(
            self, source_branch: str, target_branch: str, original_mr_data: MergeRequestData,
            source_project: Project, commits: List[str],
            cherry_picked_commit_count: int) -> MergeRequest:
        title = re.sub(
            r'^(\w+-\d+:\s+)?',
            rf'\1({original_mr_data.target_branch}->{target_branch}) ',
            original_mr_data.title)
        logger.debug(
            f"Creating MR '{title}' from '{source_branch}' to '{target_branch}'"
            f"(project {source_project.id} => {self._project.id})")

        if original_mr_data.description:
            description = f"{original_mr_data.description}\n\n"
        else:
            description = ""
        description += "\n\n".join(f"(cherry-picked from commit {sha})" for sha in commits)

        user_gitlab = self._gitlab.get_gitlab_object_for_user(original_mr_data.author_name)
        user_project = user_gitlab.get_project(source_project.id)

        mr_id = user_project.create_merge_request(
            source_branch=source_branch,
            target_branch=target_branch,
            target_project_id=self._project.id,
            title=title,
            description=description,
            squash=False,
            assignee_ids=[self._gitlab.user_id, user_gitlab.user_id])
        raw_mr = self._project.get_raw_mr_by_id(mr_id)

        mr = MergeRequest(raw_mr, self._current_user)
        mr.set_approvers_count(0)
        mr.award_emoji.create(AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI)
        mr.create_note(body=robocat.comments.template.format(
            title="Follow-up merge request",
            message=robocat.comments.followup_initial_message.format(
                branch=target_branch, original_mr_url=original_mr_data.url),
            emoji=AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI,
            revision=automation_tools.bot_info.revision()))

        if cherry_picked_commit_count < len(commits):
            mr.create_note(body=robocat.comments.template.format(
                title="Manual conflict resolution required",
                message=robocat.comments.conflicting_commit_followup_message.format(
                    branch=source_branch, commits=" ".join(commits[cherry_picked_commit_count:])),
                emoji=AwardEmojiManager.CHERRY_PICK_EMOJI,
                revision=automation_tools.bot_info.revision()))
            mr.set_draft_flag()

        return mr

    def get_next_open_merge_request(self) -> Generator[MergeRequest, None, None]:
        return self._get_next_merge_request(state='opened')

    def get_next_unfinished_merge_request(self) -> Generator[MergeRequest, None, None]:
        return self._get_next_merge_request(
            my_reaction_emoji=AwardEmojiManager.UNFINISHED_PROCESSING_EMOJI)

    def _get_next_merge_request(self, **kwargs) -> Generator[MergeRequest, None, None]:
        mrs = self._project.get_raw_mrs(as_list=False, **kwargs)
        for raw_mr in mrs:
            if self._current_user in (assignee["username"] for assignee in raw_mr.assignees):
                yield MergeRequest(raw_mr, self._current_user)

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
                elif not mr.is_closed:
                    branches_with_open_mrs.add(mr.target_branch)
            except GitlabGetError as error:
                logger.error(f"Can't obtain merge request with id {mr_id}: {error}")

        logger.debug(
            f"Branches with open merge requests: {branches_with_open_mrs!r}; "
            f"branches with merged merge requests: {branches_with_merged_mrs!r}")

        return branches_with_merged_mrs - branches_with_open_mrs
