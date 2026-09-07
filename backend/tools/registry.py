
"""
Central Tool Registry.

Internal tool names can use namespaces such as:
    computer.open_application
    computer.list_running_applications
    filesystem.read_file
    terminal.run_command
    web.search_web

OpenAI function names cannot contain dots (.).
Therefore, AI-facing tool names are converted to:

    computer_open_application
    computer_list_running_applications
    filesystem_read_file
    terminal_run_command
    web_search_web

The registry converts the AI-facing name back to the internal
name before executing the tool.

The permission system is enforced here before any tool executes.
"""

from backend.ai.base import ToolDefinition
from backend.core.logging import logger
from backend.security.permissions import (
    ConfirmationRequired,
    register_pending,
    requires_confirmation,
)
from backend.tools.base import Tool, ToolResult


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool using its internal name."""

        if tool.name in self._tools:
            raise ValueError(
                f"Tool '{tool.name}' is already registered"
            )

        self._tools[tool.name] = tool

        logger.info(
            f"Registered tool: {tool.name} "
            f"[{tool.permission_level.value}]"
        )

    def get(self, name: str) -> Tool | None:
        """
        Get a tool using either:

        1. Its internal name:
           computer.list_running_applications

        2. Its OpenAI-safe name:
           computer_list_running_applications
        """

        # Direct lookup using the internal name.
        tool = self._tools.get(name)

        if tool is not None:
            return tool

        # Try converting the AI-facing name back to
        # the internal name.
        internal_name = self.ai_name_to_internal(name)

        return self._tools.get(internal_name)

    @staticmethod
    def internal_to_ai_name(name: str) -> str:
        """
        Convert an internal tool name to an OpenAI-safe name.

        Example:
            computer.list_running_applications
            ->
            computer_list_running_applications
        """

        return name.replace(".", "_")

    def ai_name_to_internal(self, name: str) -> str:
        """
        Convert an OpenAI-safe tool name back to the
        internal registered tool name.

        Example:
            computer_list_running_applications
            ->
            computer.list_running_applications
        """

        # Already an internal name.
        if name in self._tools:
            return name

        # Find the internal name that maps to this AI name.
        for internal_name in self._tools:
            if self.internal_to_ai_name(internal_name) == name:
                return internal_name

        # Return original name if no mapping exists.
        return name

    def list_definitions(self) -> list[ToolDefinition]:
        """
        Return tool definitions for the AI provider.

        Internal names are converted into OpenAI-compatible
        function names.
        """

        return [
            ToolDefinition(
                name=self.internal_to_ai_name(t.name),
                description=t.description,
                input_schema=t.input_schema,
            )
            for t in self._tools.values()
        ]

    def list_all(self) -> list[dict]:
        """
        Return all registered tools using their internal names.

        Used by the API's tool-listing endpoint.
        """

        return [
            {
                "name": t.name,
                "description": t.description,
                "permission_level": t.permission_level.value,
                "input_schema": t.input_schema,
            }
            for t in self._tools.values()
        ]

    async def execute(
        self,
        tool_name: str,
        arguments: dict,
        *,
        pre_confirmed: bool = False,
    ) -> ToolResult:
        """
        Execute a tool.

        The AI may send an OpenAI-safe name, so it is first
        converted back to the internal tool name.
        """

        internal_name = self.ai_name_to_internal(tool_name)

        tool = self._tools.get(internal_name)

        if tool is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name}",
                error_code="UNKNOWN_TOOL",
            )

        # Enforce permission system.
        if (
            requires_confirmation(tool.permission_level)
            and not pre_confirmed
        ):
            print(
                "[DEBUG REGISTRY]",
                internal_name,
                repr(arguments),
            )

            description = tool.confirmation_description(
                **arguments
            )

            pending = register_pending(
                internal_name,
                arguments,
                description,
                tool.permission_level,
            )

            raise ConfirmationRequired(pending)

        try:
            return await tool.execute(**arguments)

        except Exception as exc:
            logger.error(
                f"Tool '{internal_name}' raised an exception: {exc}"
            )

            return ToolResult(
                success=False,
                error=str(exc),
                error_code="TOOL_EXCEPTION",
            )


# One process-wide registry.
# Populated at startup by backend/tools/register_all.py.
registry = ToolRegistry()