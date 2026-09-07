from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    role: str
    content: str
    created_at: datetime

    confirmation_required: bool = False
    confirmation_id: Optional[str] = None
    tool_name: Optional[str] = None
    description: Optional[str] = None
    permission_level: Optional[str] = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    model: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = []
    