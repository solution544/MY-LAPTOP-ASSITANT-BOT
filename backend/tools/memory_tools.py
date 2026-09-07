"""
Memory tools (spec section 3: remember_information, search_memory).

These wrap MemoryService for use inside the tool-calling loop. They open
their own DB session rather than depending on FastAPI's request-scoped
`get_db()`, since tool execution happens inside the AgentOrchestrator, not
inside a request handler.
"""

from backend.database.session import SessionLocal
from backend.memory.memory_service import memory_service
from backend.security.permissions import PermissionLevel
from backend.tools.base import Tool, ToolResult


class RememberInformationTool(Tool):
    name = "memory.remember_information"
    description = "Store a piece of information in long-term memory for future conversations."
    input_schema = {
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "memory_type": {"type": "string", "enum": ["fact", "preference", "project", "episodic"], "default": "fact"},
            "importance": {"type": "integer", "minimum": 1, "maximum": 5, "default": 1},
        },
        "required": ["content"],
    }
    permission_level = PermissionLevel.SAFE

    async def execute(self, content: str, memory_type: str = "fact", importance: int = 1) -> ToolResult:
        db = SessionLocal()
        try:
            memory = await memory_service.remember(db, content, memory_type, importance)
            return ToolResult(success=True, data={"id": memory.id, "content": memory.content})
        finally:
            db.close()


class SearchMemoryTool(Tool):
    name = "memory.search_memory"
    description = "Search long-term memory for information relevant to a query."
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 5}},
        "required": ["query"],
    }
    permission_level = PermissionLevel.SAFE

    async def execute(self, query: str, limit: int = 5) -> ToolResult:
        db = SessionLocal()
        try:
            results = await memory_service.search(db, query, limit)
            return ToolResult(success=True, data=[{"content": m.content, "type": m.memory_type} for m in results])
        finally:
            db.close()


ALL_MEMORY_TOOLS = [RememberInformationTool(), SearchMemoryTool()]
