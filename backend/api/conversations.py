from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database.models import Conversation
from backend.database.session import get_db
from backend.schemas.chat import ConversationDetailOut, ConversationOut

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationOut])
def list_conversations(db: Session = Depends(get_db)):
    return db.query(Conversation).order_by(Conversation.updated_at.desc()).all()


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation
