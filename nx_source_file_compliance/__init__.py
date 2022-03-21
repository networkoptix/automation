from ._source_file_compliance import (
    WordError,
    FileError,
    LineError,
    check_file_content,
    check_text,
    is_check_needed)

from ._generic_repo_check_config import GENERIC_REPO_CONFIG
from ._vms_check_config import VMS_REPO_CONFIG

repo_configurations = {
    "vms": VMS_REPO_CONFIG,
}

__all__ = [
    WordError,
    FileError,
    LineError,
    check_file_content,
    check_text,
    is_check_needed,
    repo_configurations,
    GENERIC_REPO_CONFIG]
