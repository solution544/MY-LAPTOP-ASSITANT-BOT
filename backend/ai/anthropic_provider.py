"""
Concrete AIProvider backed by the real Anthropic Messages API.

This is the first working implementation (Phase 2), used to validate the
whole chat pipeline end-to-end: frontend -> WebSocket -> FastAPI ->
AgentOrchestrator -> AIProvider -> Anthropic API -> back to the UI.
"""

from typing import AsyncIterator, Optional

import anthropic

from backend.ai.base import (
    AIProvider, ChatMessage, ChatResponse, ToolCallRequest, ToolDefinition,
)
from backend.core.logging import logger


class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file — "
                "see .env.example."
            )
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    def _to_anthropic_messages(self, messages: list[ChatMessage]) -> list[dict]:
        """
        Anthropic's API takes the system prompt separately (not as a message
        role), and tool results must be sent as a "user" message containing a
        `tool_result` content block referencing the original tool_use id — a
        plain role="tool" message (used internally by the orchestrator, and
        by other providers) has no direct equivalent, so it's translated here.
        """
        converted = []
        for m in messages:
            if m.role == "assistant" and m.tool_calls:
                blocks = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for call in m.tool_calls:
                    blocks.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments})
                converted.append({"role": "assistant", "content": blocks})
            elif m.role in ("user", "assistant"):
                converted.append({"role": m.role, "content": m.content})
            elif m.role == "tool":
                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.tool_call_id,
                        "content": m.content,
                    }],
                })
            # "system" role messages are ignored here — system_prompt param handles that.
        return converted

    def _to_anthropic_tools(self, tools: Optional[list[ToolDefinition]]) -> list[dict]:
        if not tools:
            return []
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> ChatResponse:
        kwargs = dict(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=self._to_anthropic_messages(messages),
        )
        if system_prompt:
            kwargs["system"] = system_prompt
        anthropic_tools = self._to_anthropic_tools(tools)
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.APIError as exc:
            logger.error(f"Anthropic API error: {exc}")
            raise

        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCallRequest(id=block.id, name=block.name, arguments=block.input))

        return ChatResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            raw=response,
        )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        kwargs = dict(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=self._to_anthropic_messages(messages),
        )
        if system_prompt:
            kwargs["system"] = system_prompt
        anthropic_tools = self._to_anthropic_tools(tools)
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    def supports_vision(self) -> bool:
        return True

    async def analyze_image(self, image_base64: str, prompt: str, media_type: str = "image/png") -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_base64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return "".join(block.text for block in response.content if block.type == "text")
