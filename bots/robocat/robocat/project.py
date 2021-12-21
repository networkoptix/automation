import logging
import json
from functools import lru_cache
from typing import List, Dict, Optional
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MergeRequestDiffData:
    overflow: bool
    changes: List[Dict]


class Project:
    DIFF_LINE_NUMBER_REMOVER_RE = re.compile(r'^^\@\@ -\d+,\d+ \+\d+,\d+ \@\@\s+', re.MULTILINE)

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
        # TODO: Need some check what file we are trying to read. If it is a binary file, don't try
        # to decode it. If it is a text file and it doesn't contain valid utf8 data, log this fact
        # and do some workaround.
        try:
            return file_handler.decode().decode('utf-8')
        except UnicodeDecodeError:
            return file_handler.decode().decode('latin1')

    @lru_cache(maxsize=64)
    def get_mr_commit_changes(
            self, mr_id: int,
            mr_target_branch: str, sha: str) -> MergeRequestDiffData:
        # "sha" and "mr_target_branch" arguments are used by the lru_cache magic.
        changes = self._gitlab_project.mergerequests.get(mr_id).changes()
        overflow = str(changes["changes_count"]).endswith("+")
        return MergeRequestDiffData(changes=changes["changes"], overflow=overflow)

    @lru_cache(maxsize=512)
    def get_commit_message(self, sha):
        return self._gitlab_project.commits.get(sha).message

    @lru_cache(maxsize=512)
    def get_commit_diff_hash(self, sha: str, include_line_numbers: bool = True) -> int:
        diff = self._gitlab_project.commits.get(sha).diff()
        if not include_line_numbers:
            for d in diff:
                d["diff"] = re.sub(self.DIFF_LINE_NUMBER_REMOVER_RE, "", d["diff"])
        return hash(json.dumps(diff, sort_keys=True))

    @lru_cache(maxsize=512)
    def get_user_ids(self, username: str) -> List[int]:
        user_ids = [user.id for user in self._gitlab_project.users.list(search=username)]
        if not user_ids:
            logger.warning(f"Can't find user id for user {username}.")
        return user_ids

    @property
    def id(self) -> int:
        return int(self._gitlab_project.id)

    def get_raw_mrs(self, **kwargs):
        return self._gitlab_project.mergerequests.list(order_by='updated_at', **kwargs)

    def get_raw_mr_by_id(self, mr_id: int, include_diverged_commits_count=False):
        return self._gitlab_project.mergerequests.get(
            mr_id,
            include_diverged_commits_count=include_diverged_commits_count)

    @property
    def name(self):
        return self._gitlab_project.name

    @property
    def namespace(self):
        return self._gitlab_project.namespace["full_path"]

    @property
    def ssh_url(self):
        return self._gitlab_project.ssh_url_to_repo

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
            assignee_ids: List[int],
            target_project_id: Optional[int] = None) -> int:

        target_project_id = self.id if target_project_id is None else target_project_id

        raw_mr = self._gitlab_project.mergerequests.create({
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": description,
            "squash": squash,
            "remove_source_branch": True,
            "target_project_id": target_project_id,
            "assignee_ids": list(set(assignee_ids))})
        return raw_mr.iid
