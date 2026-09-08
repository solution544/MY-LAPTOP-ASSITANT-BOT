"""
Filesystem tools for Solution AI.

All filesystem operations are restricted to explicitly allowed folders.
Blocked folders always take priority over allowed folders.

Security rules:
- Empty allowed_folders => deny all filesystem access.
- A path must be inside an allowed folder.
- A blocked folder always overrides an allowed folder.
- Sensitive and dangerous operations remain subject to confirmation.
"""

import os
import shutil
from pathlib import Path

from backend.core.config import get_settings
from backend.security.permissions import PermissionLevel
from backend.tools.base import Tool, ToolResult


# ---------------------------------------------------------
# Path Helpers
# ---------------------------------------------------------

def _normalize_path(path: str) -> Path:
    """
    Normalize a Windows/Linux filesystem path.

    expanduser() allows paths such as ~/Documents.
    resolve(strict=False) normalizes the path without requiring it
    to already exist.
    """
    return Path(path).expanduser().resolve(strict=False)


def _is_within(path: Path, root: Path) -> bool:
    """
    Return True when `path` is inside `root`.

    The root itself is also considered valid.
    """
    try:
        path.resolve(strict=False).relative_to(
            root.resolve(strict=False)
        )
        return True
    except ValueError:
        return False


# ---------------------------------------------------------
# Security Check
# ---------------------------------------------------------

def _check_allowed(path_str: str) -> tuple[bool, str | None]:
    """
    Check whether a filesystem path is permitted.

    Security order:
    1. Normalize the requested path.
    2. Deny everything if no allowed folders exist.
    3. Reject blocked folders.
    4. Require the path to be inside an allowed folder.
    """

    settings = get_settings()

    if not path_str or not path_str.strip():
        return False, "A filesystem path is required."

    try:
        path = _normalize_path(path_str)
    except (OSError, RuntimeError, ValueError) as exc:
        return False, f"Invalid filesystem path: {exc}"

    allowed_folders = settings.allowed_folders_list
    blocked_folders = settings.blocked_folders_list

    # No allowlist = no filesystem access.
    if not allowed_folders:
        return (
            False,
            "No folders are configured as allowed. "
            "Add one in Settings > Security > Allowed folders.",
        )

    # Blocked folders always take priority.
    for blocked in blocked_folders:
        try:
            blocked_path = _normalize_path(blocked)

            if _is_within(path, blocked_path):
                return (
                    False,
                    f"'{path}' is inside a blocked folder "
                    f"({blocked_path}).",
                )
        except (OSError, RuntimeError, ValueError):
            continue

    # Path must be inside at least one allowed folder.
    for allowed in allowed_folders:
        try:
            allowed_path = _normalize_path(allowed)

            if _is_within(path, allowed_path):
                return True, None
        except (OSError, RuntimeError, ValueError):
            continue

    return (
        False,
        f"'{path}' is not inside any allowed folder.",
    )


# ---------------------------------------------------------
# List Files
# ---------------------------------------------------------

class ListFilesTool(Tool):
    name = "filesystem.list_files"
    description = "List files and folders inside a directory."

    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list.",
            }
        },
        "required": ["path"],
    }

    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, path: str) -> ToolResult:
        ok, reason = _check_allowed(path)

        if not ok:
            return ToolResult(
                success=False,
                error=reason,
                error_code="PATH_NOT_ALLOWED",
            )

        target = _normalize_path(path)

        try:
            if not target.exists():
                return ToolResult(
                    success=False,
                    error="Path does not exist",
                    error_code="NOT_FOUND",
                )

            if not target.is_dir():
                return ToolResult(
                    success=False,
                    error="Path is not a directory",
                    error_code="NOT_DIRECTORY",
                )

            entries = []

            for entry in target.iterdir():
                try:
                    entries.append(
                        {
                            "name": entry.name,
                            "is_dir": entry.is_dir(),
                            "size": (
                                entry.stat().st_size
                                if entry.is_file()
                                else None
                            ),
                        }
                    )
                except OSError:
                    entries.append(
                        {
                            "name": entry.name,
                            "is_dir": entry.is_dir(),
                            "size": None,
                        }
                    )

            return ToolResult(
                success=True,
                data=entries,
            )

        except PermissionError:
            return ToolResult(
                success=False,
                error="Permission denied while accessing this directory.",
                error_code="PERMISSION_DENIED",
            )


# ---------------------------------------------------------
# Search Files
# ---------------------------------------------------------

class SearchFilesTool(Tool):
    name = "filesystem.search_files"
    description = (
        "Recursively search for files by name pattern "
        "within an allowed folder."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "root": {
                "type": "string",
                "description": "Allowed directory to search.",
            },
            "pattern": {
                "type": "string",
                "description": "Filename pattern, e.g. *.py",
            },
        },
        "required": ["root", "pattern"],
    }

    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, root: str, pattern: str) -> ToolResult:
        ok, reason = _check_allowed(root)

        if not ok:
            return ToolResult(
                success=False,
                error=reason,
                error_code="PATH_NOT_ALLOWED",
            )

        target = _normalize_path(root)

        if not target.exists():
            return ToolResult(
                success=False,
                error="Path does not exist",
                error_code="NOT_FOUND",
            )

        if not target.is_dir():
            return ToolResult(
                success=False,
                error="Root path is not a directory",
                error_code="NOT_DIRECTORY",
            )

        try:
            matches = [
                str(path)
                for path in target.rglob(pattern)
            ]

            return ToolResult(
                success=True,
                data=matches[:200],
            )

        except PermissionError:
            return ToolResult(
                success=False,
                error="Permission denied while searching this directory.",
                error_code="PERMISSION_DENIED",
            )


# ---------------------------------------------------------
# Read File
# ---------------------------------------------------------

class ReadFileTool(Tool):
    name = "filesystem.read_file"
    description = "Read the text contents of a file."

    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the text file.",
            }
        },
        "required": ["path"],
    }

    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, path: str) -> ToolResult:
        ok, reason = _check_allowed(path)

        if not ok:
            return ToolResult(
                success=False,
                error=reason,
                error_code="PATH_NOT_ALLOWED",
            )

        target = _normalize_path(path)

        try:
            if not target.exists():
                return ToolResult(
                    success=False,
                    error="File does not exist",
                    error_code="NOT_FOUND",
                )

            if target.is_dir():
                return ToolResult(
                    success=False,
                    error="Path is a directory, not a file",
                    error_code="IS_DIRECTORY",
                )

            content = target.read_text(
                encoding="utf-8",
                errors="replace",
            )

            return ToolResult(
                success=True,
                data=content[:200_000],
            )

        except PermissionError:
            return ToolResult(
                success=False,
                error="Permission denied while reading this file.",
                error_code="PERMISSION_DENIED",
            )


# ---------------------------------------------------------
# Write File
# ---------------------------------------------------------

class WriteFileTool(Tool):
    name = "filesystem.write_file"
    description = "Write (overwrite) text content to a file."

    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
            },
            "content": {
                "type": "string",
            },
        },
        "required": ["path", "content"],
    }

    permission_level = PermissionLevel.SENSITIVE

    def confirmation_description(
        self,
        path: str,
        content: str,
        **_,
    ) -> str:
        return f"Write {len(content)} characters to {path}"

    async def execute(
        self,
        path: str,
        content: str,
    ) -> ToolResult:

        ok, reason = _check_allowed(path)

        if not ok:
            return ToolResult(
                success=False,
                error=reason,
                error_code="PATH_NOT_ALLOWED",
            )

        target = _normalize_path(path)

        try:
            target.write_text(
                content,
                encoding="utf-8",
            )

            return ToolResult(
                success=True,
                data={
                    "path": str(target),
                    "bytes_written": len(
                        content.encode("utf-8")
                    ),
                },
            )

        except PermissionError:
            return ToolResult(
                success=False,
                error="Permission denied while writing this file.",
                error_code="PERMISSION_DENIED",
            )


# ---------------------------------------------------------
# Create Folder
# ---------------------------------------------------------

class CreateFolderTool(Tool):
    name = "filesystem.create_folder"
    description = (
        "Create a new folder, including parent folders if needed."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
            }
        },
        "required": ["path"],
    }

    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, path: str) -> ToolResult:
        ok, reason = _check_allowed(path)

        if not ok:
            return ToolResult(
                success=False,
                error=reason,
                error_code="PATH_NOT_ALLOWED",
            )

        target = _normalize_path(path)

        try:
            target.mkdir(
                parents=True,
                exist_ok=True,
            )

            return ToolResult(
                success=True,
                data={
                    "path": str(target),
                },
            )

        except PermissionError:
            return ToolResult(
                success=False,
                error="Permission denied while creating this folder.",
                error_code="PERMISSION_DENIED",
            )


# ---------------------------------------------------------
# Copy File
# ---------------------------------------------------------

class CopyFileTool(Tool):
    name = "filesystem.copy_file"
    description = "Copy a file from one path to another."

    input_schema = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
            },
            "destination": {
                "type": "string",
            },
        },
        "required": ["source", "destination"],
    }

    permission_level = PermissionLevel.LOW_RISK

    async def execute(
        self,
        source: str,
        destination: str,
    ) -> ToolResult:

        for path in (source, destination):
            ok, reason = _check_allowed(path)

            if not ok:
                return ToolResult(
                    success=False,
                    error=reason,
                    error_code="PATH_NOT_ALLOWED",
                )

        source_path = _normalize_path(source)
        destination_path = _normalize_path(destination)

        try:
            shutil.copy2(
                source_path,
                destination_path,
            )

            return ToolResult(
                success=True,
                data={
                    "source": str(source_path),
                    "destination": str(destination_path),
                },
            )

        except FileNotFoundError:
            return ToolResult(
                success=False,
                error="Source file does not exist.",
                error_code="NOT_FOUND",
            )


# ---------------------------------------------------------
# Move File
# ---------------------------------------------------------

class MoveFileTool(Tool):
    name = "filesystem.move_file"
    description = "Move or rename a file."

    input_schema = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
            },
            "destination": {
                "type": "string",
            },
        },
        "required": ["source", "destination"],
    }

    permission_level = PermissionLevel.SENSITIVE

    def confirmation_description(
        self,
        source: str,
        destination: str,
        **_,
    ) -> str:
        return f"Move {source} -> {destination}"

    async def execute(
        self,
        source: str,
        destination: str,
    ) -> ToolResult:

        for path in (source, destination):
            ok, reason = _check_allowed(path)

            if not ok:
                return ToolResult(
                    success=False,
                    error=reason,
                    error_code="PATH_NOT_ALLOWED",
                )

        source_path = _normalize_path(source)
        destination_path = _normalize_path(destination)

        try:
            shutil.move(
                source_path,
                destination_path,
            )

            return ToolResult(
                success=True,
                data={
                    "source": str(source_path),
                    "destination": str(destination_path),
                },
            )

        except FileNotFoundError:
            return ToolResult(
                success=False,
                error="Source file does not exist.",
                error_code="NOT_FOUND",
            )


# ---------------------------------------------------------
# Delete File
# ---------------------------------------------------------

class DeleteFileTool(Tool):
    name = "filesystem.delete_file"
    description = (
        "Delete a file or folder. "
        "ALWAYS requires user confirmation."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
            }
        },
        "required": ["path"],
    }

    permission_level = PermissionLevel.DANGEROUS

    def confirmation_description(
        self,
        path: str,
        **_,
    ) -> str:
        return f"Permanently delete {path}"

    async def execute(self, path: str) -> ToolResult:
        ok, reason = _check_allowed(path)

        if not ok:
            return ToolResult(
                success=False,
                error=reason,
                error_code="PATH_NOT_ALLOWED",
            )

        target = _normalize_path(path)

        try:
            if not target.exists():
                return ToolResult(
                    success=False,
                    error="Path does not exist.",
                    error_code="NOT_FOUND",
                )

            if target.is_dir():
                shutil.rmtree(target)
            else:
                os.remove(target)

            return ToolResult(
                success=True,
                data={
                    "deleted": str(target),
                },
            )

        except PermissionError:
            return ToolResult(
                success=False,
                error="Permission denied while deleting this path.",
                error_code="PERMISSION_DENIED",
            )


# ---------------------------------------------------------
# Register All Filesystem Tools
# ---------------------------------------------------------

ALL_FILESYSTEM_TOOLS = [
    ListFilesTool(),
    SearchFilesTool(),
    ReadFileTool(),
    WriteFileTool(),
    CreateFolderTool(),
    CopyFileTool(),
    MoveFileTool(),
    DeleteFileTool(),
]