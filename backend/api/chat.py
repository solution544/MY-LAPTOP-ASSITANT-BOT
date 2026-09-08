import csv
import io
import json
import traceback
import uuid
from datetime import datetime
from typing import Literal, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.ai.base import ChatMessage
from backend.ai.provider_factory import get_ai_provider
from backend.agents.orchestrator import AgentOrchestrator
from backend.core.logging import logger
from backend.database.models import Conversation, Message, User
from backend.database.session import get_db
from backend.security.permissions import get_pending, pop_pending
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
# FILE EXTRACTION
# ==============================================================

MAX_FILE_SIZE = 10 * 1024 * 1024


async def _extract_file_content(
    file: UploadFile,
) -> str:

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file has no filename.",
        )

    raw_data = await file.read()

    if len(raw_data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File is too large. Maximum size is 10 MB.",
        )

    filename = file.filename
    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    # ----------------------------------------------------------
    # TEXT FILES
    # ----------------------------------------------------------

    if extension in {
        "txt",
        "md",
        "py",
        "js",
        "jsx",
        "ts",
        "tsx",
        "css",
        "html",
        "htm",
        "sql",
        "json",
        "xml",
        "yaml",
        "yml",
        "log",
        "env",
    }:

        try:
            return raw_data.decode("utf-8", errors="replace")

        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Could not read text file: {exc}",
            ) from exc

    # ----------------------------------------------------------
    # CSV
    # ----------------------------------------------------------

    if extension == "csv":

        try:
            text = raw_data.decode(
                "utf-8",
                errors="replace",
            )

            rows = csv.reader(
                io.StringIO(text)
            )

            return "\n".join(
                " | ".join(row)
                for row in rows
            )

        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Could not read CSV file: {exc}",
            ) from exc

    # ----------------------------------------------------------
    # PDF
    # ----------------------------------------------------------

    if extension == "pdf":

        try:
            from pypdf import PdfReader

            reader = PdfReader(
                io.BytesIO(raw_data)
            )

            pages = []

            for page_number, page in enumerate(
                reader.pages,
                start=1,
            ):

                text = page.extract_text() or ""

                pages.append(
                    f"--- Page {page_number} ---\n{text}"
                )

            return "\n\n".join(pages)

        except ImportError as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "PDF support is not installed. "
                    "Run: pip install pypdf"
                ),
            ) from exc

        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Could not read PDF: {exc}",
            ) from exc

    # ----------------------------------------------------------
    # DOCX
    # ----------------------------------------------------------

    if extension == "docx":

        try:
            from docx import Document

            document = Document(
                io.BytesIO(raw_data)
            )

            paragraphs = [
                paragraph.text
                for paragraph in document.paragraphs
                if paragraph.text.strip()
            ]

            return "\n".join(paragraphs)

        except ImportError as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "DOCX support is not installed. "
                    "Run: pip install python-docx"
                ),
            ) from exc

        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Could not read DOCX: {exc}",
            ) from exc

    # ----------------------------------------------------------
    # UNSUPPORTED
    # ----------------------------------------------------------

    raise HTTPException(
        status_code=400,
        detail=(
            f"Unsupported file type: .{extension}. "
            "Supported files: TXT, MD, PDF, DOCX, CSV, "
            "JSON, XML, YAML, PY, JS, JSX, TS, TSX, CSS, HTML and SQL."
        ),
    )


# ==============================================================
# RUN AGENT
# ==============================================================

async def _run_agent(
    request_message: str,
    history: list[ChatMessage],
):

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

@router.post("")
async def chat(
    message: str = Form(""),
    conversation_id: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    """
    Main Solution AI chat endpoint.

    Accepts:
    - normal text messages
    - optional file uploads
    - optional conversation ID
    """

    # ----------------------------------------------------------
    # VALIDATE INPUT
    # ----------------------------------------------------------

    if not message.strip() and file is None:
        raise HTTPException(
            status_code=400,
            detail="Please provide a message or upload a file.",
        )

    # ----------------------------------------------------------
    # USER
    # ----------------------------------------------------------

    user = _get_or_create_default_user(db)

    # ----------------------------------------------------------
    # CONVERSATION
    # ----------------------------------------------------------

    if conversation_id:

        conversation = db.get(
            Conversation,
            conversation_id,
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
            title=(
                message.strip()[:60]
                if message.strip()
                else (
                    file.filename[:60]
                    if file and file.filename
                    else "New Conversation"
                )
            ),
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    conversation_id = cast(
        str,
        conversation.id,
    )

    # ----------------------------------------------------------
    # PROCESS FILE
    # ----------------------------------------------------------

    file_content = ""

    if file is not None:

        file_content = await _extract_file_content(
            file
        )

        if not file_content.strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    f"The file '{file.filename}' "
                    "does not contain readable text."
                ),
            )

    # ----------------------------------------------------------
    # BUILD AI MESSAGE
    # ----------------------------------------------------------

    ai_message = message.strip()

    if file is not None:

        ai_message = f"""
The user uploaded a file named "{file.filename}".

Use the contents of this file when answering the user's request.

================ FILE CONTENT ================

{file_content}

============== END FILE CONTENT ==============

User's request:
{message.strip() or "Please analyze this file."}
""".strip()

    # ----------------------------------------------------------
    # SAVE USER MESSAGE
    # ----------------------------------------------------------

    saved_user_content = message.strip()

    if file is not None:

        saved_user_content = (
            f"📎 {file.filename}\n\n"
            f"{message.strip() or 'Please analyze this file.'}"
        )

    user_message = Message(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role="user",
        content=saved_user_content,
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

    history = chat_messages[:-1]

    # ----------------------------------------------------------
    # RUN AI
    # ----------------------------------------------------------

    try:

        provider, orchestrator, result = await _run_agent(
            request_message=ai_message,
            history=history,
        )

    except Exception as exc:

        logger.exception(
            "Agent execution failed"
        )

        print(
            "\n========== SOLUTION AI ERROR =========="
        )
        print(f"ERROR: {exc}")
        traceback.print_exc()
        print(
            "=======================================\n"
        )

        raise HTTPException(
            status_code=502,
            detail=f"AI agent error: {exc}",
        ) from exc

    # ----------------------------------------------------------
    # CONFIRMATION
    # ----------------------------------------------------------

    if result.pending_confirmation is not None:

        confirmation = result.pending_confirmation

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

        return {
            "conversation_id": conversation_id,
            "message_id": cast(
                str,
                assistant_message.id,
            ),
            "role": "assistant",
            "content": confirmation_text,
            "created_at": cast(
                datetime,
                assistant_message.created_at,
            ).isoformat(),
            "confirmation_required": True,
            "confirmation_id": confirmation.id,
            "tool_name": confirmation.tool_name,
            "description": confirmation.description,
            "permission_level": (
                confirmation.permission_level.value
            ),
        }

    # ----------------------------------------------------------
    # FINAL RESPONSE
    # ----------------------------------------------------------

    final_text = result.final_text or (
        "I completed the request, but I don't have "
        "a final response to provide."
    )

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

    return {
        "conversation_id": conversation_id,
        "message_id": cast(
            str,
            assistant_message.id,
        ),
        "role": "assistant",
        "content": cast(
            str,
            assistant_message.content,
        ),
        "created_at": cast(
            datetime,
            assistant_message.created_at,
        ).isoformat(),
        "confirmation_required": False,
    }


# ==============================================================
# CONFIRMATION
# ==============================================================

@router.post("/confirm")
async def confirm_chat(
    request: ChatConfirmationRequest,
    db: Session = Depends(get_db),
):

    confirmation_id = request.confirmation_id
    approved = request.approved

    pending = get_pending(
        confirmation_id
    )

    if pending is None:
        raise HTTPException(
            status_code=404,
            detail="Confirmation expired or unknown.",
        )

    context = pending.context or {}

    if context.get("source") != "chat_api":
        raise HTTPException(
            status_code=403,
            detail=(
                "This confirmation does not belong "
                "to the chat API."
            ),
        )

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

    paused_messages = (
        pending.context or {}
    ).get(
        "paused_messages"
    )

    history = (
        paused_messages
        if isinstance(paused_messages, list)
        else []
    )

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

        traceback.print_exc()

        raise HTTPException(
            status_code=502,
            detail=(
                "Confirmation execution failed: "
                f"{exc}"
            ),
        ) from exc

    if not approved:

        final_text = (
            "Okay. I cancelled the action."
        )

    else:

        final_text = result.final_text or (
            "Confirmed. The action has been completed."
        )

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