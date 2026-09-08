
"""
ComputerControlService (spec section 11).

Windows-focused computer control using:
- pyautogui for mouse/keyboard/screen interaction
- pygetwindow for window management
- psutil for process management
- subprocess for application launching

Imports that require a graphical environment are kept lazy where appropriate
so the backend can still import safely in headless environments.
"""

import platform
import subprocess
import time

from backend.security.permissions import PermissionLevel
from backend.tools.base import Tool, ToolResult


def _pyautogui():
    import pyautogui

    pyautogui.FAILSAFE = True
    return pyautogui


# ---------------------------------------------------------------------------
# Mouse
# ---------------------------------------------------------------------------

class MoveMouseTool(Tool):
    name = "computer.move_mouse"
    description = "Move the mouse cursor to absolute screen coordinates."

    input_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
        },
        "required": ["x", "y"],
    }

    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, **kwargs) -> ToolResult:
        x = kwargs["x"]
        y = kwargs["y"]

        _pyautogui().moveTo(
            x,
            y,
            duration=0.2,
        )

        return ToolResult(
            success=True,
            data={
                "x": x,
                "y": y,
            },
        )


class ClickTool(Tool):
    name = "computer.click"
    description = (
        "Click the mouse at coordinates "
        "(or current position if omitted)."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
        },
    }

    permission_level = PermissionLevel.SENSITIVE

    def confirmation_description(self, **kwargs) -> str:
        x = kwargs.get("x")
        y = kwargs.get("y")

        if x is not None and y is not None:
            return f"Click at ({x}, {y})"

        return "Click at current mouse position"

    async def execute(self, **kwargs) -> ToolResult:
        x = kwargs.get("x")
        y = kwargs.get("y")

        pg = _pyautogui()

        if x is not None and y is not None:
            pg.click(x, y)
        else:
            pg.click()

        return ToolResult(
            success=True,
            data={
                "x": x,
                "y": y,
            },
        )


class DoubleClickTool(Tool):
    name = "computer.double_click"
    description = "Double-click at coordinates."

    input_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
        },
        "required": ["x", "y"],
    }

    permission_level = PermissionLevel.SENSITIVE

    def confirmation_description(self, **kwargs) -> str:
        x = kwargs["x"]
        y = kwargs["y"]

        return f"Double-click at ({x}, {y})"

    async def execute(self, **kwargs) -> ToolResult:
        x = kwargs["x"]
        y = kwargs["y"]

        _pyautogui().doubleClick(
            x,
            y,
        )

        return ToolResult(
            success=True,
            data={
                "x": x,
                "y": y,
            },
        )


class RightClickTool(Tool):
    name = "computer.right_click"
    description = "Right-click at coordinates."

    input_schema = {
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
        },
        "required": ["x", "y"],
    }

    permission_level = PermissionLevel.SENSITIVE

    def confirmation_description(self, **kwargs) -> str:
        x = kwargs["x"]
        y = kwargs["y"]

        return f"Right-click at ({x}, {y})"

    async def execute(self, **kwargs) -> ToolResult:
        x = kwargs["x"]
        y = kwargs["y"]

        _pyautogui().rightClick(
            x,
            y,
        )

        return ToolResult(
            success=True,
            data={
                "x": x,
                "y": y,
            },
        )


class DragTool(Tool):
    name = "computer.drag"
    description = "Drag the mouse from a start point to an end point."

    input_schema = {
        "type": "object",
        "properties": {
            "start_x": {"type": "integer"},
            "start_y": {"type": "integer"},
            "end_x": {"type": "integer"},
            "end_y": {"type": "integer"},
        },
        "required": [
            "start_x",
            "start_y",
            "end_x",
            "end_y",
        ],
    }

    permission_level = PermissionLevel.SENSITIVE

    def confirmation_description(self, **kwargs) -> str:
        start_x = kwargs["start_x"]
        start_y = kwargs["start_y"]
        end_x = kwargs["end_x"]
        end_y = kwargs["end_y"]

        return (
            f"Drag from "
            f"({start_x},{start_y}) "
            f"to "
            f"({end_x},{end_y})"
        )

    async def execute(self, **kwargs) -> ToolResult:
        start_x = kwargs["start_x"]
        start_y = kwargs["start_y"]
        end_x = kwargs["end_x"]
        end_y = kwargs["end_y"]

        pg = _pyautogui()

        pg.moveTo(
            start_x,
            start_y,
        )

        pg.dragTo(
            end_x,
            end_y,
            duration=0.3,
        )

        return ToolResult(
            success=True,
            data={
                "from": [
                    start_x,
                    start_y,
                ],
                "to": [
                    end_x,
                    end_y,
                ],
            },
        )


class ScrollTool(Tool):
    name = "computer.scroll"
    description = "Scroll the mouse wheel. Positive = up, negative = down."

    input_schema = {
        "type": "object",
        "properties": {
            "amount": {"type": "integer"},
        },
        "required": ["amount"],
    }

    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, **kwargs) -> ToolResult:
        amount = kwargs["amount"]

        _pyautogui().scroll(amount)

        return ToolResult(
            success=True,
            data={
                "amount": amount,
            },
        )


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------

class TypeTextTool(Tool):
    name = "computer.type_text"
    description = "Type text at the current cursor/focus position."

    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
        },
        "required": ["text"],
    }

    permission_level = PermissionLevel.SENSITIVE

    def confirmation_description(self, **kwargs) -> str:
        text = kwargs["text"]

        preview = (
            text
            if len(text) <= 60
            else text[:57] + "..."
        )

        return f'Type: "{preview}"'

    async def execute(self, **kwargs) -> ToolResult:
        text = kwargs["text"]

        if not isinstance(text, str):
            return ToolResult(
                success=False,
                error="Text must be a string.",
                error_code="INVALID_TEXT",
            )

        if not text:
            return ToolResult(
                success=False,
                error="Text cannot be empty.",
                error_code="EMPTY_TEXT",
            )

        try:
            pg = _pyautogui()

            pg.typewrite(
                text,
                interval=0.01,
            )

            return ToolResult(
                success=True,
                data={
                    "characters_typed": len(text),
                    "text": text,
                },
            )

        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Could not type text: {exc}",
                error_code="TYPE_TEXT_FAILED",
            )


class PressKeyTool(Tool):
    name = "computer.press_key"
    description = (
        "Press a single key "
        "(e.g. 'enter', 'esc', 'tab', 'f5')."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
        },
        "required": ["key"],
    }

    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, **kwargs) -> ToolResult:
        key = kwargs["key"]

        _pyautogui().press(key)

        return ToolResult(
            success=True,
            data={
                "key": key,
            },
        )


class HotkeyTool(Tool):
    name = "computer.hotkey"
    description = (
        "Press a key combination, "
        "e.g. ['ctrl', 'c']."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "keys": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
        },
        "required": ["keys"],
    }

    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, **kwargs) -> ToolResult:
        keys = kwargs["keys"]

        _pyautogui().hotkey(
            *keys,
        )

        return ToolResult(
            success=True,
            data={
                "keys": keys,
            },
        )


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------

class GetScreenSizeTool(Tool):
    name = "computer.get_screen_size"
    description = "Get the primary screen's resolution."

    input_schema = {
        "type": "object",
        "properties": {},
    }

    permission_level = PermissionLevel.SAFE

    async def execute(self, **kwargs) -> ToolResult:
        width, height = _pyautogui().size()

        return ToolResult(
            success=True,
            data={
                "width": width,
                "height": height,
            },
        )


class GetActiveWindowTool(Tool):
    name = "computer.get_active_window"
    description = "Get the title of the currently focused window."

    input_schema = {
        "type": "object",
        "properties": {},
    }

    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, **kwargs) -> ToolResult:
        import pygetwindow as gw

        try:
            win = gw.getActiveWindow()

            return ToolResult(
                success=True,
                data={
                    "title": (
                        win.title
                        if win
                        else None
                    ),
                },
            )

        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Could not get active window: {exc}",
                error_code="ACTIVE_WINDOW_FAILED",
            )


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

_APP_COMMANDS = {
    # Browsers
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "firefox": "firefox",

    # Development
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",

    # Windows
    "notepad": "notepad",
    "calculator": "calc",
    "explorer": "explorer",
    "file explorer": "explorer",
    "paint": "mspaint",
    "task manager": "taskmgr",
    "command prompt": "cmd",
    "cmd": "cmd",
    "powershell": "powershell",

    # Media
    "spotify": "spotify",
    "vlc": "vlc",
    "tiktok": "tiktok",

    # Communication
    "teams": "teams",
    "discord": "discord",
    "whatsapp": "whatsapp",

    # Microsoft Office
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
}


class OpenApplicationTool(Tool):
    name = "computer.open_application"

    description = (
        "Open a desktop application by name and "
        "bring its window to the foreground."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
            },
        },
        "required": ["name"],
    }

    permission_level = PermissionLevel.SAFE

    async def execute(self, **kwargs) -> ToolResult:
        import pygetwindow as gw

        name = kwargs["name"].strip()

        if not name:
            return ToolResult(
                success=False,
                error="Application name cannot be empty.",
                error_code="INVALID_APPLICATION_NAME",
            )

        command = _APP_COMMANDS.get(name.lower()) or name

        try:
            # ------------------------------------------------------
            # Get windows before launching
            # ------------------------------------------------------

            existing_windows = set()

            try:
                for window in gw.getAllWindows():
                    title = (
                        window.title or ""
                    ).strip()

                    if title:
                        existing_windows.add(
                            title.lower()
                        )

            except Exception:
                pass

            # ------------------------------------------------------
            # Launch application
            # ------------------------------------------------------

            if platform.system() == "Windows":
                subprocess.Popen(
                    [
                        "cmd",
                        "/c",
                        "start",
                        "",
                        command,
                    ],
                    shell=False,
                )
            else:
                subprocess.Popen(
                    [command]
                )

            # ------------------------------------------------------
            # Wait for application window
            # ------------------------------------------------------

            time.sleep(1.5)

            # ------------------------------------------------------
            # Find application window
            # ------------------------------------------------------

            try:
                windows = gw.getAllWindows()
            except Exception:
                windows = []

            target_name = name.lower()
            target_window = None

            # First: newly created matching window
            for window in windows:
                title = (
                    window.title or ""
                ).strip()

                title_lower = title.lower()

                if not title:
                    continue

                if title_lower not in existing_windows:
                    if (
                        target_name in title_lower
                        or title_lower in target_name
                    ):
                        target_window = window
                        break

            # Second: existing matching window
            if target_window is None:
                for window in windows:
                    title = (
                        window.title or ""
                    ).strip()

                    title_lower = title.lower()

                    if not title:
                        continue

                    if target_name in title_lower:
                        target_window = window
                        break

            # ------------------------------------------------------
            # Aliases
            # ------------------------------------------------------

            if target_window is None:

                aliases = {
                    "notepad": [
                        "notepad",
                    ],
                    "calculator": [
                        "calculator",
                        "calc",
                    ],
                    "paint": [
                        "paint",
                    ],
                    "chrome": [
                        "chrome",
                    ],
                    "google chrome": [
                        "chrome",
                    ],
                    "edge": [
                        "edge",
                    ],
                    "microsoft edge": [
                        "edge",
                    ],
                    "vs code": [
                        "visual studio code",
                        "vs code",
                    ],
                    "vscode": [
                        "visual studio code",
                        "vs code",
                    ],
                    "visual studio code": [
                        "visual studio code",
                        "vs code",
                    ],
                }

                possible_titles = aliases.get(
                    target_name,
                    [],
                )

                for window in windows:
                    title = (
                        window.title or ""
                    ).strip().lower()

                    if not title:
                        continue

                    if any(
                        alias in title
                        for alias in possible_titles
                    ):
                        target_window = window
                        break

            # ------------------------------------------------------
            # Force foreground focus using Windows API
            # ------------------------------------------------------

            focused = False

            if target_window is not None:

                try:
                    hwnd = target_window._hWnd

                    if platform.system() == "Windows":

                        import ctypes

                        user32 = ctypes.windll.user32

                        SW_RESTORE = 9

                        # Restore if minimized
                        user32.ShowWindow(
                            hwnd,
                            SW_RESTORE,
                        )

                        time.sleep(0.2)

                        # Get current foreground window
                        foreground_hwnd = (
                            user32.GetForegroundWindow()
                        )

                        # Get window thread IDs
                        current_thread = (
                            user32.GetWindowThreadProcessId(
                                foreground_hwnd,
                                None,
                            )
                        )

                        target_thread = (
                            user32.GetWindowThreadProcessId(
                                hwnd,
                                None,
                            )
                        )

                        # Attach input threads temporarily
                        if (
                            current_thread
                            and target_thread
                            and current_thread
                            != target_thread
                        ):
                            user32.AttachThreadInput(
                                current_thread,
                                target_thread,
                                True,
                            )

                        # Bring window to foreground
                        user32.BringWindowToTop(
                            hwnd
                        )

                        user32.SetForegroundWindow(
                            hwnd
                        )

                        user32.SetFocus(
                            hwnd
                        )

                        # Detach threads
                        if (
                            current_thread
                            and target_thread
                            and current_thread
                            != target_thread
                        ):
                            user32.AttachThreadInput(
                                current_thread,
                                target_thread,
                                False,
                            )

                        time.sleep(0.5)

                        # Verify actual foreground window
                        active_hwnd = (
                            user32.GetForegroundWindow()
                        )

                        focused = (
                            active_hwnd == hwnd
                        )

                    else:
                        target_window.activate()

                        time.sleep(0.5)

                        focused = True

                except Exception as focus_error:
                    focused = False

                    print(
                        f"[FOCUS ERROR] "
                        f"{focus_error}"
                    )

            return ToolResult(
                success=True,
                data={
                    "opened": name,
                    "focused": focused,
                    "window_title": (
                        target_window.title
                        if target_window is not None
                        else None
                    ),
                },
            )

        except Exception as exc:
            return ToolResult(
                success=False,
                error=(
                    f"Could not open '{name}': "
                    f"{exc}"
                ),
                error_code="APPLICATION_NOT_FOUND",
            )


class CloseApplicationTool(Tool):
    name = "computer.close_application"

    description = (
        "Close a running application by process name "
        "(e.g. 'chrome.exe')."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
            },
        },
        "required": ["name"],
    }

    permission_level = PermissionLevel.SENSITIVE

    def confirmation_description(self, **kwargs) -> str:
        name = kwargs["name"]

        return f"Close all '{name}' processes"

    async def execute(self, **kwargs) -> ToolResult:
        import psutil

        name = kwargs["name"]
        target = name.lower()

        closed = 0

        for proc in psutil.process_iter(["name"]):

            proc_name = (
                proc.info.get("name")
                or ""
            ).lower()

            if target in proc_name:

                try:
                    proc.terminate()
                    closed += 1

                except psutil.NoSuchProcess:
                    pass

        if closed == 0:
            return ToolResult(
                success=False,
                error=(
                    f"No running process matched '{name}'"
                ),
                error_code="NOT_RUNNING",
            )

        return ToolResult(
            success=True,
            data={
                "processes_closed": closed,
            },
        )


class ListRunningApplicationsTool(Tool):
    name = "computer.list_running_applications"
    description = "List currently running application processes."

    input_schema = {
        "type": "object",
        "properties": {},
    }

    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, **kwargs) -> ToolResult:
        import psutil

        names = sorted(
            {
                p.info["name"]
                for p in psutil.process_iter(["name"])
                if p.info.get("name")
            }
        )

        return ToolResult(
            success=True,
            data=names,
        )


# ---------------------------------------------------------------------------
# All Computer Tools
# ---------------------------------------------------------------------------

ALL_COMPUTER_TOOLS = [
    MoveMouseTool(),
    ClickTool(),
    DoubleClickTool(),
    RightClickTool(),
    DragTool(),
    ScrollTool(),

    TypeTextTool(),
    PressKeyTool(),
    HotkeyTool(),

    GetScreenSizeTool(),
    GetActiveWindowTool(),

    OpenApplicationTool(),
    CloseApplicationTool(),
    ListRunningApplicationsTool(),
]