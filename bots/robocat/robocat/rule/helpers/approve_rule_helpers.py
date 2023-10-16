from collections.abc import Callable
from dataclasses import dataclass
import logging
from pathlib import Path
import re
from typing import Dict, Generator, List, Set, TypedDict

import source_file_compliance
from automation_tools.mr_data_structures import ApprovalRequirements
from robocat.merge_request_manager import MergeRequestManager

logger = logging.getLogger(__name__)

DiffCheckerFunction = Callable[[Dict[str, str]], bool]


class ApproveRuleDict(TypedDict):
    approvers: List[str]
    patterns: List[str]


class ApproveRuleset(TypedDict):
    relevance_checker: str
    rules: List[ApproveRuleDict]


@dataclass
class ApproveRule:
    approvers: List[str]
    patterns: List[str]
    relevance_checker: DiffCheckerFunction


# The "keepers" are the users that are responsible for compliance of the open-source part to the
# standards. The keepers are listed in the bot configuration file and it is possible to specify
# the "preferred" keepers for the different files. Any keeper can approve any Merge Request
# requiring such approval, but when assigning the keepers to the Merge Request the bot tries to
# narrow the list of the assigned users - it firstly searches for the preferred keepers for the
# changed part of the code and assigns only them instead of all the keepers in the list.
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
        return _get_all_keepers(approve_rules)

    files = set()
    for approve_rule in approve_rules:
        files.update(
            set(_relevant_files(mr_manager, approve_rule, include_deleted=for_affected_files)))
    return _get_keepers_for_files(files=files, approve_rules=approve_rules)


def _get_all_keepers(approve_rules: List[ApproveRule]) -> Set[str]:
    return set(sum([r.approvers for r in approve_rules], []))


def _relevant_files(
        mr_manager: MergeRequestManager,
        approve_rule: ApproveRule,
        include_deleted: bool = True) -> Generator[str, None, None]:

    def is_relevant(item):
        if item["deleted_file"] and not include_deleted:
            return False
        return approve_rule.relevance_checker(item)

    changes = mr_manager.get_changes()
    return (c["new_path"] for c in changes.changes if is_relevant(c))


def _get_keepers_for_files(
        approve_rules: List[ApproveRule], files: Set[str]) -> Set[str]:
    for rule in approve_rules:
        for file_name in files:
            if any([re.match(p, file_name) for p in rule.patterns]):
                logger.debug(f"Preferred approvers found for file {file_name!r}")
                return set(rule.approvers)

    # Return all approvers if we can't determine who is the best match.
    logger.debug("No preferred approvers found, returning complete approver list.")
    return _get_all_keepers(approve_rules)


def is_file_open_sourced(item: Dict[str, str]) -> bool:
    # Default RepoCheckConfig can generate some false positives, but using it minimizes issues
    # caused by the implicit dependencies between the bot and the checked repo - the check
    # configuration can be placed in different files, in different branches it can have different
    # formats, etc.
    return source_file_compliance.is_check_needed(
        path=Path(item["new_path"]), repo_config=source_file_compliance.DEFAULT_REPO_CHECK_CONFIG)


def does_file_diff_contain_apidoc_changes(item: Dict[str, str]) -> bool:
    return re.search("^\+.+%apidoc", item["diff"], re.MULTILINE)  # noqa W605
