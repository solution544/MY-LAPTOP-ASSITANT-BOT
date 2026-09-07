"""
Filesystem tools (spec section 15).

Every tool here resolves the target path and checks it against
`Settings.allowed_folders_list` / `blocked_folders_list` before touching
disk. If `ALLOWED_FOLDERS` is empty, filesystem tools refuse everything —
the user must explicitly opt folders in via Settings before Solution AI can
read/write anything, rather than defaulting to "everything is allowed".
"""

import os
import shutil
from pathlib import Path

from backend.core.config import get_settings
from backend.security.permissions import PermissionLevel
from backend.tools.base import Tool, ToolResult


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _check_allowed(path_str: str) -> tuple[bool, str | None]:
    settings = get_settings()
    path = Path(path_str)

    if not settings.allowed_folders_list:
        return False, "No folders are configured as allowed. Add one in Settings > Security > Allowed folders."

    for blocked in settings.blocked_folders_list:
        if _is_within(path, Path(blocked)):
            return False, f"'{path}' is inside a blocked folder ({blocked})."

    for allowed in settings.allowed_folders_list:
        if _is_within(path, Path(allowed)):
            return True, None

    return False, f"'{path}' is not inside any allowed folder."


class ListFilesTool(Tool):
    name = "filesystem.list_files"
    description = "List files and folders inside a directory."
    input_schema = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, path: str) -> ToolResult:
        ok, reason = _check_allowed(path)
        if not ok:
            return ToolResult(success=False, error=reason, error_code="PATH_NOT_ALLOWED")
        try:
            entries = [
                {"name": e.name, "is_dir": e.is_dir(), "size": e.stat().st_size if e.is_file() else None}
                for e in Path(path).iterdir()
            ]
            return ToolResult(success=True, data=entries)
        except FileNotFoundError:
            return ToolResult(success=False, error="Path does not exist", error_code="NOT_FOUND")


class SearchFilesTool(Tool):
    name = "filesystem.search_files"
    description = "Recursively search for files by name pattern within an allowed folder."
    input_schema = {
        "type": "object",
        "properties": {"root": {"type": "string"}, "pattern": {"type": "string"}},
        "required": ["root", "pattern"],
    }
    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, root: str, pattern: str) -> ToolResult:
        ok, reason = _check_allowed(root)
        if not ok:
            return ToolResult(success=False, error=reason, error_code="PATH_NOT_ALLOWED")
        matches = [str(p) for p in Path(root).rglob(pattern)]
        return ToolResult(success=True, data=matches[:200])  # cap to avoid dumping huge trees


class ReadFileTool(Tool):
    name = "filesystem.read_file"
    description = "Read the text contents of a file."
    input_schema = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, path: str) -> ToolResult:
        ok, reason = _check_allowed(path)
        if not ok:
            return ToolResult(success=False, error=reason, error_code="PATH_NOT_ALLOWED")
        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
            return ToolResult(success=True, data=content[:200_000])  # cap per-read size
        except FileNotFoundError:
            return ToolResult(success=False, error="File does not exist", error_code="NOT_FOUND")
        except IsADirectoryError:
            return ToolResult(success=False, error="Path is a directory, not a file", error_code="IS_DIRECTORY")


class WriteFileTool(Tool):
    name = "filesystem.write_file"
    description = "Write (overwrite) text content to a file."
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    }
    permission_level = PermissionLevel.SENSITIVE

    def confirmation_description(self, path: str, content: str, **_) -> str:
        return f"Write {len(content)} characters to {path}"

    async def execute(self, path: str, content: str) -> ToolResult:
        ok, reason = _check_allowed(path)
        if not ok:
            return ToolResult(success=False, error=reason, error_code="PATH_NOT_ALLOWED")
        Path(path).write_text(content, encoding="utf-8")
        return ToolResult(success=True, data={"path": path, "bytes_written": len(content.encode('utf-8'))})


class CreateFolderTool(Tool):
    name = "filesystem.create_folder"
    description = "Create a new folder (including parent folders if needed)."
    input_schema = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, path: str) -> ToolResult:
        ok, reason = _check_allowed(path)
        if not ok:
            return ToolResult(success=False, error=reason, error_code="PATH_NOT_ALLOWED")
        Path(path).mkdir(parents=True, exist_ok=True)
        return ToolResult(success=True, data={"path": path})


class CopyFileTool(Tool):
    name = "filesystem.copy_file"
    description = "Copy a file from one path to another."
    input_schema = {
        "type": "object",
        "properties": {"source": {"type": "string"}, "destination": {"type": "string"}},
        "required": ["source", "destination"],
    }
    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, source: str, destination: str) -> ToolResult:
        for p in (source, destination):
            ok, reason = _check_allowed(p)
            if not ok:
                return ToolResult(success=False, error=reason, error_code="PATH_NOT_ALLOWED")
        shutil.copy2(source, destination)
        return ToolResult(success=True, data={"source": source, "destination": destination})


class MoveFileTool(Tool):
    name = "filesystem.move_file"
    description = "Move or rename a file."
    input_schema = {
        "type": "object",
        "properties": {"source": {"type": "string"}, "destination": {"type": "string"}},
        "required": ["source", "destination"],
    }
    permission_level = PermissionLevel.SENSITIVE

    def confirmation_description(self, source: str, destination: str, **_) -> str:
        return f"Move {source} -> {destination}"

    async def execute(self, source: str, destination: str) -> ToolResult:
        for p in (source, destination):
            ok, reason = _check_allowed(p)
            if not ok:
                return ToolResult(success=False, error=reason, error_code="PATH_NOT_ALLOWED")
        shutil.move(source, destination)
        return ToolResult(success=True, data={"source": source, "destination": destination})


class DeleteFileTool(Tool):
    name = "filesystem.delete_file"
    description = "Delete a file or folder. ALWAYS requires user confirmation."
    input_schema = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}
    permission_level = PermissionLevel.DANGEROUS

    def confirmation_description(self, path: str, **_) -> str:
        return f"Permanently delete {path}"

    async def execute(self, path: str) -> ToolResult:
        ok, reason = _check_allowed(path)
        if not ok:
            return ToolResult(success=False, error=reason, error_code="PATH_NOT_ALLOWED")
        target = Path(path)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            os.remove(target)
        return ToolResult(success=True, data={"deleted": path})


ALL_FILESYSTEM_TOOLS = [
    ListFilesTool(), SearchFilesTool(), ReadFileTool(), WriteFileTool(),
    CreateFolderTool(), CopyFileTool(), MoveFileTool(), DeleteFileTool(),
]
