
import base64
import time
import uuid
from typing import cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.agents.orchestrator import AgentOrchestrator
from backend.ai.provider_factory import get_ai_provider
from backend.database.models import Conversation, Message, User
from backend.database.session import get_db
from backend.tools.registry import registry
from backend.voice.provider_factory import get_stt_provider, get_tts_provider


router = APIRouter(prefix="/api/voice", tags=["voice"])


class VoiceRequest(BaseModel):
    audio_base64: str
    conversation_id: str | None = None


class VoiceResponse(BaseModel):
    transcript: str
    reply_text: str
    reply_audio_base64: str
    reply_audio_mime_type: str
    conversation_id: str


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


@router.post("", response_model=VoiceResponse)
async def voice_turn(
    request: VoiceRequest,
    db: Session = Depends(get_db),
):
    total_start = time.perf_counter()

    # ---------------------------------
    # Decode audio
    # ---------------------------------
    audio_bytes = base64.b64decode(request.audio_base64)

    print(
        f"[VOICE] Audio received: "
        f"{len(audio_bytes) / 1024:.1f} KB"
    )

    # ---------------------------------
    # Speech-to-Text
    # ---------------------------------
    stt_start = time.perf_counter()

    stt = get_stt_provider()
    transcript = await stt.transcribe(audio_bytes)

    stt_time = time.perf_counter() - stt_start

    print(f"[VOICE] STT: {stt_time:.2f}s")
    print(f"[VOICE] Transcript: {transcript}")

    # ---------------------------------
    # Database / Conversation
    # ---------------------------------
    database_start = time.perf_counter()

    user = _get_or_create_default_user(db)

    if request.conversation_id:
        conversation = db.get(
            Conversation,
            request.conversation_id,
        )
    else:
        conversation = None

    if conversation is None:
        conversation = Conversation(
            id=str(uuid.uuid4()),
            user_id=user.id,
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    db.add(
        Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            role="user",
            content=transcript,
        )
    )

    db.commit()

    database_time = time.perf_counter() - database_start

    print(
        f"[VOICE] Database: {database_time:.2f}s"
    )

    # ---------------------------------
    # AI
    # ---------------------------------
    ai_start = time.perf_counter()

    orchestrator = AgentOrchestrator(
        provider=get_ai_provider(),
        tools=registry,
    )

    result = await orchestrator.run(
        transcript,
        history=[],
    )

    reply_text = (
        result.final_text
        or "I ran into an issue and couldn't finish that."
    )

    ai_time = time.perf_counter() - ai_start

    print(f"[VOICE] AI: {ai_time:.2f}s")
    print(f"[VOICE] Reply: {reply_text}")

    # ---------------------------------
    # Save AI response
    # ---------------------------------
    db.add(
        Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            role="assistant",
            content=reply_text,
        )
    )

    db.commit()

    # ---------------------------------
    # Text-to-Speech
    # ---------------------------------
    tts_start = time.perf_counter()

    tts = get_tts_provider()

    reply_audio = await tts.synthesize(
        reply_text
    )

    tts_time = time.perf_counter() - tts_start

    print(f"[VOICE] TTS: {tts_time:.2f}s")

    # ---------------------------------
    # Total time
    # ---------------------------------
    total_time = time.perf_counter() - total_start

    print(
        f"[VOICE] TOTAL: {total_time:.2f}s"
    )

    # ---------------------------------
    # Response
    # ---------------------------------
    return VoiceResponse(
        transcript=transcript,
        reply_text=reply_text,
        reply_audio_base64=base64.b64encode(
            reply_audio
        ).decode("ascii"),
        reply_audio_mime_type="audio/wav",
        conversation_id=cast(
            str,
            conversation.id,
        ),
    )