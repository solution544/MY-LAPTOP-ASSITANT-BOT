from typing import AsyncIterator, Optional, cast
import json

from openai import AsyncOpenAI
from openai.types.responses import ResponseInputParam

from backend.ai.base import (
    AIProvider,
    ChatMessage,
    ChatResponse,
    ToolCallRequest,
    ToolDefinition,
)
from backend.core.logging import logger


class OpenAIProvider(AIProvider):
    """
    OpenAI Responses API implementation for Solution AI.

    Supports:
    - Normal chat
    - Function/tool calling
    - Multi-step tool execution
    - Streaming text
    - Vision/image analysis
    """

    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Add it to your .env file."
            )

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    # ------------------------------------------------------------------
    # INPUT CONVERSION
    # ------------------------------------------------------------------

    def _to_openai_input(
        self,
        messages: list[ChatMessage],
        system_prompt: Optional[str] = None,
    ) -> list[dict]:
        """
        Convert internal ChatMessage objects into Responses API input.

        Important:
        OpenAI Responses API requires the original function_call item
        to appear before its corresponding function_call_output item.

        We therefore preserve the important function_call fields instead
        of blindly replaying every field returned by the SDK.
        """

        converted: list[dict] = []

        if system_prompt:
            converted.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        for message in messages:

            # ----------------------------------------------------------
            # USER MESSAGE
            # ----------------------------------------------------------

            if message.role == "user":
                converted.append(
                    {
                        "role": "user",
                        "content": message.content,
                    }
                )

            # ----------------------------------------------------------
            # ASSISTANT MESSAGE
            # ----------------------------------------------------------

            elif message.role == "assistant":

                response_items = getattr(
                    message,
                    "response_items",
                    [],
                )

                if response_items:

                    for item in response_items:

                        # Convert SDK object to dictionary.
                        if hasattr(item, "model_dump"):
                            item_dict = item.model_dump(
                                exclude_none=True
                            )

                        elif isinstance(item, dict):
                            item_dict = dict(item)

                        else:
                            item_dict = {
                                "type": getattr(
                                    item,
                                    "type",
                                    None,
                                ),
                                "id": getattr(
                                    item,
                                    "id",
                                    None,
                                ),
                                "call_id": getattr(
                                    item,
                                    "call_id",
                                    None,
                                ),
                                "name": getattr(
                                    item,
                                    "name",
                                    None,
                                ),
                                "arguments": getattr(
                                    item,
                                    "arguments",
                                    None,
                                ),
                            }

                        item_type = item_dict.get("type")

                        # --------------------------------------------------
                        # FUNCTION CALL
                        # --------------------------------------------------

                        if item_type == "function_call":

                            function_call = {
                                "type": "function_call",
                                "call_id": item_dict.get(
                                    "call_id"
                                ),
                                "name": item_dict.get(
                                    "name"
                                ),
                                "arguments": item_dict.get(
                                    "arguments"
                                ),
                            }

                            # Preserve the item ID if one exists.
                            if item_dict.get("id"):
                                function_call["id"] = item_dict[
                                    "id"
                                ]

                            converted.append(function_call)

                        # --------------------------------------------------
                        # OTHER RESPONSE ITEMS
                        # --------------------------------------------------

                        else:

                            # Do not replay output-only status fields.
                            item_dict.pop(
                                "status",
                                None,
                            )

                            converted.append(item_dict)

                # Normal assistant text when there are no raw
                # Responses API items to preserve.
                elif message.content:

                    converted.append(
                        {
                            "role": "assistant",
                            "content": message.content,
                        }
                    )

            # ----------------------------------------------------------
            # TOOL RESULT
            # ----------------------------------------------------------

            elif message.role == "tool":

                if not message.tool_call_id:
                    logger.warning(
                        "Tool message has no tool_call_id."
                    )
                    continue

                converted.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id,
                        "output": message.content,
                    }
                )

        return converted

    # ------------------------------------------------------------------
    # TOOL CONVERSION
    # ------------------------------------------------------------------

    def _to_openai_tools(
        self,
        tools: Optional[list[ToolDefinition]],
    ) -> list[dict]:

        if not tools:
            return []

        converted_tools = []

        for tool in tools:

            converted_tools.append(
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                }
            )

        return converted_tools

    # ------------------------------------------------------------------
    # CHAT
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> ChatResponse:

        input_messages = self._to_openai_input(
            messages,
            system_prompt,
        )

        openai_tools = self._to_openai_tools(
            tools
        )

        kwargs = {
            "model": self._model,
            "input": input_messages,
            "max_output_tokens": max_tokens,
        }

        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        try:

            response = await self._client.responses.create(
                **kwargs
            )

        except Exception as exc:

            logger.error(
                f"OpenAI Responses API error: {exc}"
            )

            raise

        # --------------------------------------------------------------
        # READ MODEL OUTPUT
        # --------------------------------------------------------------

        tool_calls: list[ToolCallRequest] = []

        for item in response.output:

            item_type = getattr(
                item,
                "type",
                None,
            )

            if item_type != "function_call":
                continue

            try:

                arguments = json.loads(
                    item.arguments
                )

                print(
                    "[DEBUG TOOL CALL]",
                    item.name,
                    repr(arguments),
                )

            except (
                TypeError,
                json.JSONDecodeError,
            ):

                logger.warning(
                    f"Could not parse tool arguments for "
                    f"{item.name}: {item.arguments}"
                )

                arguments = {}

            tool_calls.append(
                ToolCallRequest(
                    id=item.call_id,
                    name=item.name,
                    arguments=arguments,
                )
            )

        # --------------------------------------------------------------
        # DEBUG INFORMATION
        # --------------------------------------------------------------

        logger.info(
            "OpenAI response received. "
            f"Tool calls: {len(tool_calls)}"
        )

        for call in tool_calls:

            logger.info(
                f"Tool requested: {call.name} "
                f"arguments={call.arguments}"
            )

        # --------------------------------------------------------------
        # RETURN RESPONSE
        # --------------------------------------------------------------

        return ChatResponse(
            text=response.output_text or "",
            tool_calls=tool_calls,
            stop_reason=None,
            raw=response,
            response_items=list(
                response.output
            ),
        )

    # ------------------------------------------------------------------
    # STREAMING CHAT
    # ------------------------------------------------------------------

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:

        input_messages = self._to_openai_input(
            messages,
            system_prompt,
        )

        openai_tools = self._to_openai_tools(
            tools
        )

        kwargs = {
            "model": self._model,
            "input": input_messages,
            "max_output_tokens": max_tokens,
        }

        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        try:

            async with self._client.responses.stream(
                **kwargs
            ) as stream:

                async for event in stream:

                    if event.type == "response.output_text.delta":
                        yield event.delta

                await stream.get_final_response()

        except Exception as exc:

            logger.error(
                f"OpenAI streaming error: {exc}"
            )

            raise

    # ------------------------------------------------------------------
    # VISION
    # ------------------------------------------------------------------

    def supports_vision(self) -> bool:
        return True

    async def analyze_image(
        self,
        image_base64: str,
        prompt: str,
        media_type: str = "image/png",
    ) -> str:

        try:

            response = await self._client.responses.create(
                model=self._model,
                input=cast(ResponseInputParam, [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "image_url": (
                                    f"data:{media_type};base64,"
                                    f"{image_base64}"
                                ),
                            },
                            {
                                "type": "input_text",
                                "text": prompt,
                            },
                        ],
                    }
                ]),
            )

            return response.output_text or ""

        except Exception as exc:

            logger.error(
                f"OpenAI vision error: {exc}"
            )

            raise