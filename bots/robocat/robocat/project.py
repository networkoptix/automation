import logging
import json
from functools import lru_cache
from typing import List, Dict
from dataclasses import dataclass
from gitlab import Gitlab

logger = logging.getLogger(__name__)


@dataclass
class MergeRequestDiffData:
    overflow: bool
    changes: List[Dict]


class Project:
    def __init__(self, gitlab_project):
        self._gitlab_project = gitlab_project

    def __eq__(self, other):
        return self._gitlab_project.id == other._gitlab_project.id

    def __hash__(self):
        return int(self._gitlab_project.id)

    @lru_cache(maxsize=64)
    def get_file_content(self, sha: str, file: str) -> str:
        logger.debug(f"Getting file content: {sha}, {file}")
        file_handler = self._gitlab_project.files.get(file_path=file, ref=sha)
        return file_handler.decode().decode('utf-8')

    @lru_cache(maxsize=64)
    def get_mr_commit_changes(
            self, mr_id: int,
            mr_target_branch: str, sha: str) -> MergeRequestDiffData:  # pylint: disable=unused-argument
        # "sha" and "mr_target_branch" arguments are used by the lru_cache magic.
        changes = self._gitlab_project.mergerequests.get(mr_id).changes()
        overflow = str(changes["changes_count"]).endswith("+")
        return MergeRequestDiffData(changes=changes["changes"], overflow=overflow)

    @lru_cache(maxsize=512)
    def get_commit_message(self, sha):
        return self._gitlab_project.commits.get(sha).message

    @lru_cache(maxsize=512)
    def get_commit_diff_hash(self, sha):
        diff = self._gitlab_project.commits.get(sha).diff()
        return hash(json.dumps(diff, sort_keys=True))

    @lru_cache(maxsize=512)
    def get_user_ids(self, username: str) -> List[int]:
        user_ids = [user.id for user in self._gitlab_project.users.list(search=username)]
        if not user_ids:
            logger.warning(f"Can't find user id for user {username}.")
        return user_ids

    def get_raw_mrs(self, **kwargs):
        return self._gitlab_project.mergerequests.list(order_by='updated_at', **kwargs)

    def get_raw_mr_by_id(self, mr_id: int):
        return self._gitlab_project.mergerequests.get(mr_id)

    @property
    def name(self):
        return self._gitlab_project.name

    def cherry_pick_to_branch(self, branch, commit_sha):
        commit = self._get_raw_commit_by_sha(commit_sha)
        commit.cherry_pick(branch=branch)

    def _get_raw_commit_by_sha(self, sha):
        return self._gitlab_project.commits.get(sha)

    def create_branch(self, branch: str, from_branch: str):
        return self._gitlab_project.branches.create({"branch": branch, "ref": from_branch})

    def create_merge_request(
            self, source_branch: str,
            target_branch: str,
            title: str,
            description: str,
            squash: bool,
            author: str):

        bot_gitlab = self._gitlab_project.manager.gitlab
        assignee_ids = [bot_gitlab.user.id]

        try:
            effective_user = bot_gitlab.users.list(search=author)[0]
        except IndexError as e:
            raise RuntimeError(f"Invalid username: {author}") from e

        impersonation_token = effective_user.impersonationtokens.create(
            {"name": author, "scopes": ["api"]}, lazy=True)
        user_gitlab = Gitlab(bot_gitlab.url, private_token=impersonation_token.token)
        user_gitlab.auth()  # Needed to initialize "user" field of the user_gitlab object.
        assignee_ids.append(user_gitlab.user.id)
        raw_project = user_gitlab.projects.get(self._gitlab_project.id, lazy=True)

        raw_mr = raw_project.mergerequests.create({
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": description,
            "squash": squash,
            "remove_source_branch": True,
            "assignee_ids": assignee_ids})

        impersonation_token.delete()
        # Return "bot owned" merge request, not "user owned".
        return self._gitlab_project.mergerequests.get(raw_mr.iid)
