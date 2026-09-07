from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.memory.memory_service import memory_service

router = APIRouter(prefix="/api/memory", tags=["memory"])


class RememberRequest(BaseModel):
    content: str
    memory_type: str = "fact"
    importance: int = 1


class MemoryOut(BaseModel):
    id: str
    content: str
    memory_type: str
    importance: int

    class Config:
        from_attributes = True


@router.get("", response_model=list[MemoryOut])
def list_memories(db: Session = Depends(get_db), limit: int = 100):
    return memory_service.list_all(db, limit)


@router.get("/search", response_model=list[MemoryOut])
async def search_memories(query: str, limit: int = 5, db: Session = Depends(get_db)):
    return await memory_service.search(db, query, limit)


@router.post("", response_model=MemoryOut)
async def create_memory(request: RememberRequest, db: Session = Depends(get_db)):
    return await memory_service.remember(db, request.content, request.memory_type, request.importance)


@router.delete("/{memory_id}")
def delete_memory(memory_id: str, db: Session = Depends(get_db)):
    if not memory_service.forget(db, memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": memory_id}
