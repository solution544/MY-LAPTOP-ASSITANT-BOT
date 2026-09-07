from backend.security.permissions import PermissionLevel
from backend.tools.base import Tool, ToolResult
from backend.vision.capture import screen_capture_service
from backend.vision.vision_service import vision_service


class TakeScreenshotTool(Tool):
    name = "computer.take_screenshot"
    description = "Capture the screen and return it as base64 PNG (for the AI's own reference, not shown raw to the user)."
    input_schema = {"type": "object", "properties": {}}
    permission_level = PermissionLevel.LOW_RISK

    async def execute(self) -> ToolResult:
        png_bytes = screen_capture_service.capture_screen()
        return ToolResult(success=True, data={"image_base64": screen_capture_service.to_base64(png_bytes)})


class AnalyzeScreenTool(Tool):
    name = "vision.analyze_screen"
    description = "Take a screenshot and have the vision model answer a question about what's on screen."
    input_schema = {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}
    permission_level = PermissionLevel.LOW_RISK

    async def execute(self, question: str, **kwargs) -> ToolResult:
        try:
            answer = await vision_service.describe_screen(question)
            return ToolResult(success=True, data={"answer": answer})
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc), error_code="VISION_FAILED")


ALL_VISION_TOOLS = [TakeScreenshotTool(), AnalyzeScreenTool()]
