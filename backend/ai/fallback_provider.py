from typing import AsyncIterator, Optional

from backend.ai.base import (
    AIProvider,
    ChatMessage,
    ChatResponse,
    ToolDefinition,
)


class FallbackAIProvider(AIProvider):
    def __init__(
        self,
        primary: AIProvider,
        backup: AIProvider,
    ):
        self.primary = primary
        self.backup = backup

        # Once the primary provider fails during a task,
        # stay on the backup provider for the rest of that task.
        self._use_backup = False

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> ChatResponse:

        # ---------------------------------------------------------
        # BACKUP MODE
        # ---------------------------------------------------------

        if self._use_backup:
            return await self.backup.chat(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        # ---------------------------------------------------------
        # PRIMARY MODE
        # ---------------------------------------------------------

        try:
            return await self.primary.chat(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        except Exception as primary_error:

            print("[AI FALLBACK] Primary provider failed.")
            print(f"[AI FALLBACK] Error: {primary_error}")
            print("[AI FALLBACK] Switching to backup provider...")

            # Stay with the backup provider for subsequent
            # agent steps so provider-specific tool history
            # is not mixed together.
            self._use_backup = True

            return await self.backup.chat(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:

        # ---------------------------------------------------------
        # BACKUP MODE
        # ---------------------------------------------------------

        if self._use_backup:
            async for chunk in self.backup.stream_chat(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            ):
                yield chunk

            return

        # ---------------------------------------------------------
        # PRIMARY MODE
        # ---------------------------------------------------------

        try:

            async for chunk in self.primary.stream_chat(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            ):
                yield chunk

        except Exception as primary_error:

            print("[AI FALLBACK] Primary streaming provider failed.")
            print(f"[AI FALLBACK] Error: {primary_error}")
            print("[AI FALLBACK] Switching to backup provider...")

            self._use_backup = True

            async for chunk in self.backup.stream_chat(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            ):
                yield chunk

    def supports_vision(self) -> bool:

        if self._use_backup:
            return self.backup.supports_vision()

        return (
            self.primary.supports_vision()
            or self.backup.supports_vision()
        )

    async def analyze_image(
        self,
        image_base64: str,
        prompt: str,
        media_type: str = "image/png",
    ) -> str:

        # ---------------------------------------------------------
        # BACKUP MODE
        # ---------------------------------------------------------

        if self._use_backup:
            return await self.backup.analyze_image(
                image_base64,
                prompt,
                media_type,
            )

        # ---------------------------------------------------------
        # PRIMARY MODE
        # ---------------------------------------------------------

        try:

            return await self.primary.analyze_image(
                image_base64,
                prompt,
                media_type,
            )

        except Exception as primary_error:

            print("[AI FALLBACK] Primary vision provider failed.")
            print(f"[AI FALLBACK] Error: {primary_error}")

            if not self.backup.supports_vision():
                raise primary_error

            print("[AI FALLBACK] Switching vision to backup provider...")

            self._use_backup = True

            return await self.backup.analyze_image(
                image_base64,
                prompt,
                media_type,
            )