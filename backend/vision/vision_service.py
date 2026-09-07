"""
VisionService (spec section 12) — the "screenshot -> vision model -> analyze
-> AI response" pipeline. Kept separate from the ComputerAgent loop
(backend/agents/computer_agent.py) so plain "what's on my screen" questions
don't need the full agent loop.
"""

from backend.ai.provider_factory import get_ai_provider
from backend.vision.capture import screen_capture_service


class VisionService:
    async def describe_screen(self, question: str = "Describe what is on the screen and answer any implicit question in it.") -> str:
        png_bytes = screen_capture_service.capture_screen()
        image_b64 = screen_capture_service.to_base64(png_bytes)
        provider = get_ai_provider()
        if not provider.supports_vision():
            raise RuntimeError(f"Configured AI provider does not support vision.")
        return await provider.analyze_image(image_b64, question)

    async def describe_window(self, title_substring: str, question: str) -> str:
        png_bytes = screen_capture_service.capture_window(title_substring)
        image_b64 = screen_capture_service.to_base64(png_bytes)
        provider = get_ai_provider()
        return await provider.analyze_image(image_b64, question)


vision_service = VisionService()
