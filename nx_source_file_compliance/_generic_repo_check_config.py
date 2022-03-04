from typing import TypedDict


class RepoCheckConfig(TypedDict):
    opensource_roots: list
    excluded_dirs: set
    excluded_file_paths: set
    excluded_file_name_patterns: set


GENERIC_REPO_CONFIG = RepoCheckConfig(
    opensource_roots=[],
    excluded_dirs=set(),
    excluded_file_paths=set(),
    excluded_file_name_patterns=set(),
)
