"""
Database models for Solution AI.

The application supports:

- SQLite for local development
- PostgreSQL + pgvector for production

The Memory.embedding column uses native pgvector when the
application is connected to PostgreSQL. For SQLite, embeddings
are stored as JSON text so the local development database can
still operate without PostgreSQL extensions.
"""

import uuid
import json
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from backend.database.session import Base


# ---------------------------------------------------------
# OPTIONAL PGVECTOR SUPPORT
# ---------------------------------------------------------

try:
    from pgvector.sqlalchemy import Vector

    PGVECTOR_AVAILABLE = True

except ImportError:
    Vector = None
    PGVECTOR_AVAILABLE = False


# ---------------------------------------------------------
# UUID HELPER
# ---------------------------------------------------------

def _uuid():
    return str(uuid.uuid4())


# ---------------------------------------------------------
# CROSS-DATABASE EMBEDDING TYPE
# ---------------------------------------------------------

class EmbeddingType(TypeDecorator):
    """
    Stores embeddings differently depending on the database.

    PostgreSQL:
        Uses native pgvector VECTOR(1536).

    SQLite:
        Stores the vector as JSON text.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and PGVECTOR_AVAILABLE:
            return dialect.type_descriptor(Vector(1536))

        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None

        if dialect.name == "postgresql":
            return value

        # SQLite fallback
        if isinstance(value, str):
            return value

        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None

        if dialect.name == "postgresql":
            return value

        # SQLite fallback
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        return value


# ---------------------------------------------------------
# USER
# ---------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
    )

    name = Column(
        String,
        nullable=False,
    )

    email = Column(
        String,
        unique=True,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    conversations = relationship(
        "Conversation",
        back_populates="user",
    )

    memories = relationship(
        "Memory",
        back_populates="user",
    )


# ---------------------------------------------------------
# CONVERSATION
# ---------------------------------------------------------

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
    )

    user_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=False,
    )

    title = Column(
        String,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    user = relationship(
        "User",
        back_populates="conversations",
    )

    messages = relationship(
        "Message",
        back_populates="conversation",
        order_by="Message.created_at",
    )


# ---------------------------------------------------------
# MESSAGE
# ---------------------------------------------------------

class Message(Base):
    __tablename__ = "messages"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
    )

    conversation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("conversations.id"),
        nullable=False,
    )

    role = Column(
        String,
        nullable=False,
    )

    content = Column(
        Text,
        nullable=False,
    )

    model = Column(
        String,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    conversation = relationship(
        "Conversation",
        back_populates="messages",
    )


# ---------------------------------------------------------
# MEMORY
# ---------------------------------------------------------

class Memory(Base):
    __tablename__ = "memories"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
    )

    user_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=False,
    )

    content = Column(
        Text,
        nullable=False,
    )

    memory_type = Column(
        String,
        nullable=False,
    )

    importance = Column(
        Integer,
        default=1,
    )

    # PostgreSQL:
    #     VECTOR(1536)
    #
    # SQLite:
    #     JSON text fallback
    embedding = Column(
        EmbeddingType,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    user = relationship(
        "User",
        back_populates="memories",
    )


# ---------------------------------------------------------
# TASK
# ---------------------------------------------------------

class Task(Base):
    __tablename__ = "tasks"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
    )

    name = Column(
        String,
        nullable=False,
    )

    description = Column(
        Text,
        nullable=True,
    )

    status = Column(
        String,
        default="pending",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    started_at = Column(
        DateTime,
        nullable=True,
    )

    completed_at = Column(
        DateTime,
        nullable=True,
    )

    result = Column(
        JSON,
        nullable=True,
    )

    error = Column(
        Text,
        nullable=True,
    )

    steps = relationship(
        "TaskStep",
        back_populates="task",
        order_by="TaskStep.step_number",
    )


# ---------------------------------------------------------
# TASK STEP
# ---------------------------------------------------------

class TaskStep(Base):
    __tablename__ = "task_steps"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
    )

    task_id = Column(
        UUID(as_uuid=False),
        ForeignKey("tasks.id"),
        nullable=False,
    )

    step_number = Column(
        Integer,
        nullable=False,
    )

    description = Column(
        Text,
        nullable=False,
    )

    status = Column(
        String,
        default="pending",
    )

    result = Column(
        JSON,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    task = relationship(
        "Task",
        back_populates="steps",
    )


# ---------------------------------------------------------
# TOOL CALL
# ---------------------------------------------------------

class ToolCall(Base):
    __tablename__ = "tool_calls"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
    )

    session_id = Column(
        UUID(as_uuid=False),
        ForeignKey("agent_sessions.id"),
        nullable=True,
    )

    tool_name = Column(
        String,
        nullable=False,
    )

    arguments = Column(
        JSON,
        nullable=True,
    )

    result = Column(
        JSON,
        nullable=True,
    )

    status = Column(
        String,
        default="pending",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


# ---------------------------------------------------------
# AGENT SESSION
# ---------------------------------------------------------

class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
    )

    conversation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("conversations.id"),
        nullable=True,
    )

    status = Column(
        String,
        default="running",
    )

    steps_taken = Column(
        Integer,
        default=0,
    )

    max_steps = Column(
        Integer,
        default=30,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    completed_at = Column(
        DateTime,
        nullable=True,
    )


# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------

class Setting(Base):
    __tablename__ = "settings"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
    )

    key = Column(
        String,
        unique=True,
        nullable=False,
    )

    value = Column(
        Text,
        nullable=True,
    )

    is_encrypted = Column(
        Boolean,
        default=False,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


# ---------------------------------------------------------
# SCHEDULED TASK
# ---------------------------------------------------------

class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id = Column(
        UUID(as_uuid=False),
        primary_key=True,
        default=_uuid,
    )

    name = Column(
        String,
        nullable=False,
    )

    description = Column(
        Text,
        nullable=True,
    )

    schedule_type = Column(
        String,
        nullable=False,
    )

    cron_expression = Column(
        String,
        nullable=True,
    )

    run_at = Column(
        DateTime,
        nullable=True,
    )

    enabled = Column(
        Boolean,
        default=True,
    )

    last_run_at = Column(
        DateTime,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )