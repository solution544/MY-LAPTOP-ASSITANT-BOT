"""
Database models — the minimum schema required by the Solution AI spec
(section 19): users, conversations, messages, memories, tasks, task_steps,
tool_calls, agent_sessions, settings, scheduled_tasks.

pgvector is used for the `memories.embedding` column so semantic memory
search (Phase 7) can run directly against Postgres. If the pgvector
extension isn't installed yet, `scripts/init_db.sql` creates it.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.database.session import Base


def _uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    conversations = relationship("Conversation", back_populates="user")
    memories = relationship("Memory", back_populates="user")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    conversation_id = Column(UUID(as_uuid=False), ForeignKey("conversations.id"), nullable=False)
    role = Column(String, nullable=False)  # user | assistant | system | tool
    content = Column(Text, nullable=False)
    model = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class Memory(Base):
    __tablename__ = "memories"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    memory_type = Column(String, nullable=False)  # preference | project | fact | episodic
    importance = Column(Integer, default=1)
    embedding = Column(Vector(1536), nullable=True)  # populated in Phase 7
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="memories")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, default="pending")  # pending|running|paused|completed|failed|cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    steps = relationship("TaskStep", back_populates="task", order_by="TaskStep.step_number")


class TaskStep(Base):
    __tablename__ = "task_steps"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    task_id = Column(UUID(as_uuid=False), ForeignKey("tasks.id"), nullable=False)
    step_number = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String, default="pending")
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("Task", back_populates="steps")


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    session_id = Column(UUID(as_uuid=False), ForeignKey("agent_sessions.id"), nullable=True)
    tool_name = Column(String, nullable=False)
    arguments = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    status = Column(String, default="pending")  # pending|success|failed|awaiting_confirmation
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    conversation_id = Column(UUID(as_uuid=False), ForeignKey("conversations.id"), nullable=True)
    status = Column(String, default="running")
    steps_taken = Column(Integer, default=0)
    max_steps = Column(Integer, default=30)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class Setting(Base):
    __tablename__ = "settings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    key = Column(String, unique=True, nullable=False)
    value = Column(Text, nullable=True)
    is_encrypted = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    schedule_type = Column(String, nullable=False)  # once|daily|weekly|monthly|custom
    cron_expression = Column(String, nullable=True)
    run_at = Column(DateTime, nullable=True)
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
