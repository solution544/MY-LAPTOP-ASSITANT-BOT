"""
Unit tests for the permission/confirmation system — these run without a
database, an API key, or a display, since they test pure logic.
"""

import pytest

from backend.security.permissions import (
    ConfirmationRequired, PermissionLevel, get_pending, pop_pending,
    register_pending, requires_confirmation,
)


def test_safe_never_requires_confirmation():
    assert requires_confirmation(PermissionLevel.SAFE) is False


def test_dangerous_always_requires_confirmation():
    assert requires_confirmation(PermissionLevel.DANGEROUS) is True


def test_pending_confirmation_roundtrip():
    pending = register_pending("test.tool", {"a": 1}, "do a thing", PermissionLevel.SENSITIVE)
    assert get_pending(pending.id) is pending
    popped = pop_pending(pending.id)
    assert popped is pending
    assert get_pending(pending.id) is None


@pytest.mark.asyncio
async def test_registry_raises_confirmation_required_for_dangerous_tool():
    from backend.tools.base import Tool, ToolResult
    from backend.tools.registry import ToolRegistry

    class DangerousTestTool(Tool):
        name = "test.dangerous"
        description = "test"
        input_schema = {"type": "object", "properties": {}}
        permission_level = PermissionLevel.DANGEROUS

        async def execute(self, **kwargs) -> ToolResult:
            return ToolResult(success=True, data="ran")

    reg = ToolRegistry()
    reg.register(DangerousTestTool())

    with pytest.raises(ConfirmationRequired):
        await reg.execute("test.dangerous", {})

    # pre_confirmed=True bypasses the check, as the orchestrator does after approval
    result = await reg.execute("test.dangerous", {}, pre_confirmed=True)
    assert result.success is True
