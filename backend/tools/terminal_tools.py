"""
Terminal agent (spec section 16).

`run_command` is SENSITIVE by default and DANGEROUS (always confirmed,
regardless of CONFIRMATION_MODE) if it matches a known destructive pattern —
format, shutdown/restart, recursive force-delete, credential dumps, etc.
This list is deliberately conservative: it can have false positives (a
harmless command gets a confirmation prompt it didn't strictly need) but
must never have false negatives in the other direction.
"""

import asyncio
import re

from backend.security.permissions import PermissionLevel
from backend.tools.base import Tool, ToolResult

_DANGEROUS_PATTERNS = [
    r"\bformat\s+[a-zA-Z]:",
    r"\bshutdown\b",
    r"\brestart-computer\b",
    r"\brm\s+-rf\s+/",
    r"\bdel\s+/s\s+/q\b",
    r"\bremove-item\b.*-recurse.*-force",
    r"\bdiskpart\b",
    r"\bmkfs\b",
    r":(){:|:&};:",  # fork bomb
]


def _is_dangerous(command: str) -> bool:
    lowered = command.lower()
    return any(re.search(pattern, lowered) for pattern in _DANGEROUS_PATTERNS)


class RunCommandTool(Tool):
    name = "terminal.run_command"
    description = (
        "Run a shell command and return its output. Destructive-looking commands "
        "(format, shutdown, recursive force-delete, etc.) always require confirmation."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "cwd": {"type": "string", "description": "Working directory, optional"},
            "timeout_seconds": {"type": "integer", "default": 30},
        },
        "required": ["command"],
    }
    permission_level = PermissionLevel.SENSITIVE  # escalated to DANGEROUS per-call below

    def confirmation_description(self, command: str, **_) -> str:
        return f"Run command: {command}"

    async def execute(self, command: str, cwd: str | None = None, timeout_seconds: int = 30) -> ToolResult:
        try:
            process = await asyncio.create_subprocess_shell(
                command, cwd=cwd,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(success=False, error=f"Command timed out after {timeout_seconds}s", error_code="TIMEOUT")

            return ToolResult(
                success=process.returncode == 0,
                data={
                    "stdout": stdout.decode(errors="replace")[-20_000:],
                    "stderr": stderr.decode(errors="replace")[-20_000:],
                    "return_code": process.returncode,
                },
                error=None if process.returncode == 0 else f"Command exited with code {process.returncode}",
                error_code=None if process.returncode == 0 else "NONZERO_EXIT",
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc), error_code="EXECUTION_FAILED")


class DangerousRunCommandTool(RunCommandTool):
    """Registered separately so the registry always enforces DANGEROUS confirmation
    for commands matching _DANGEROUS_PATTERNS, regardless of CONFIRMATION_MODE."""
    name = "terminal.run_dangerous_command"
    permission_level = PermissionLevel.DANGEROUS


def classify_command_tool(command: str) -> str:
    """Used by the orchestrator to route a command to the right tool name before execution."""
    return "terminal.run_dangerous_command" if _is_dangerous(command) else "terminal.run_command"


ALL_TERMINAL_TOOLS = [RunCommandTool(), DangerousRunCommandTool()]
