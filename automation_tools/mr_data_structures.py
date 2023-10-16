from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ApprovalsInfo:
    approvals_left: int
    approvals_required: int


@dataclass
class ApprovalRequirements:
    approvals_left: Optional[int] = None
    authorized_approvers: set[str] = field(default_factory=set)
