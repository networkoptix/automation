## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import logging
import dataclasses
import logging
import re
from typing import Generator

from git import GitCommandError
from gitlab import GitlabGetError

import automation_tools
from robocat.award_emoji_manager import AwardEmojiManager
from robocat.merge_request import MergeRequest
from robocat.merge_request_manager import MergeRequestManager, MergeRequestData
from robocat.note import MessageId, Note, NoteDetails
from robocat.pipeline import Pipeline, PipelineLocation
from robocat.project import Project, MergeRequestAlreadyExistsError
from robocat.award_emoji_manager import AwardEmojiManager
import robocat.comments

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class ProjectData:
    name: str
    namespace: str
    ssh_url: str
    path: str


class EmptyFollowUpError(RuntimeError):
    pass


class ProjectManager:
    def __init__(self, gitlab_project, current_user, repo):
        self._current_user = current_user
        self._project = Project(gitlab_project)
        self._gitlab = robocat.gitlab.Gitlab(gitlab_project.manager.gitlab)
        self._repo = repo
        self._repo.add_remote(self._project.namespace, self._project.ssh_url)

    @property
    def data(self) -> ProjectData:
        return ProjectData(
            **{f.name: getattr(self._project, f.name) for f in dataclasses.fields(ProjectData)})

    def file_get_content(self, ref: str, file: str) -> str:
        return self._project.get_file_content(ref=ref, file=file)

    def create_follow_up_merge_request(
            self,
            target_branch: str,
            original_mr_manager: MergeRequestManager,
            set_draft_flag: bool) -> MergeRequest:
        commits = original_mr_manager.get_merged_commits()
        assert len(commits) > 0, "No commits for cherry-pick"

        original_mr_data = original_mr_manager.data
        follow_up_mr_source_branch = f"{original_mr_data.source_branch}_{target_branch}"
        source_project = self._gitlab.get_project(
            original_mr_data.source_branch_project_id, lazy=False)
        self._create_new_branch(
            new_branch=follow_up_mr_source_branch,
            base_branch=target_branch,
            project=source_project)

        try:
            cherry_picked_commit_count = self._add_commits_to_branch(
                branch=follow_up_mr_source_branch,
                remote=source_project.namespace,
                commits=commits)
        except EmptyFollowUpError:
            logger.info(
                f"Seems that all the changes from '{original_mr_manager}' are already in branch "
                f"{target_branch}. Follow-up merge request is not created.")
            raise

        try:
            mr = self._create_follow_up_mr_from_branch(
                source_branch=follow_up_mr_source_branch,
                target_branch=target_branch,
                original_mr_data=original_mr_data,
                source_project=source_project,
                commits=commits,
                cherry_picked_commit_count=cherry_picked_commit_count)
        except MergeRequestAlreadyExistsError as e:
            logger.info(f"Failed to create follow-up merge request: {e}")
            original_mr_manager.add_comment(robocat.comments.Message(
                id=MessageId.FollowUpExistsForTheBranch,
                params={"source_branch": e.source_branch, "target_branch": e.target_branch}))
            raise

        if set_draft_flag:
            mr.set_draft_flag()

        return mr

    def get_pipeline(self, pipeline_location: PipelineLocation) -> Pipeline:
        return self._gitlab.get_pipeline(pipeline_location)

    def _create_new_branch(self, new_branch: str, base_branch: str, project: Project):
        logger.debug(
            f"Creating branch {new_branch!r} in {project.namespace!r} ({project.ssh_url!r}) "
            f"from {base_branch!r} in {self._project.namespace!r} ({self._project.ssh_url!r})")
        self._repo.add_remote(project.namespace, project.ssh_url)
        self._repo.create_branch(
            new_branch=new_branch,
            target_remote=project.namespace,
            source_branch=base_branch,
            source_remote=self._project.namespace)

    def _add_commits_to_branch(self, branch: str, remote: str, commits: list[str]) -> int:
        cherry_picked_commit_count = 0
        for sha in commits:
            try:
                # cherry-pick command can fail for two reasons:
                # 1. Conflict with the target branch.
                # 2. Nothing to cherry-pick (incoming changes are already in the target branch).
                #
                # In the first case cherry_pick() throws an exception, because we have to stop the
                # cherry-picking process. In the second case we can proceed, but we must be aware
                # of the fact that no changes were picked, so cherry_pick() returns "False".
                cherry_pick_result = self._repo.cherry_pick(sha=sha, branch=branch, remote=remote)
                if cherry_pick_result:
                    cherry_picked_commit_count += 1
                    self._repo.push_current_branch(remote)
            except GitCommandError as error:
                logger.warning(f"Can't cherry-pick commit {sha} to branch {branch}: {error}")
                return cherry_picked_commit_count

        # No error occurred but nothing was cherry-picked, thus no need to create the follow-up MR.
        if not cherry_picked_commit_count:
            raise EmptyFollowUpError

        return cherry_picked_commit_count

    def _create_follow_up_mr_from_branch(
            self,
            source_branch: str,
            target_branch: str,
            original_mr_data: MergeRequestData,
            source_project: Project,
            commits: list[str],
            cherry_picked_commit_count: int) -> MergeRequest:
        title = re.sub(
            # Issue name in the form "<project_key>-<NNN>", preceded by coma-separated zero or
            # more other Issue names in the same format and followed by the colon (":") symbol
            # (e.g. "VMS-666:" or "INFRA-123, VMS-665, VMS-665:").
            r'^((?:(?:\w+-\d+),\s+)*(?:\w+-\d+):\s+)?',
            rf'\1({original_mr_data.target_branch}->{target_branch}) ',
            original_mr_data.title)
        logger.debug(
            f"Creating MR '{title}' from '{source_branch}' to '{target_branch}'"
            f"(project {source_project.id} => {self._project.id})")

        description = f"{original_mr_data.description}\n\n" if original_mr_data.description else ""
        description += "\n\n".join(f"(cherry-picked from commit {sha})" for sha in commits)

        user_gitlab = self._gitlab.get_gitlab_object_for_user(original_mr_data.author.username)
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
            message=robocat.comments.follow_up_initial_message.format(
                branch=target_branch, original_mr_url=original_mr_data.url),
            emoji=AwardEmojiManager.FOLLOWUP_MERGE_REQUEST_EMOJI,
            revision=automation_tools.bot_info.revision()))

        if cherry_picked_commit_count < len(commits):
            manual_resolution_required_message = robocat.comments.Message(
                id=MessageId.ManualResolutionRequired,
                params={
                    "branch": source_branch,
                    "commits": " ".join(commits[cherry_picked_commit_count:]),
                })
            manual_resolution_required_message_body = robocat.comments.template.format(
                title=manual_resolution_required_message.title,
                message=manual_resolution_required_message.text,
                emoji=AwardEmojiManager.EMOJI_BY_MESSAGE_ID.get(
                    MessageId.ManualResolutionRequired),
                revision=automation_tools.bot_info.revision())

            manual_resolution_required_message_body += str(
                NoteDetails(message_id=MessageId.ManualResolutionRequired, sha=mr.sha))
            # Create a comment thread if there are conflicts with the target branch. If no commits
            # were cherry-picked, resolve them automatically, otherwise leave them unresolved to
            # avoid merging a partially-ready MR.
            mr.create_discussion(
                body=manual_resolution_required_message_body,
                autoresolve=(cherry_picked_commit_count == 0))

        return mr

    def get_merge_request_manager_by_id(self, mr_id) -> MergeRequestManager:
        raw_mr = self._project.get_raw_mr_by_id(mr_id)
        mr = MergeRequest(raw_mr, self._current_user)
        return MergeRequestManager(mr, self._current_user)

    def get_next_open_merge_request(self) -> Generator[MergeRequest, None, None]:
        return self._get_next_merge_request(state='opened')

    def get_next_unfinished_merge_request(self) -> Generator[MergeRequest, None, None]:
        return self._get_next_merge_request(
            my_reaction_emoji=AwardEmojiManager.UNFINISHED_POST_MERGING_EMOJI)

    def _get_next_merge_request(self, **kwargs) -> Generator[MergeRequest, None, None]:
        mrs = self._project.get_raw_mrs(as_list=False, **kwargs)
        for raw_mr in mrs:
            if self._current_user in (assignee["username"] for assignee in raw_mr.assignees):
                yield MergeRequest(raw_mr, self._current_user)

    def get_merged_branches_by_mr_ids(self, mr_ids: set[int]) -> set[str]:
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
