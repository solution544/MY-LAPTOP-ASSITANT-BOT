"""
Every tool in Solution AI — computer control, filesystem, web, terminal,
memory, system — implements this same `Tool` interface, so the
`ToolRegistry` and `AgentOrchestrator` never need special cases per tool.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from backend.security.permissions import PermissionLevel


@dataclass
class ToolResult:
    """
    Every tool returns this shape (spec section 33: structured results,
    never a raw exception that could crash the assistant).
    """
    success: bool
    data: Any = None
    error: str | None = None
    error_code: str | None = None

    def to_dict(self) -> dict:
        return {"success": self.success, "data": self.data, "error": self.error, "error_code": self.error_code}


class Tool(ABC):
    name: str
    description: str
    input_schema: dict  # JSON Schema
    permission_level: PermissionLevel

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        raise NotImplementedError

    def confirmation_description(self, **kwargs) -> str:
        """Human-readable summary shown in the confirmation dialog (spec section 31)."""
        return f"{self.name}({kwargs})"
