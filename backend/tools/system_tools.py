"""
System control tools (spec section 23). Read-only info tools are SAFE;
volume/brightness are LOW_RISK; lock is SENSITIVE; shutdown/restart are
DANGEROUS and always confirmed.
"""

import platform
import subprocess

from backend.security.permissions import PermissionLevel
from backend.tools.base import Tool, ToolResult


class GetSystemInformationTool(Tool):
    name = "system.get_system_information"
    description = "Get OS, CPU, memory, disk, and battery information in one call."
    input_schema = {"type": "object", "properties": {}}
    permission_level = PermissionLevel.SAFE

    async def execute(self, **kwargs) -> ToolResult:
        import psutil
        battery = psutil.sensors_battery()
        return ToolResult(success=True, data={
            "os": f"{platform.system()} {platform.release()}",
            "cpu_percent": psutil.cpu_percent(interval=0.3),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent,
            "battery_percent": battery.percent if battery else None,
            "battery_plugged": battery.power_plugged if battery else None,
        })


class GetNetworkStatusTool(Tool):
    name = "system.get_network_status"
    description = "Check whether the machine currently has network connectivity."
    input_schema = {"type": "object", "properties": {}}
    permission_level = PermissionLevel.SAFE

    async def execute(self, **kwargs) -> ToolResult:
        import socket
        try:
            socket.create_connection(("1.1.1.1", 53), timeout=2).close()
            return ToolResult(success=True, data={"online": True})
        except OSError:
            return ToolResult(success=True, data={"online": False})


class GetSetVolumeTool(Tool):
    name = "system.set_volume"
    description = "Set system volume (0-100)."
    input_schema = {"type": "object", "properties": {"level": {"type": "integer", "minimum": 0, "maximum": 100}}, "required": ["level"]}
    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, **kwargs) -> ToolResult:
        level = kwargs["level"]
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            volume.SetMasterVolumeLevelScalar(  # type: ignore[attr-defined]
                max(0, min(level, 100)) / 100, None
            )
            return ToolResult(success=True, data={"level": level})
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"Volume control unavailable: {exc}", error_code="VOLUME_CONTROL_FAILED")

class LockPCTool(Tool):
    name = "system.lock_pc"
    description = "Lock the computer (Windows: Win+L)."
    input_schema = {"type": "object", "properties": {}}
    permission_level = PermissionLevel.SENSITIVE

    def confirmation_description(self, **_) -> str:
        return "Lock this computer"

    async def execute(self, **_) -> ToolResult:
        if platform.system() == "Windows":
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return ToolResult(success=True, data={"locked": True})

        return ToolResult(
            success=False,
            error="Lock is only implemented for Windows",
            error_code="UNSUPPORTED_PLATFORM",
        )


class ShutdownPCTool(Tool):
    name = "system.shutdown_pc"
    description = "Shut down the computer."
    input_schema = {"type": "object", "properties": {}}
    permission_level = PermissionLevel.DANGEROUS

    def confirmation_description(self, **_) -> str:
        return "Shut down this computer"

    async def execute(self, **_) -> ToolResult:
        if platform.system() != "Windows":
            return ToolResult(success=False, error="Shutdown is only implemented for Windows", error_code="UNSUPPORTED_PLATFORM")
        try:
            subprocess.run(["shutdown", "/s", "/t", "0"], check=True)
            return ToolResult(success=True, data={"shutdown": True})
        except (OSError, subprocess.SubprocessError) as exc:
            return ToolResult(success=False, error=f"Shutdown failed: {exc}", error_code="SHUTDOWN_FAILED")


class RestartPCTool(Tool):
    name = "system.restart_pc"
    description = "Restart the computer."
    input_schema = {"type": "object", "properties": {}}
    permission_level = PermissionLevel.DANGEROUS

    def confirmation_description(self, **_) -> str:
        return "Restart this computer"

    async def execute(self, **_) -> ToolResult:
        if platform.system() != "Windows":
            return ToolResult(success=False, error="Restart is only implemented for Windows", error_code="UNSUPPORTED_PLATFORM")
        try:
            subprocess.run(["shutdown", "/r", "/t", "0"], check=True)
            return ToolResult(success=True, data={"restarted": True})
        except (OSError, subprocess.SubprocessError) as exc:
            return ToolResult(success=False, error=f"Restart failed: {exc}", error_code="RESTART_FAILED")


ALL_SYSTEM_TOOLS = [
    GetSystemInformationTool(), GetNetworkStatusTool(), GetSetVolumeTool(),
    LockPCTool(), ShutdownPCTool(), RestartPCTool(),
]
