## Copyright 2018-present Network Optix, Inc. Licensed under MPL 2.0: www.mozilla.org/MPL/2.0/

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ApprovalsInfo:
    is_approved: bool
    approvals_left: int
    approvals_required: int


@dataclass
class ApprovalRequirements:
    approvals_left: Optional[int] = None
    authorized_approvers: set[str] = field(default_factory=set)
