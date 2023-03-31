import json
from pathlib import Path
from typing import List, NamedTuple


class RepoCheckConfig(NamedTuple):
    opensource_roots: List[Path]
    excluded_dirs: List[Path]
    excluded_file_paths: List[Path]
    excluded_file_name_patterns: List[str]

    @classmethod
    def load(cls, file_name: Path) -> 'RepoCheckConfig':
        config = {}
        with open(file_name, 'r') as f:
            config = json.load(f)

        def _extract_and_check_list_of_string(key: str) -> List[str]:
            value = config.get(key, [])
            if not isinstance(value, list) or any(e for e in value if not isinstance(e, str)):
                raise RuntimeError(
                    f"Configuration error: '{key}' should be a list of strings (configuration "
                    f"file '{file_name}')")
            return value

        opensource_roots = [Path(p) for p in _extract_and_check_list_of_string('opensource_roots')]
        excluded_dirs = [Path(p) for p in _extract_and_check_list_of_string('excluded_dirs')]
        excluded_file_paths = [
            Path(p) for p in _extract_and_check_list_of_string('excluded_file_paths')]
        excluded_file_name_patterns = _extract_and_check_list_of_string(
            'excluded_file_name_patterns')

        return cls(
            opensource_roots, excluded_dirs, excluded_file_paths, excluded_file_name_patterns)
