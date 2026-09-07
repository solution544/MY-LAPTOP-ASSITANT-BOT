
import traceback
import uuid
from datetime import datetime
from typing import Literal, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.ai.base import ChatMessage
from backend.ai.provider_factory import get_ai_provider
from backend.agents.orchestrator import AgentOrchestrator
from backend.core.logging import logger
from backend.database.models import Conversation, Message, User
from backend.database.session import get_db
from backend.schemas.chat import ChatRequest, ChatResponse
from backend.security.permissions import (
    get_pending,
    pop_pending,
)
from backend.tools.registry import registry


router = APIRouter(
    prefix="/api/chat",
    tags=["chat"],
)


# ==============================================================
# CONFIRMATION REQUEST
# ==============================================================

class ChatConfirmationRequest(BaseModel):
    confirmation_id: str
    approved: bool


# ==============================================================
# USER
# ==============================================================

def _get_or_create_default_user(db: Session) -> User:
    """
    Get the first user in the database.

    If no user exists, create a default user.
    """

    user = db.query(User).first()

    if user is None:
        user = User(
            id=str(uuid.uuid4()),
            name="User",
        )

        db.add(user)
        db.commit()
        db.refresh(user)

    return user


# ==============================================================
# LOAD CONVERSATION HISTORY
# ==============================================================

def _load_history(
    db: Session,
    conversation_id: str,
) -> list[ChatMessage]:
    """
    Load normal conversation history for the AI agent.
    """

    history = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation_id
        )
        .order_by(Message.created_at)
        .all()
    )

    chat_messages: list[ChatMessage] = []

    for message in history:

        if message.role not in (
            "user",
            "assistant",
        ):
            continue

        chat_messages.append(
            ChatMessage(
                role=cast(
                    Literal[
                        "user",
                        "assistant",
                        "system",
                        "tool",
                    ],
                    message.role,
                ),
                content=cast(
                    str,
                    message.content,
                ),
            )
        )

    return chat_messages


# ==============================================================
# RUN AGENT
# ==============================================================

async def _run_agent(
    request_message: str,
    history: list[ChatMessage],
):
    """
    Create and run the Solution AI agent.
    """

    provider = get_ai_provider()

    orchestrator = AgentOrchestrator(
        provider=provider,
        tools=registry,
    )

    result = await orchestrator.run(
        user_message=request_message,
        history=history,
    )

    return provider, orchestrator, result


# ==============================================================
# CHAT
# ==============================================================

@router.post(
    "",
    response_model=ChatResponse,
)
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
):
    """
    Main Solution AI chat endpoint.
    """

    # ----------------------------------------------------------
    # USER
    # ----------------------------------------------------------

    user = _get_or_create_default_user(db)

    # ----------------------------------------------------------
    # CONVERSATION
    # ----------------------------------------------------------

    if request.conversation_id:

        conversation = db.get(
            Conversation,
            request.conversation_id,
        )

        if conversation is None:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found",
            )

    else:

        conversation = Conversation(
            id=str(uuid.uuid4()),
            user_id=user.id,
            title=None,
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    conversation_id = cast(
        str,
        conversation.id,
    )

    # ----------------------------------------------------------
    # SAVE USER MESSAGE
    # ----------------------------------------------------------

    user_message = Message(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role="user",
        content=request.message,
    )

    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    # ----------------------------------------------------------
    # LOAD HISTORY
    # ----------------------------------------------------------

    chat_messages = _load_history(
        db,
        conversation_id,
    )

    # The newest user message is passed separately.
    history = chat_messages[:-1]

    # ----------------------------------------------------------
    # RUN AI AGENT
    # ----------------------------------------------------------

    try:

        provider, orchestrator, result = await _run_agent(
            request_message=request.message,
            history=history,
        )

    except Exception as exc:

        logger.exception(
            "Agent execution failed"
        )

        print(
            "\n========== SOLUTION AI ERROR =========="
        )
        print(
            f"ERROR: {exc}"
        )
        traceback.print_exc()
        print(
            "=======================================\n"
        )

        raise HTTPException(
            status_code=502,
            detail=f"AI agent error: {exc}",
        ) from exc

    # ----------------------------------------------------------
    # CONFIRMATION REQUIRED
    # ----------------------------------------------------------

    if result.pending_confirmation is not None:

        confirmation = (
            result.pending_confirmation
        )

        # IMPORTANT:
        # Preserve the context created by AgentOrchestrator.
        #
        # The orchestrator already stores:
        # - source
        # - tool_call_id
        # - paused_messages
        #
        # We only ADD the conversation ID here.

        existing_context = (
            confirmation.context or {}
        )

        confirmation.context = {
            **existing_context,
            "source": "chat_api",
            "conversation_id": conversation_id,
        }

        confirmation_text = (
            "I need your confirmation before I can run "
            f"'{confirmation.tool_name}'.\n\n"
            f"{confirmation.description}"
        )

        assistant_message = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            role="assistant",
            content=confirmation_text,
            model=getattr(
                provider,
                "_model",
                None,
            ),
        )

        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)

        return ChatResponse(
            conversation_id=conversation_id,
            message_id=cast(
                str,
                assistant_message.id,
            ),
            role="assistant",
            content=confirmation_text,
            created_at=cast(
                datetime,
                assistant_message.created_at,
            ),
            confirmation_required=True,
            confirmation_id=confirmation.id,
            tool_name=confirmation.tool_name,
            description=confirmation.description,
            permission_level=(
                confirmation.permission_level.value
            ),
        )

    # ----------------------------------------------------------
    # FINAL RESPONSE
    # ----------------------------------------------------------

    final_text = result.final_text or (
        "I completed the request, but I don't have "
        "a final response to provide."
    )

    # ----------------------------------------------------------
    # SAVE ASSISTANT MESSAGE
    # ----------------------------------------------------------

    assistant_message = Message(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role="assistant",
        content=final_text,
        model=getattr(
            provider,
            "_model",
            None,
        ),
    )

    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    # ----------------------------------------------------------
    # RETURN
    # ----------------------------------------------------------

    return ChatResponse(
        conversation_id=conversation_id,
        message_id=cast(
            str,
            assistant_message.id,
        ),
        role="assistant",
        content=cast(
            str,
            assistant_message.content,
        ),
        created_at=cast(
            datetime,
            assistant_message.created_at,
        ),
    )


# ==============================================================
# CHAT CONFIRMATION
# ==============================================================

@router.post("/confirm")
async def confirm_chat(
    request: ChatConfirmationRequest,
    db: Session = Depends(get_db),
):
    """
    Approve or reject a confirmation generated by /api/chat.
    """

    confirmation_id = request.confirmation_id
    approved = request.approved

    # ----------------------------------------------------------
    # FIND PENDING CONFIRMATION
    # ----------------------------------------------------------

    pending = get_pending(
        confirmation_id
    )

    if pending is None:

        raise HTTPException(
            status_code=404,
            detail="Confirmation expired or unknown.",
        )

    # ----------------------------------------------------------
    # VERIFY SOURCE
    # ----------------------------------------------------------

    context = pending.context or {}

    if context.get("source") != "chat_api":

        raise HTTPException(
            status_code=403,
            detail=(
                "This confirmation does not belong "
                "to the chat API."
            ),
        )

    # ----------------------------------------------------------
    # CONVERSATION
    # ----------------------------------------------------------

    conversation_id = context.get(
        "conversation_id"
    )

    if not conversation_id:

        raise HTTPException(
            status_code=400,
            detail="Confirmation has no conversation.",
        )

    conversation = db.get(
        Conversation,
        conversation_id,
    )

    if conversation is None:

        raise HTTPException(
            status_code=404,
            detail="Conversation not found.",
        )

    # ----------------------------------------------------------
    # REMOVE PENDING CONFIRMATION
    # ----------------------------------------------------------

    pending = pop_pending(
        confirmation_id
    )

    if pending is None:

        raise HTTPException(
            status_code=404,
            detail=(
                "Confirmation expired or "
                "already processed."
            ),
        )

    # ----------------------------------------------------------
    # RESTORE PAUSED AGENT HISTORY
    # ----------------------------------------------------------

    paused_messages = (
        pending.context or {}
    ).get(
        "paused_messages"
    )

    if isinstance(
        paused_messages,
        list,
    ):

        history = paused_messages

    else:

        history = []

    # ----------------------------------------------------------
    # RUN CONFIRMATION
    # ----------------------------------------------------------

    try:

        provider = get_ai_provider()

        orchestrator = AgentOrchestrator(
            provider=provider,
            tools=registry,
        )

        result = (
            await orchestrator.continue_after_confirmation(
                pending=pending,
                approved=approved,
                history=history,
            )
        )

    except Exception as exc:

        logger.exception(
            "Confirmation continuation failed"
        )

        print(
            "\n========== SOLUTION AI CONFIRMATION ERROR =========="
        )
        print(
            f"ERROR: {exc}"
        )
        traceback.print_exc()
        print(
            "=====================================================\n"
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Confirmation execution failed: "
                f"{exc}"
            ),
        ) from exc

    # ----------------------------------------------------------
    # FINAL RESPONSE
    # ----------------------------------------------------------

    if not approved:

        final_text = (
            "Okay. I cancelled the action."
        )

    else:

        final_text = result.final_text or (
            "Confirmed. The action has been completed."
        )

    # ----------------------------------------------------------
    # SAVE ASSISTANT RESPONSE
    # ----------------------------------------------------------

    assistant_message = Message(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role="assistant",
        content=final_text,
        model=getattr(
            provider,
            "_model",
            None,
        ),
    )

    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    # ----------------------------------------------------------
    # RETURN
    # ----------------------------------------------------------

    return {
        "success": True,
        "conversation_id": conversation_id,
        "message_id": cast(
            str,
            assistant_message.id,
        ),
        "role": "assistant",
        "content": final_text,
        "confirmation_required": False,
        "confirmation_id": confirmation_id,
        "approved": approved,
        "created_at": cast(
            datetime,
            assistant_message.created_at,
        ).isoformat(),
    }
