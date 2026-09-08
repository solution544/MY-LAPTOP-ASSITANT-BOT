"""
Groq AI provider.

Implements the provider-agnostic AIProvider interface using
the official Groq Python SDK.
"""

import json
from typing import AsyncIterator, Optional

from groq import AsyncGroq

from backend.ai.base import (
    AIProvider,
    ChatMessage,
    ChatResponse,
    ToolCallRequest,
    ToolDefinition,
)


class GroqProvider(AIProvider):
    """Groq implementation of the AIProvider interface."""

    def __init__(
        self,
        api_key: str,
        model: str,
    ):
        if not api_key:
            raise ValueError("GROQ_API_KEY is not configured.")

        self.client = AsyncGroq(api_key=api_key)
        self.model = model

    # ---------------------------------------------------------
    # Message conversion
    # ---------------------------------------------------------

    def _convert_messages(
        self,
        messages: list[ChatMessage],
        system_prompt: Optional[str] = None,
    ) -> list[dict]:
        result = []

        if system_prompt:
            result.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        for message in messages:
            if message.role == "tool":
                result.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.tool_call_id,
                        "content": message.content,
                    }
                )

            elif message.role == "assistant":
                item: dict[str, object] = {
                    "role": "assistant",
                    "content": message.content or "",
                }

                if message.tool_calls:
                    item["tool_calls"] = [
                        {
                            "id": tool.id,
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "arguments": json.dumps(
                                    tool.arguments
                                ),
                            },
                        }
                        for tool in message.tool_calls
                    ]

                result.append(item)

            else:
                result.append(
                    {
                        "role": message.role,
                        "content": message.content,
                    }
                )

        return result

    # ---------------------------------------------------------
    # Tool conversion
    # ---------------------------------------------------------

    def _convert_tools(
        self,
        tools: Optional[list[ToolDefinition]],
    ) -> Optional[list[dict]]:
        if not tools:
            return None

        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in tools
        ]

    # ---------------------------------------------------------
    # Chat
    # ---------------------------------------------------------

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> ChatResponse:

        converted_messages = self._convert_messages(
            messages,
            system_prompt,
        )

        converted_tools = self._convert_tools(tools)

        kwargs = {
            "model": self.model,
            "messages": converted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if converted_tools:
            kwargs["tools"] = converted_tools
            kwargs["tool_choice"] = "auto"

        response = await self.client.chat.completions.create(
            **kwargs
        )

        choice = response.choices[0]
        message = choice.message

        print("\n========== GROQ TOOL DEBUG ==========")
        print("MODEL:", self.model)
        print("CONTENT:", repr(message.content))
        print("TOOL CALLS:", message.tool_calls)
        print("=====================================\n")

        tool_calls = []

        if message.tool_calls:
            for tool_call in message.tool_calls:
                try:
                    arguments = json.loads(
                        tool_call.function.arguments
                    )
                except json.JSONDecodeError:
                    arguments = {}

                tool_calls.append(
                    ToolCallRequest(
                        id=tool_call.id,
                        name=tool_call.function.name,
                        arguments=arguments,
                    )
                )

        stop_reason = getattr(
            choice,
            "finish_reason",
            None,
        )

        return ChatResponse(
            text=message.content or "",
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            raw=response,
        )

    # ---------------------------------------------------------
    # Streaming
    # ---------------------------------------------------------

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:

        converted_messages = self._convert_messages(
            messages,
            system_prompt,
        )

        converted_tools = self._convert_tools(tools)

        kwargs = {
            "model": self.model,
            "messages": converted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        if converted_tools:
            kwargs["tools"] = converted_tools
            kwargs["tool_choice"] = "auto"

        stream = await self.client.chat.completions.create(
            **kwargs
        )

        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            if delta.content:
                yield delta.content

    # ---------------------------------------------------------
    # Vision
    # ---------------------------------------------------------

    def supports_vision(self) -> bool:
        """
        Return True for Groq models that support vision.

        This can be expanded when additional Groq vision models
        are added to the project.
        """

        vision_models = {
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "meta-llama/llama-4-maverick-17b-128e-instruct",
        }

        return self.model in vision_models

    async def analyze_image(
        self,
        image_base64: str,
        prompt: str,
        media_type: str = "image/png",
    ) -> str:

        if not self.supports_vision():
            raise NotImplementedError(
                f"Groq model '{self.model}' does not support vision."
            )

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    f"data:{media_type};base64,"
                                    f"{image_base64}"
                                )
                            },
                        },
                    ],
                }
            ],
            max_tokens=4096,
            temperature=0.7,
        )

        return response.choices[0].message.content or ""