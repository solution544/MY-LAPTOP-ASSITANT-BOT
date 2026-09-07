"""
Notification system (spec section 24) — native Windows toast notifications
via `win10toast_click` (falls back to `plyer` cross-platform if unavailable).
"""

from backend.security.permissions import PermissionLevel
from backend.tools.base import Tool, ToolResult


class SendNotificationTool(Tool):
    name = "system.send_notification"
    description = "Show a desktop notification to the user."
    input_schema = {
        "type": "object",
        "properties": {"title": {"type": "string"}, "message": {"type": "string"}},
        "required": ["title", "message"],
    }
    permission_level = PermissionLevel.SAFE

    async def execute(self, title: str, message: str) -> ToolResult:
        try:
            from win10toast_click import ToastNotifier
            ToastNotifier().show_toast(title, message, duration=6, threaded=True)
        except Exception:
            try:
                from plyer import notification
                notification.notify(title=title, message=message, timeout=6)
            except Exception as exc:  # noqa: BLE001
                return ToolResult(success=False, error=f"Could not show notification: {exc}", error_code="NOTIFICATION_FAILED")
        return ToolResult(success=True, data={"title": title, "message": message})


ALL_NOTIFICATION_TOOLS = [SendNotificationTool()]
