from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.laptop_manager import laptop_manager
from backend.security.permissions import (
    PendingConfirmation,
    get_pending,
    pop_pending,
    register_pending,
    requires_confirmation,
)
from backend.tools.registry import registry


router = APIRouter(
    prefix="/api/laptop",
    tags=["Laptop Commands"],
)


class LaptopCommandRequest(BaseModel):
    device_id: str
    command: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class LaptopConfirmationRequest(BaseModel):
    confirmation_id: str
    approved: bool


@router.post("/command")
async def send_laptop_command(request: LaptopCommandRequest):
    """
    Send a command to a connected Solution AI laptop.

    Sensitive and dangerous commands require explicit
    confirmation before being sent to the laptop agent.
    """

    laptop = await laptop_manager.get(request.device_id)

    if laptop is None:
        raise HTTPException(
            status_code=404,
            detail="Laptop is not connected.",
        )

    allowed_commands = {
        "computer.get_screen_size",
        "computer.open_application",
        "computer.type_text",
    }

    if request.command not in allowed_commands:
        raise HTTPException(
            status_code=403,
            detail="This command is not enabled yet.",
        )

    tool = registry.get(request.command)

    if tool is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{request.command}' is not registered.",
        )

    # ---------------------------------------------------------
    # CONFIRMATION CHECK
    # ---------------------------------------------------------

    if requires_confirmation(tool.permission_level):

        description = tool.confirmation_description(
            **request.arguments
        )

        pending = register_pending(
            tool_name=request.command,
            arguments=request.arguments,
            description=description,
            level=tool.permission_level,
            context={
                "device_id": request.device_id,
                "source": "laptop_api",
            },
        )

        return {
            "success": False,
            "confirmation_required": True,
            "confirmation_id": pending.id,
            "device_id": request.device_id,
            "command": request.command,
            "description": pending.description,
            "permission_level": pending.permission_level.value,
            "status": "awaiting_confirmation",
        }

    # ---------------------------------------------------------
    # SAFE COMMAND
    # ---------------------------------------------------------

    command_id = await laptop_manager.send_command(
        device_id=request.device_id,
        command=request.command,
        arguments=request.arguments,
    )

    return {
        "success": True,
        "confirmation_required": False,
        "command_id": command_id,
        "device_id": request.device_id,
        "command": request.command,
        "status": "sent",
    }


@router.post("/confirm")
async def confirm_laptop_command(
    request: LaptopConfirmationRequest,
):
    """
    Approve or reject a pending laptop command.
    """

    pending = get_pending(
        request.confirmation_id
    )

    if pending is None:
        raise HTTPException(
            status_code=404,
            detail="Confirmation expired or unknown.",
        )

    # Remove it immediately so the same confirmation
    # cannot be used twice.
    pop_pending(request.confirmation_id)

    context = pending.context or {}

    if context.get("source") != "laptop_api":
        raise HTTPException(
            status_code=400,
            detail="This confirmation does not belong to a laptop command.",
        )

    device_id = context.get("device_id")

    if not device_id:
        raise HTTPException(
            status_code=400,
            detail="Laptop device ID is missing from confirmation.",
        )

    laptop = await laptop_manager.get(device_id)

    if laptop is None:
        raise HTTPException(
            status_code=404,
            detail="Laptop is no longer connected.",
        )

    # ---------------------------------------------------------
    # USER REJECTED
    # ---------------------------------------------------------

    if not request.approved:
        return {
            "success": False,
            "confirmation_required": False,
            "confirmation_id": request.confirmation_id,
            "device_id": device_id,
            "command": pending.tool_name,
            "status": "rejected",
        }

    # ---------------------------------------------------------
    # USER APPROVED
    # ---------------------------------------------------------

    command_id = await laptop_manager.send_command(
    device_id=device_id,
    command=pending.tool_name,
    arguments=pending.arguments,
)

    return {
        "success": True,
        "confirmation_required": False,
        "confirmation_id": request.confirmation_id,
        "command_id": command_id,
        "device_id": device_id,
        "command": pending.tool_name,
        "status": "sent",
    }