"""
Tool introspection + direct execution endpoints.
"""

from fastapi import APIRouter, HTTPException

from backend.security.permissions import (
    ConfirmationRequired,
    get_pending,
    pop_pending,
)
from backend.tools.registry import registry

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("")
def list_tools():
    return registry.list_all()


@router.post("/{tool_name}/execute")
async def execute_tool(
    tool_name: str,
    arguments: dict,
    confirmed: bool = False,
):
    try:
        result = await registry.execute(
            tool_name,
            arguments,
            pre_confirmed=confirmed,
        )
    except ConfirmationRequired as exc:
        return {
            "confirmation_required": True,
            "confirmation_id": exc.pending.id,
            "description": exc.pending.description,
            "permission_level": exc.pending.permission_level.value,
        }

    if result.error_code == "UNKNOWN_TOOL":
        raise HTTPException(
            status_code=404,
            detail=result.error,
        )

    return result.to_dict()


@router.get("/confirmations/{confirmation_id}")
def get_confirmation(confirmation_id: str):
    """
    Get information about a pending confirmation.
    """
    pending = get_pending(confirmation_id)

    if pending is None:
        raise HTTPException(
            status_code=404,
            detail="Confirmation not found or already processed.",
        )

    return {
        "confirmation_id": pending.id,
        "tool_name": pending.tool_name,
        "arguments": pending.arguments,
        "description": pending.description,
        "permission_level": pending.permission_level.value,
    }


@router.post("/confirmations/{confirmation_id}/approve")
async def approve_confirmation(confirmation_id: str):
    """
    Approve and execute a pending confirmation.
    """
    pending = pop_pending(confirmation_id)

    if pending is None:
        raise HTTPException(
            status_code=404,
            detail="Confirmation not found or already processed.",
        )

    try:
        result = await registry.execute(
            pending.tool_name,
            pending.arguments,
            pre_confirmed=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Tool execution failed: {exc}",
        ) from exc

    return {
        "confirmation_approved": True,
        "confirmation_id": confirmation_id,
        "result": result.to_dict(),
    }


@router.post("/confirmations/{confirmation_id}/reject")
def reject_confirmation(confirmation_id: str):
    """
    Reject and remove a pending confirmation.
    """
    pending = pop_pending(confirmation_id)

    if pending is None:
        raise HTTPException(
            status_code=404,
            detail="Confirmation not found or already processed.",
        )

    return {
        "confirmation_rejected": True,
        "confirmation_id": confirmation_id,
        "message": "The requested action was cancelled.",
    }