## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

import dataclasses
import logging
from operator import is_
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Optional

import git
from robocat.project_manager import ProjectManager
from robocat.rule.helpers.stateful_checker_helpers import CheckError

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class NxSubmoduleConfig:
    subrepo_url: str
    subrepo_dir: str
    commit_sha: str
    git_ref: str = ""


class GetSubrepoError(RuntimeError):
    def __init__(self, error: CheckError):
        self.__super__(str(CheckError))
        self.check_error = error


class NxSubmoduleChecker:
    CONFIG_FILE_NAME = "_nx_submodule"

    CONFIG_MALFORMED_ERROR = "nx_submodule_config_malformed"
    CONFIG_DELETED_ERROR = "nx_submodule_config_deleted"
    CONFIG_BAD_GIT_DATA = "nx_submodule_bad_url_or_commit_sha"
    INCONSISTENT_CONTENT = "inconsistent_nx_submodule_change"

    def __init__(self, submodule_dirs: List[str], project_manager: ProjectManager, sha: str):
        self._submodule_dirs = submodule_dirs
        self._project_manager = project_manager
        self._sha = sha
        self._nx_submodules_repo_dirs = {}
        self._nx_submodule_configs = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.clean_up()

    def clean_up(self):
        for tmp_dir in self._nx_submodules_repo_dirs.values():
            tmp_dir.cleanup()
        self._nx_submodules_repo_dirs = {}

    def find_error(
            self, file_name: str, is_executable: bool, is_deleted: bool) -> Optional[CheckError]:
        nx_submodule_dir = self._get_nx_submodule_by_file_name(file_name)
        if not nx_submodule_dir:
            return None

        config_file_name = f"{nx_submodule_dir}/{self.CONFIG_FILE_NAME}"
        if file_name == config_file_name and is_deleted:
            return CheckError(
                type=self.CONFIG_DELETED_ERROR,
                params={"nx_submodule_dir": nx_submodule_dir})

        if config_error := self._load_nx_submodule_config_returning_error(nx_submodule_dir):
            return config_error

        if subrepo_error := self._load_subrepo_returning_error(nx_submodule_dir):
            return subrepo_error

        # Stop checks here if the changed file is a submodule config file.
        if file_name == config_file_name:
            return None

        return self._check_file_consistency(
            file_name=file_name,
            is_executable=is_executable,
            is_deleted=is_deleted)

    def _get_nx_submodule_by_file_name(self, file_name: str) -> Optional[str]:
        nx_submodule_dirs = [d for d in self._submodule_dirs if file_name.startswith(f"{d}/")]
        return nx_submodule_dirs[0] if nx_submodule_dirs else None

    def _load_nx_submodule_config_returning_error(
            self, nx_submodule_dir: str) -> Optional[CheckError]:
        if nx_submodule_dir in self._nx_submodule_configs:
            return None

        config_file_name = f"{nx_submodule_dir}/{self.CONFIG_FILE_NAME}"
        file_content = self._project_manager.file_get_content(ref=self._sha, file=config_file_name)

        config_data = {}
        for line in file_content.split("\n"):
            if line.startswith("#") or not line.strip():
                continue
            file_key, _, value = line.partition("=")
            object_key = file_key.strip().replace("-", "_")
            config_data[object_key] = value.strip()

        try:
            self._nx_submodule_configs[nx_submodule_dir] = NxSubmoduleConfig(**config_data)
        except TypeError as err:
            logger.debug(f"Nx submodule config file {config_file_name!r} has wrong format: {err}")
            return CheckError(
                type=self.CONFIG_MALFORMED_ERROR,
                params={"nx_submodule_dir": nx_submodule_dir})

        return None

    def _load_subrepo_returning_error(self, nx_submodule_dir: str) -> Optional[CheckError]:
        nx_submodule_config = self._nx_submodule_configs[nx_submodule_dir]
        subrepo_dir = Path(self._nx_submodules_repo_dirs.setdefault(
            nx_submodule_dir,
            TemporaryDirectory(prefix="subrepo-dir-")).name)

        try:
            if next(subrepo_dir.iterdir(), None):  # Check if subrepo is already cloned.
                subrepo = git.Repo(str(subrepo_dir))
            else:
                subrepo = git.Repo.clone_from(
                    url=nx_submodule_config.subrepo_url,
                    to_path=str(subrepo_dir))

            subrepo.git.clean("-df")
            subrepo.head.reset(
                commit=nx_submodule_config.commit_sha,
                index=True, working_tree=True)
        except git.exc.GitCommandError as err:
            return CheckError(
                type=self.CONFIG_BAD_GIT_DATA,
                params={
                    "nx_submodule_dir": nx_submodule_dir,
                    "subrepo_url": nx_submodule_config.subrepo_url,
                    "subrepo_commit_sha": nx_submodule_config.commit_sha,
                    "explanation": str(err),
                })

        if not (subrepo_dir / nx_submodule_config.subrepo_dir).is_dir():
            return CheckError(
                type=self.CONFIG_BAD_GIT_DATA,
                params={
                    "nx_submodule_dir": nx_submodule_dir,
                    "subrepo_url": nx_submodule_config.subrepo_url,
                    "subrepo_dir": nx_submodule_config.subrepo_dir,
                    "subrepo_commit_sha": nx_submodule_config.commit_sha,
                    "explanation": "No such directory in subrepo",
                })

        return None

    def _check_file_consistency(
            self, file_name: str, is_executable: bool, is_deleted: bool) -> Optional[CheckError]:
        def _inconsistency_error(explanation):
            return CheckError(
                type=self.INCONSISTENT_CONTENT,
                params={
                    "nx_submodule_dir": nx_submodule_dir,
                    "subrepo_url": nx_submodule_config.subrepo_url,
                    "subrepo_dir": nx_submodule_config.subrepo_dir,
                    "subrepo_commit_sha": nx_submodule_config.commit_sha,
                    "explanation": explanation,
                })

        nx_submodule_dir = self._get_nx_submodule_by_file_name(file_name)
        subrepo_dir = Path(self._nx_submodules_repo_dirs[nx_submodule_dir].name)
        nx_submodule_config = self._nx_submodule_configs[nx_submodule_dir]

        relative_file_name = file_name[len(nx_submodule_dir) + 1:]
        subrepo_file = subrepo_dir / nx_submodule_config.subrepo_dir / relative_file_name

        if not subrepo_file.is_file():
            if is_deleted:
                return None
            return _inconsistency_error(f"File {relative_file_name!r} is not found in subrepo")

        if is_deleted:
            return _inconsistency_error(
                f"File {relative_file_name!r} is deleted by found in subrepo")

        # Check executable flags.
        if is_executable != bool(subrepo_file.stat().st_mode & 0o111):
            return _inconsistency_error(
                f"File {relative_file_name!r} has wrong executable flag '{is_executable}'")

        changed_file_content = self._project_manager.file_get_content(
            ref=self._sha, file=file_name)
        with open(subrepo_file, 'r') as f:
            subrepo_file_content = f.read()

        if changed_file_content != subrepo_file_content:
            return _inconsistency_error(
                f"File {relative_file_name!r} differs from its counterpart")

        return None
