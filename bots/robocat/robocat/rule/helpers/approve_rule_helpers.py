## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from collections.abc import Callable
from dataclasses import dataclass
import logging
from pathlib import Path
import re
from typing import Generator, TypedDict

import source_file_compliance
from automation_tools.mr_data_structures import ApprovalRequirements
from robocat.merge_request_manager import MergeRequestManager

logger = logging.getLogger(__name__)


class ApproveRuledict(TypedDict):
    approvers: list[str]
    patterns: list[str]


class ApproveRuleset(TypedDict):
    relevance_checker: str
    rules: list[ApproveRuledict]


@dataclass
class ApproveRule:
    approvers: list[str]
    patterns: list[str]
    relevance_checker: "DiffCheckerFunction"


DiffCheckerFunction = Callable[[ApproveRule, dict[str, str]], bool]


# The "keepers" are the users that are responsible for the code in the part of the repo that is
# defined by the specific rule. There are the following rule types for now:
# - "open_source": to ensure the complicance of the open-source part to the standards.
# - "apidoc": to check the changes influencing the API documentation.
# - "code_owner_approval": check for specific parts of the repo by the assigned code owners.
#
# There can be different keepers for different rules. When some of the functions defined in this
# file accepts a list of ApproveRule objects, it means that the keepers defined in all of them are
# are suitable keepers for this rule (i.e. any keeper has a right to approve the MR), but generally
# we are trying to narrow down the list of keepers to the most suitable ones.

def is_mr_author_keeper(
        approve_rules: list[ApproveRule], mr_manager: MergeRequestManager) -> bool:
    keepers = get_keepers(approve_rules=approve_rules, mr_manager=mr_manager)
    return mr_manager.data.author.username in keepers


def get_approval_requirements(
        approve_rules: list[ApproveRule],
        mr_manager: MergeRequestManager) -> ApprovalRequirements:
    keepers = get_keepers(approve_rules=approve_rules, mr_manager=mr_manager)
    logger.debug(f"{mr_manager}: Authorized approvers are {keepers!r}")
    return ApprovalRequirements(authorized_approvers=keepers)


def get_keepers(
        approve_rules: list[ApproveRule],
        mr_manager: MergeRequestManager,
        for_affected_files: bool = False,
        for_changed_files: bool = False) -> set[str]:
    if not (for_affected_files or for_changed_files):
        return _get_all_keepers(approve_rules)

    files = get_all_relevant_files(
        mr_manager=mr_manager, approve_rules=approve_rules, include_deleted=for_affected_files)
    return _get_keepers_for_files(files=files, approve_rules=approve_rules)


def _get_all_keepers(approve_rules: list[ApproveRule]) -> set[str]:
    return set(sum([r.approvers for r in approve_rules], []))


def get_all_relevant_files(
        mr_manager: MergeRequestManager,
        approve_rules: list[ApproveRule],
        include_deleted: bool = True) -> set[str]:
    relevant_files = []
    for rule in approve_rules:
        relevant_files.extend(_relevant_files(mr_manager, rule, include_deleted=include_deleted))
    return set(relevant_files)


def _relevant_files(
        mr_manager: MergeRequestManager,
        approve_rule: ApproveRule,
        include_deleted: bool = True) -> Generator[str, None, None]:

    def is_relevant(item):
        if item["deleted_file"] and not include_deleted:
            return False
        return approve_rule.relevance_checker(approve_rule, item)

    changes = mr_manager.get_changes()
    return (c["new_path"] for c in changes.changes if is_relevant(c))


def _get_keepers_for_files(
        approve_rules: list[ApproveRule], files: set[str]) -> set[str]:
    for rule in approve_rules:
        for file_name in files:
            if any([re.match(p, file_name) for p in rule.patterns]):
                logger.debug(f"Preferred approvers found for file {file_name!r}")
                return set(rule.approvers)

    # Return all approvers if we can't determine who is the best match.
    logger.debug("No preferred approvers found, returning complete approver list.")
    return _get_all_keepers(approve_rules)

# The following three functions are used as relevance checkers for the rules. Not all of them needs
# both parameters, but the signature is the same because the caller function doesn't know which
# parameters are needed for the specific relevance checker.


def is_file_open_sourced(_: ApproveRule, item: dict[str, str]) -> bool:
    # Default RepoCheckConfig can generate some false positives, but using it minimizes issues
    # caused by the implicit dependencies between the bot and the checked repo - the check
    # configuration can be placed in different files, in different branches it can have different
    # formats, etc.
    return source_file_compliance.is_check_needed(
        path=Path(item["new_path"]), repo_config=source_file_compliance.DEFAULT_REPO_CHECK_CONFIG)


def does_file_diff_contain_apidoc_changes(_: ApproveRule, item: dict[str, str]) -> bool:
    return re.search("^\+.+%apidoc", item["diff"], re.MULTILINE)  # noqa W605


def match_name_pattern(rule: ApproveRule, item: dict[str, str]) -> bool:
    return any([re.match(p, item["new_path"]) for p in rule.patterns])
