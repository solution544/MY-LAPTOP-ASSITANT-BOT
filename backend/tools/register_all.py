"""
Registers every local tool with the process-wide ToolRegistry. Called once
from backend/main.py at startup. MCP tools (Phase 10) register separately,
after the MCP client discovers them, via backend/mcp/client.py.
"""

from backend.core.logging import logger
from backend.tools.computer_control import ALL_COMPUTER_TOOLS
from backend.tools.filesystem_tools import ALL_FILESYSTEM_TOOLS
from backend.tools.memory_tools import ALL_MEMORY_TOOLS
from backend.tools.notification_tools import ALL_NOTIFICATION_TOOLS
from backend.tools.registry import registry
from backend.tools.system_tools import ALL_SYSTEM_TOOLS
from backend.tools.terminal_tools import ALL_TERMINAL_TOOLS
from backend.tools.vision_tools import ALL_VISION_TOOLS
from backend.tools.web_tools import ALL_WEB_TOOLS

_ALL_TOOL_GROUPS = [
    ALL_COMPUTER_TOOLS, ALL_FILESYSTEM_TOOLS, ALL_TERMINAL_TOOLS, ALL_WEB_TOOLS,
    ALL_MEMORY_TOOLS, ALL_SYSTEM_TOOLS, ALL_NOTIFICATION_TOOLS, ALL_VISION_TOOLS,
]


def register_all_tools() -> None:
    total = 0
    for group in _ALL_TOOL_GROUPS:
        for tool in group:
            if registry.get(tool.name) is None:  # idempotent — safe if called twice (e.g. reload)
                registry.register(tool)
                total += 1
    logger.info(f"Tool registry ready: {total} tools registered.")
