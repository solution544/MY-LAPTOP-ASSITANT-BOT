"""
WS /ws/assistant — realtime event stream to the UI, now running through the
full AgentOrchestrator (tool calling + confirmation flow) instead of a bare
chat() call.

Event names match spec section 39 (assistant.started, assistant.listening,
assistant.thinking, assistant.tool_started, assistant.tool_completed,
assistant.speaking, assistant.completed, assistant.error), plus one addition
not in the original list but required by the confirmation system (section
31): assistant.confirmation_required. The frontend shows a confirmation
dialog on this event and replies with {"confirmation_id": ..., "approved": bool}.
"""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from backend.agents.orchestrator import AgentOrchestrator
from backend.ai.base import ChatMessage
from backend.ai.provider_factory import get_ai_provider
from backend.core.logging import logger
from backend.database.models import Conversation, Message, User
from backend.database.session import SessionLocal
from backend.security.permissions import get_pending, pop_pending
from backend.tools.registry import registry

router = APIRouter()


async def _emit(ws: WebSocket, event: str, **payload):
    await ws.send_text(json.dumps({
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload,
    }))


def _get_or_create_default_user(db: Session) -> User:
    user = db.query(User).first()
    if user is None:
        user = User(id=str(uuid.uuid4()), name="User")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _load_history(db: Session, conversation_id: str) -> list:
    rows = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .all()
    )
    return [ChatMessage(role=m.role, content=m.content) for m in rows if m.role in ("user", "assistant")]


@router.websocket("/ws/assistant")
async def assistant_ws(websocket: WebSocket):
    await websocket.accept()
    await _emit(websocket, "assistant.started")
    orchestrator = AgentOrchestrator(provider=get_ai_provider(), tools=registry)

    # Per-connection state for a paused (awaiting-confirmation) turn.
    paused_history = None
    paused_conversation_id = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await _emit(websocket, "assistant.error", error="Malformed JSON.")
                continue

            db = SessionLocal()
            try:
                if "confirmation_id" in data:
                    pending = get_pending(data["confirmation_id"])
                    if pending is None:
                        await _emit(websocket, "assistant.error", error="Confirmation expired or unknown.")
                        continue
                    pop_pending(data["confirmation_id"])

                    await _emit(websocket, "assistant.thinking", conversation_id=paused_conversation_id)
                    result = await orchestrator.continue_after_confirmation(
                        pending, approved=bool(data.get("approved")), history=paused_history or [],
                    )
                    if result.final_text:
                        msg = Message(id=str(uuid.uuid4()), conversation_id=paused_conversation_id, role="assistant", content=result.final_text)
                        db.add(msg)
                        db.commit()
                    await _emit(
                        websocket, "assistant.completed",
                        conversation_id=paused_conversation_id, content=result.final_text or "",
                    )
                    paused_history, paused_conversation_id = None, None
                    continue

                user_text = data["message"]
                conversation_id = data.get("conversation_id")
                user = _get_or_create_default_user(db)

                if conversation_id:
                    conversation = db.get(Conversation, conversation_id)
                    if conversation is None:
                        await _emit(websocket, "assistant.error", error="Conversation not found")
                        continue
                else:
                    conversation = Conversation(id=str(uuid.uuid4()), user_id=user.id)
                    db.add(conversation)
                    db.commit()
                    db.refresh(conversation)

                db.add(Message(id=str(uuid.uuid4()), conversation_id=conversation.id, role="user", content=user_text))
                db.commit()

                await _emit(websocket, "assistant.thinking", conversation_id=conversation.id)

                history = _load_history(db, conversation.id)
                result = await orchestrator.run(user_text, history[:-1])

                for event in result.tool_events:
                    kwargs = {"success": event["success"]} if "success" in event else {}
                    await _emit(websocket, f"assistant.{event['type']}", tool=event["tool"], conversation_id=conversation.id, **kwargs)

                if result.pending_confirmation:
                    paused_history = history
                    paused_conversation_id = conversation.id
                    await _emit(
                        websocket, "assistant.confirmation_required",
                        conversation_id=conversation.id,
                        confirmation_id=result.pending_confirmation.id,
                        tool=result.pending_confirmation.tool_name,
                        description=result.pending_confirmation.description,
                        permission_level=result.pending_confirmation.permission_level.value,
                    )
                    continue

                final_text = result.final_text or ""
                await _emit(websocket, "assistant.speaking", delta=final_text, conversation_id=conversation.id)

                assistant_message = Message(id=str(uuid.uuid4()), conversation_id=conversation.id, role="assistant", content=final_text)
                db.add(assistant_message)
                db.commit()
                db.refresh(assistant_message)

                await _emit(
                    websocket, "assistant.completed",
                    conversation_id=conversation.id, message_id=assistant_message.id,
                    content=final_text, steps_taken=result.steps_taken,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(f"WebSocket assistant error: {exc}")
                await _emit(websocket, "assistant.error", error=str(exc))
            finally:
                db.close()

    except WebSocketDisconnect:
        logger.info("Client disconnected from /ws/assistant")
