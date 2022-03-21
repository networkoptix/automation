from dataclasses import dataclass
import logging
import re
from typing import List, Set


logger = logging.getLogger(__name__)


@dataclass
class ApproveRule:
    approvers: List[str]
    patterns: List[str]


def get_all_open_source_keepers(approve_rules: List[ApproveRule]) -> Set[str]:
    return set(sum([r.approvers for r in approve_rules], []))


def get_open_source_keepers_for_files(
        approve_rules: List[ApproveRule], files: List[str]) -> Set[str]:
    for rule in approve_rules:
        for file_name in files:
            if any([re.match(p, file_name) for p in rule.patterns]):
                logger.debug(f"Preferred approvers found for file {file_name!r}")
                return set(rule.approvers)

    # Return all approvers if we can't determine who is the best match.
    logger.debug("No preferred approvers found, returning complete approver list.")
    return get_all_open_source_keepers(approve_rules)
