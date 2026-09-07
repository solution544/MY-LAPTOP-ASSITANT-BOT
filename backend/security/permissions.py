"""
Permission system (spec section 30) and confirmation mechanism (section 31).

Every tool declares a PermissionLevel. SENSITIVE and DANGEROUS tools never
execute silently: the orchestrator raises ConfirmationRequired, the API
layer surfaces it to the frontend as a pending confirmation, and the tool
only actually runs after the user explicitly allows it. There is no code
path that lets a DANGEROUS tool execute without this step — enforced in
`backend/tools/registry.py::ToolRegistry.execute`, not left to each tool to
remember.
"""

import uuid
from dataclasses import dataclass
from enum import Enum

from backend.core.config import get_settings


class PermissionLevel(str, Enum):
    SAFE = "SAFE"
    LOW_RISK = "LOW_RISK"
    SENSITIVE = "SENSITIVE"
    DANGEROUS = "DANGEROUS"

@dataclass
class PendingConfirmation:
    id: str
    tool_name: str
    arguments: dict
    description: str
    permission_level: PermissionLevel
    context: dict | None = None

class ConfirmationRequired(Exception):
    """Raised by ToolRegistry.execute() when a tool needs explicit user approval."""

    def __init__(self, pending: PendingConfirmation):
        self.pending = pending
        super().__init__(f"Confirmation required for {pending.tool_name}: {pending.description}")


def requires_confirmation(level: PermissionLevel) -> bool:
    settings = get_settings()
    if settings.confirmation_mode == "strict":
        return level in (PermissionLevel.SENSITIVE, PermissionLevel.DANGEROUS)
    # dangerous_only
    return level == PermissionLevel.DANGEROUS


# In-memory store of confirmations awaiting a decision. A single-user desktop
# app doesn't need this in Postgres — it's transient by nature (either
# answered within the session or the request is abandoned).
_pending: dict[str, PendingConfirmation] = {}


def register_pending(
    tool_name: str,
    arguments: dict,
    description: str,
    level: PermissionLevel,
    context: dict | None = None,
) -> PendingConfirmation:
    pending = PendingConfirmation(
        id=str(uuid.uuid4()),
        tool_name=tool_name,
        arguments=arguments,
        description=description,
        permission_level=level,
        context=context,
    )

    _pending[pending.id] = pending

    return pending


def pop_pending(confirmation_id: str) -> PendingConfirmation | None:
    return _pending.pop(confirmation_id, None)


def get_pending(confirmation_id: str) -> PendingConfirmation | None:
    return _pending.get(confirmation_id)
