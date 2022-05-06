from dataclasses import dataclass
import logging
import re
from typing import Generator, List, Set

import source_file_compliance
from robocat.merge_request_manager import MergeRequestManager, ApprovalRequirements

logger = logging.getLogger(__name__)


@dataclass
class ApproveRule:
    approvers: List[str]
    patterns: List[str]


# The "keepers" are the users that are responsible for compilance of the open-source part to the
# standards. The keepers are listed in the bot configuration file and it is possible to specify
# the "preferred" keepers for the different files. Any keeper can approve any Merge Request
# requiring such approval, but when assigning the keepers to the Merge Request the bot trys to
# narrow the list of the assigned users and firstly trys to find the prefferred keepers for the
# changed part of the code and assigned only them instead of all the keepers in the list.
def is_mr_author_keeper(
        approve_rules: List[ApproveRule], mr_manager: MergeRequestManager) -> bool:
    keepers = get_keepers(approve_rules=approve_rules, mr_manager=mr_manager)
    return mr_manager.data.author_name in keepers


def get_approval_requirements(
        approve_rules: List[ApproveRule],
        mr_manager: MergeRequestManager) -> ApprovalRequirements:
    keepers = get_keepers(approve_rules=approve_rules, mr_manager=mr_manager)
    logger.debug(f"{mr_manager}: Authorized approvers are {keepers!r}")
    return ApprovalRequirements(authorized_approvers=keepers)


def get_keepers(
        approve_rules: List[ApproveRule],
        mr_manager: MergeRequestManager,
        for_affected_files: bool = False,
        for_changed_files: bool = False) -> Set[str]:
    if not (for_affected_files or for_changed_files):
        return _get_all_open_source_keepers(approve_rules)

    files = list(_affected_open_source_files(mr_manager, include_deleted=for_affected_files))
    return _get_open_source_keepers_for_files(files=files, approve_rules=approve_rules)


def _get_all_open_source_keepers(approve_rules: List[ApproveRule]) -> Set[str]:
    return set(sum([r.approvers for r in approve_rules], []))


def _affected_open_source_files(
        mr_manager: MergeRequestManager,
        include_deleted: bool = True) -> Generator[str, None, None]:

    def is_check_needed(file_path: str):
        return source_file_compliance.is_check_needed(
            path=file_path,
            repo_config=source_file_compliance.repo_configurations["vms"])

    changes = mr_manager.get_changes()
    return (
        c["new_path"] for c in changes.changes
        if (not c["deleted_file"] or include_deleted) and is_check_needed(c["new_path"]))


def _get_open_source_keepers_for_files(
        approve_rules: List[ApproveRule], files: List[str]) -> Set[str]:
    for rule in approve_rules:
        for file_name in files:
            if any([re.match(p, file_name) for p in rule.patterns]):
                logger.debug(f"Preferred approvers found for file {file_name!r}")
                return set(rule.approvers)

    # Return all approvers if we can't determine who is the best match.
    logger.debug("No preferred approvers found, returning complete approver list.")
    return _get_all_open_source_keepers(approve_rules)
