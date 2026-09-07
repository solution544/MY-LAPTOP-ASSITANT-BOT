"""
MCP client (spec section 17) — connects to external MCP servers configured
in Settings, discovers their tools/resources, and wraps each discovered MCP
tool as a `backend.tools.base.Tool` so it can register with the same
ToolRegistry as every built-in tool. The AgentOrchestrator's loop doesn't
know or care whether a tool is local or came from an MCP server.

Uses the official `mcp` Python SDK's stdio client, since most current MCP
servers are launched as local subprocesses (e.g. `npx @some/mcp-server`)
rather than exposed over HTTP.
"""

from contextlib import AsyncExitStack

from backend.core.logging import logger
from backend.security.permissions import PermissionLevel
from backend.tools.base import Tool, ToolResult
from backend.tools.registry import registry


class MCPServerConfig:
    def __init__(self, name: str, command: str, args: list[str] | None = None, env: dict | None = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}


class _MCPToolWrapper(Tool):
    """Adapts one tool discovered from an MCP server to the local Tool interface."""

    def __init__(self, session, mcp_tool, server_name: str):
        self._session = session
        self.name = f"mcp.{server_name}.{mcp_tool.name}"
        self.description = mcp_tool.description or f"MCP tool from {server_name}"
        self.input_schema = mcp_tool.inputSchema or {"type": "object", "properties": {}}
        # MCP tools are treated as SENSITIVE by default — they run arbitrary code
        # in a server we didn't write, so the confirmation system should see them
        # unless the user has explicitly trusted that server (a Settings-level
        # override, not implemented here to avoid quietly widening the default).
        self.permission_level = PermissionLevel.SENSITIVE

    async def execute(self, **kwargs) -> ToolResult:
        try:
            result = await self._session.call_tool(self.name.split(".", 2)[-1], arguments=kwargs)
            text_parts = [block.text for block in result.content if hasattr(block, "text")]
            return ToolResult(success=not result.isError, data="\n".join(text_parts))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc), error_code="MCP_TOOL_FAILED")


class MCPClientManager:
    """
    Holds one live session per configured MCP server for the lifetime of the
    backend process. Call `connect_all()` once at startup (after
    register_all_tools()) with the list of servers from Settings/DB.
    """

    def __init__(self):
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, object] = {}

    async def connect(self, config: MCPServerConfig) -> int:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=config.command, args=config.args, env=config.env or None)
        read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        tools_result = await session.list_tools()
        for mcp_tool in tools_result.tools:
            wrapper = _MCPToolWrapper(session, mcp_tool, config.name)
            if registry.get(wrapper.name) is None:
                registry.register(wrapper)

        self._sessions[config.name] = session
        logger.info(f"MCP server '{config.name}' connected: {len(tools_result.tools)} tool(s) registered.")
        return len(tools_result.tools)

    async def connect_all(self, configs: list[MCPServerConfig]) -> None:
        for config in configs:
            try:
                await self.connect(config)
            except Exception as exc:  # noqa: BLE001
                logger.error(f"Failed to connect MCP server '{config.name}': {exc}")

    async def shutdown(self) -> None:
        await self._exit_stack.aclose()


mcp_manager = MCPClientManager()
