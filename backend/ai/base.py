"""
AIProvider — the abstraction the entire rest of the application talks to.

Nothing outside `backend/ai/` should import `anthropic`, `openai`, or any
other vendor SDK directly. Every provider implements this same interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Optional


@dataclass
class ToolDefinition:
    """A tool the AI is allowed to call, in provider-agnostic form."""

    name: str
    description: str
    input_schema: dict


@dataclass
class ToolCallRequest:
    """A tool invocation the model asked for."""

    id: str
    name: str
    arguments: dict


@dataclass
class ChatMessage:
    """
    Internal provider-agnostic chat message.

    response_items:
        Original provider response items that may need to be preserved
        between tool-calling steps.
    """

    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_call_id: Optional[str] = None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)

    # Raw provider response items.
    # Required by the OpenAI Responses API when continuing after
    # a function/tool call.
    response_items: list[Any] = field(default_factory=list)


@dataclass
class ChatResponse:
    """
    Normalized response shape returned by every provider.

    response_items:
        Provider-specific response items.

        OpenAI Responses API requires the original function_call items
        to be preserved and sent back together with their corresponding
        function_call_output items during multi-step tool calling.
    """

    text: str
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    stop_reason: Optional[str] = None
    raw: Any = None

    # Original provider response items returned by the model.
    response_items: list[Any] = field(default_factory=list)


class AIProvider(ABC):
    """Every concrete provider must implement this interface."""

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> ChatResponse:
        """
        Send a full conversation and get back one response.

        The response may contain tool calls.
        """
        raise NotImplementedError

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """
        Same as chat(), but yields text chunks as they arrive.
        """
        raise NotImplementedError

        # Makes this an async generator for type-checkers.
        yield  # pragma: no cover

    @abstractmethod
    def supports_vision(self) -> bool:
        raise NotImplementedError

    async def analyze_image(
        self,
        image_base64: str,
        prompt: str,
        media_type: str = "image/png",
    ) -> str:
        """
        Send an image + question to the model and return its text answer.

        Providers without vision support fail loudly rather than silently
        returning an incorrect result.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support vision"
        )