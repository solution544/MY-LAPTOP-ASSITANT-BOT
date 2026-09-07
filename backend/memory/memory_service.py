"""
MemoryService (spec section 18).

Long-term/semantic memory: content is embedded and stored in
`memories.embedding` (pgvector). Retrieval does a cosine-distance nearest-
neighbor search, so "what's my main AI project?" can match a memory stored
as "User's main AI project is called Solution AI" without exact keyword
overlap.

Short-term memory (current conversation) is just `messages` for the active
`conversation_id` — already covered by the chat/WebSocket endpoints and
doesn't need this service. Episodic memory (important past events) is
stored the same way as long-term memory here, distinguished only by
`memory_type="episodic"`.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.models import Memory, User
from backend.memory.embeddings import get_embedding_provider


def _get_or_create_default_user(db: Session) -> User:
    user = db.query(User).first()
    if user is None:
        user = User(id=str(uuid.uuid4()), name="User")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


class MemoryService:
    async def remember(self, db: Session, content: str, memory_type: str = "fact", importance: int = 1) -> Memory:
        user = _get_or_create_default_user(db)
        embedder = get_embedding_provider()
        vector = await embedder.embed(content)

        memory = Memory(
            id=str(uuid.uuid4()), user_id=user.id, content=content,
            memory_type=memory_type, importance=importance, embedding=vector,
        )
        db.add(memory)
        db.commit()
        db.refresh(memory)
        return memory

    async def search(self, db: Session, query: str, limit: int = 5) -> list[Memory]:
        embedder = get_embedding_provider()
        query_vector = await embedder.embed(query)

        stmt = (
            select(Memory)
            .order_by(Memory.embedding.cosine_distance(query_vector))
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())

    def forget(self, db: Session, memory_id: str) -> bool:
        memory = db.get(Memory, memory_id)
        if memory is None:
            return False
        db.delete(memory)
        db.commit()
        return True

    def list_all(self, db: Session, limit: int = 100) -> list[Memory]:
        return list(
            db.query(Memory).order_by(Memory.created_at.desc()).limit(limit).all()
        )


memory_service = MemoryService()
