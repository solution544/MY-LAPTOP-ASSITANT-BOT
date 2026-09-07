"""
AgentOrchestrator — the brain of Solution AI.

Handles:
    REQUEST
        ↓
    UNDERSTAND
        ↓
    RETRIEVE CONTEXT
        ↓
    PLAN
        ↓
    EXECUTE TOOL
        ↓
    OBSERVE RESULT
        ↓
    VERIFY
        ↓
    CONTINUE / RETRY
        ↓
    COMPLETE
        ↓
    RESPOND

Important:
- Normal conversation history is bounded.
- Tool execution history is preserved during a single run.
- Confirmation pauses preserve the exact working tool history.
- Confirmation resumes using the original provider tool_call_id.
"""

from dataclasses import dataclass, field
from typing import Optional

from backend.ai.base import AIProvider, ChatMessage
from backend.core.config import get_settings
from backend.core.logging import logger
from backend.security.permissions import (
    ConfirmationRequired,
    PendingConfirmation,
)
from backend.tools.registry import ToolRegistry


SYSTEM_PROMPT = """You are Solution AI, a personal AI agent running on the user's own computer.

You have access to tools for:
- controlling the computer
- browsing the web
- reading and writing files
- running terminal commands
- remembering information
- seeing and analyzing the screen

Rules:
- Use tools when they are the right way to accomplish what the user asked.
- Do not ask the user to do something manually when you have a tool that can do it.
- After every tool result, check whether the action actually accomplished what you intended.
- If a tool fails or produces an unexpected result, adapt your plan instead of reporting success.
- Continue using tools when additional actions are required to complete the user's request.
- Be concise in your final response.
- Do not reveal internal reasoning or chain-of-thought.
- Report what you actually did and the result.

Computer-control rules:
- When the user asks you to open an application, use computer.open_application.
- When the user asks you to type something, use computer.type_text.
- If typing into an application requires opening that application first, open it before typing.
- Do not repeatedly call unrelated computer tools.
- Do not call the same tool repeatedly unless the previous result shows that the action failed.
- Once the requested action succeeds, stop using tools and respond to the user.
- If a computer action requires confirmation, pause and wait for the user's confirmation.

If you are not confident a destructive action is what the user wants, ask before doing it.
"""


MAX_HISTORY_MESSAGES = 30
MAX_HISTORY_MESSAGE_CHARS = 4000


def _trim_history(history: list) -> list:
    """
    Keep only a bounded amount of recent conversation history.

    This is used when starting a new user request.

    Working tool history during an active task is never trimmed.
    """

    if not history:
        return []

    recent = history[-MAX_HISTORY_MESSAGES:]

    trimmed: list = []

    for message in recent:

        if not isinstance(
            message,
            ChatMessage,
        ):
            continue

        content = message.content or ""

        if len(content) > MAX_HISTORY_MESSAGE_CHARS:

            content = (
                content[:MAX_HISTORY_MESSAGE_CHARS]
                + "\n[Older content truncated.]"
            )

        trimmed.append(
            ChatMessage(
                role=message.role,
                content=content,
                tool_call_id=message.tool_call_id,
                tool_calls=message.tool_calls,
                response_items=message.response_items,
            )
        )

    return trimmed


@dataclass
class AgentTurnResult:

    final_text: Optional[str] = None

    pending_confirmation: Optional[
        PendingConfirmation
    ] = None

    steps_taken: int = 0

    stopped_reason: Optional[str] = None

    tool_events: list = field(
        default_factory=list
    )

    paused_messages: list = field(
        default_factory=list
    )


class AgentOrchestrator:

    def __init__(
        self,
        provider: AIProvider,
        tools: ToolRegistry,
    ):
        self._provider = provider
        self._tools = tools

    # ==========================================================
    # NORMAL CHAT
    # ==========================================================

    async def run(
        self,
        user_message: str,
        history: list,
    ) -> AgentTurnResult:

        settings = get_settings()

        # ------------------------------------------------------
        # BOUNDED CONVERSATION HISTORY
        # ------------------------------------------------------

        messages = _trim_history(history)

        messages.append(
            ChatMessage(
                role="user",
                content=user_message,
            )
        )

        # ------------------------------------------------------
        # TOOL DEFINITIONS
        # ------------------------------------------------------

        tool_definitions = (
            self._tools.list_definitions()
        )

        result = AgentTurnResult()

        # ------------------------------------------------------
        # AGENT LOOP
        # ------------------------------------------------------

        for step in range(
            settings.max_agent_steps
        ):

            result.steps_taken = step + 1

            logger.info(
                "Solution AI agent step %s/%s",
                step + 1,
                settings.max_agent_steps,
            )

            # --------------------------------------------------
            # ASK AI
            # --------------------------------------------------

            response = await self._provider.chat(
                messages=messages,
                tools=tool_definitions,
                system_prompt=SYSTEM_PROMPT,
            )

            # --------------------------------------------------
            # MODEL FINISHED
            # --------------------------------------------------

            if not response.tool_calls:

                result.final_text = (
                    response.text
                    or "I completed the request."
                )

                result.stopped_reason = (
                    "completed"
                )

                return result

            # --------------------------------------------------
            # PRESERVE PROVIDER RESPONSE
            # --------------------------------------------------

            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.text or "",
                    tool_calls=response.tool_calls,
                    response_items=(
                        response.response_items
                    ),
                )
            )

            # --------------------------------------------------
            # EXECUTE TOOLS
            # --------------------------------------------------

            for call in response.tool_calls:

                logger.info(
                    "Solution AI executing tool: %s",
                    call.name,
                )

                result.tool_events.append(
                    {
                        "type": "tool_started",
                        "tool": call.name,
                    }
                )

                try:

                    tool_result = (
                        await self._tools.execute(
                            call.name,
                            call.arguments,
                        )
                    )

                except ConfirmationRequired as exc:

                    # --------------------------------------------------
                    # PRESERVE EXACT WORKING STATE
                    # --------------------------------------------------

                    pending = exc.pending

                    pending.context = {
                        "source": "chat_api",
                        "tool_call_id": call.id,
                        "paused_messages": list(
                            messages
                        ),
                    }

                    result.pending_confirmation = (
                        pending
                    )

                    result.paused_messages = list(
                        messages
                    )

                    result.stopped_reason = (
                        "awaiting_confirmation"
                    )

                    logger.info(
                        "Solution AI waiting for confirmation: "
                        "%s | tool_call_id=%s",
                        pending.tool_name,
                        call.id,
                    )

                    return result

                except Exception as exc:

                    logger.exception(
                        "Unexpected error executing "
                        "tool %s",
                        call.name,
                    )

                    result.tool_events.append(
                        {
                            "type": "tool_completed",
                            "tool": call.name,
                            "success": False,
                        }
                    )

                    messages.append(
                        ChatMessage(
                            role="tool",
                            content=(
                                "Tool execution failed: "
                                f"{type(exc).__name__}: "
                                f"{exc}"
                            ),
                            tool_call_id=call.id,
                        )
                    )

                    continue

                # --------------------------------------------------
                # TOOL COMPLETED
                # --------------------------------------------------

                result.tool_events.append(
                    {
                        "type": "tool_completed",
                        "tool": call.name,
                        "success": tool_result.success,
                    }
                )

                # --------------------------------------------------
                # RETURN TOOL RESULT TO AI
                # --------------------------------------------------

                messages.append(
                    ChatMessage(
                        role="tool",
                        content=str(
                            tool_result.to_dict()
                        ),
                        tool_call_id=call.id,
                    )
                )

                # --------------------------------------------------
                # STOP AFTER SUCCESSFUL REQUESTED ACTION
                # --------------------------------------------------

                if (
                    call.name
                    == "computer.type_text"
                    and tool_result.success
                ):

                    result.final_text = (
                        "Done. I typed the requested text."
                    )

                    result.stopped_reason = (
                        "completed"
                    )

                    return result

                if (
                    call.name
                    == "computer.open_application"
                    and tool_result.success
                ):

                    # Do not stop here because opening an
                    # application may only be the first part
                    # of a larger request such as:
                    #
                    # "open notepad and type hello"

                    continue

        # ======================================================
        # MAX STEPS
        # ======================================================

        result.stopped_reason = (
            "max_steps"
        )

        result.final_text = (
            "Task stopped because the maximum "
            f"number of actions "
            f"({settings.max_agent_steps}) "
            "was reached."
        )

        logger.warning(
            "Agent hit MAX_AGENT_STEPS (%s)",
            settings.max_agent_steps,
        )

        return result

    # ==========================================================
    # CONFIRMATION CONTINUATION
    # ==========================================================

    async def continue_after_confirmation(
        self,
        pending: PendingConfirmation,
        approved: bool,
        history: list,
    ) -> AgentTurnResult:
        """
        Resume an agent after confirmation.

        The exact paused tool history is restored from the
        pending confirmation context whenever available.
        """

        # ------------------------------------------------------
        # SETTINGS
        # ------------------------------------------------------

        settings = get_settings()

        # ------------------------------------------------------
        # RESTORE CONTEXT
        # ------------------------------------------------------

        context = pending.context or {}

        paused_messages = context.get(
            "paused_messages"
        )

        if isinstance(
            paused_messages,
            list,
        ):

            messages = list(
                paused_messages
            )

        else:

            messages = list(
                history
            )

        # ------------------------------------------------------
        # RESTORE ORIGINAL TOOL CALL ID
        # ------------------------------------------------------

        tool_call_id = context.get(
            "tool_call_id"
        )

        if not tool_call_id:

            tool_call_id = pending.id

        result = AgentTurnResult()

        # ------------------------------------------------------
        # USER REJECTED ACTION
        # ------------------------------------------------------

        if not approved:

            logger.info(
                "Confirmation rejected: %s",
                pending.tool_name,
            )

            result.final_text = (
                "Okay. I cancelled the action."
            )

            result.stopped_reason = (
                "rejected"
            )

            return result

        # ------------------------------------------------------
        # USER APPROVED ACTION
        # ------------------------------------------------------

        logger.info(
            "Confirmation approved: %s",
            pending.tool_name,
        )

        logger.info(
            "Executing confirmed tool: %s | arguments=%s",
            pending.tool_name,
            pending.arguments,
        )

        # ------------------------------------------------------
        # EXECUTE APPROVED TOOL
        # ------------------------------------------------------

        try:

            tool_result = await self._tools.execute(
                pending.tool_name,
                pending.arguments,
                pre_confirmed=True,
            )

        except Exception as exc:

            logger.exception(
                "Confirmed tool execution failed "
                "for %s",
                pending.tool_name,
            )

            result.tool_events.append(
                {
                    "type": "tool_completed",
                    "tool": pending.tool_name,
                    "success": False,
                }
            )

            result.final_text = (
                f"The action failed: {exc}"
            )

            result.stopped_reason = (
                "tool_error"
            )

            return result

        # ------------------------------------------------------
        # RECORD TOOL EVENT
        # ------------------------------------------------------

        result.tool_events.append(
            {
                "type": "tool_completed",
                "tool": pending.tool_name,
                "success": tool_result.success,
            }
        )

        # ------------------------------------------------------
        # ADD TOOL RESULT TO PAUSED HISTORY
        # ------------------------------------------------------

        messages.append(
            ChatMessage(
                role="tool",
                content=str(
                    tool_result.to_dict()
                ),
                tool_call_id=tool_call_id,
            )
        )

        # ------------------------------------------------------
        # TOOL FAILED
        # ------------------------------------------------------

        if not tool_result.success:

            logger.error(
                "Confirmed tool failed: %s | error=%s",
                pending.tool_name,
                tool_result.error,
            )

            result.final_text = (
                tool_result.error
                or "The requested action failed."
            )

            result.stopped_reason = (
                "tool_failed"
            )

            return result

        # ------------------------------------------------------
        # CONFIRMED COMPUTER.TYPE_TEXT SUCCEEDED
        # ------------------------------------------------------

        if (
            pending.tool_name
            == "computer.type_text"
        ):

            logger.info(
                "Confirmed computer.type_text "
                "completed successfully."
            )

            result.final_text = (
                "Done. I typed the requested text."
            )

            result.stopped_reason = (
                "completed"
            )

            return result

        # ------------------------------------------------------
        # CONFIRMED COMPUTER.OPEN_APPLICATION
        # ------------------------------------------------------

        if (
            pending.tool_name
            == "computer.open_application"
        ):

            logger.info(
                "Confirmed computer.open_application "
                "completed successfully."
            )

            result.final_text = (
                "Done. I opened the requested application."
            )

            result.stopped_reason = (
                "completed"
            )

            return result

        # ------------------------------------------------------
        # OTHER CONFIRMED TOOLS
        # ------------------------------------------------------

        tool_definitions = (
            self._tools.list_definitions()
        )

        # ------------------------------------------------------
        # CONTINUE AGENT LOOP
        # ------------------------------------------------------

        for step in range(
            settings.max_agent_steps
        ):

            result.steps_taken = (
                step + 1
            )

            logger.info(
                "Solution AI confirmation step %s/%s",
                step + 1,
                settings.max_agent_steps,
            )

            # --------------------------------------------------
            # ASK AI
            # --------------------------------------------------

            response = await self._provider.chat(
                messages=messages,
                tools=tool_definitions,
                system_prompt=SYSTEM_PROMPT,
            )

            # --------------------------------------------------
            # MODEL FINISHED
            # --------------------------------------------------

            if not response.tool_calls:

                result.final_text = (
                    response.text
                    or "The action has been completed."
                )

                result.stopped_reason = (
                    "completed"
                )

                return result

            # --------------------------------------------------
            # PRESERVE PROVIDER RESPONSE
            # --------------------------------------------------

            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.text or "",
                    tool_calls=response.tool_calls,
                    response_items=(
                        response.response_items
                    ),
                )
            )

            # --------------------------------------------------
            # EXECUTE FOLLOW-UP TOOLS
            # --------------------------------------------------

            for call in response.tool_calls:

                logger.info(
                    "Solution AI executing follow-up tool: %s",
                    call.name,
                )

                result.tool_events.append(
                    {
                        "type": "tool_started",
                        "tool": call.name,
                    }
                )

                try:

                    tool_result = (
                        await self._tools.execute(
                            call.name,
                            call.arguments,
                        )
                    )

                except ConfirmationRequired as exc:

                    pending_next = exc.pending

                    pending_next.context = {
                        "source": "chat_api",
                        "tool_call_id": call.id,
                        "paused_messages": list(
                            messages
                        ),
                    }

                    result.pending_confirmation = (
                        pending_next
                    )

                    result.paused_messages = list(
                        messages
                    )

                    result.stopped_reason = (
                        "awaiting_confirmation"
                    )

                    logger.info(
                        "Solution AI waiting for "
                        "follow-up confirmation: %s | "
                        "tool_call_id=%s",
                        pending_next.tool_name,
                        call.id,
                    )

                    return result

                except Exception as exc:

                    logger.exception(
                        "Unexpected error executing "
                        "follow-up tool %s",
                        call.name,
                    )

                    result.tool_events.append(
                        {
                            "type": "tool_completed",
                            "tool": call.name,
                            "success": False,
                        }
                    )

                    messages.append(
                        ChatMessage(
                            role="tool",
                            content=(
                                "Tool execution failed: "
                                f"{type(exc).__name__}: "
                                f"{exc}"
                            ),
                            tool_call_id=call.id,
                        )
                    )

                    continue

                # --------------------------------------------------
                # FOLLOW-UP TOOL COMPLETED
                # --------------------------------------------------

                result.tool_events.append(
                    {
                        "type": "tool_completed",
                        "tool": call.name,
                        "success": tool_result.success,
                    }
                )

                messages.append(
                    ChatMessage(
                        role="tool",
                        content=str(
                            tool_result.to_dict()
                        ),
                        tool_call_id=call.id,
                    )
                )

                # --------------------------------------------------
                # STOP AFTER SUCCESSFUL TYPING
                # --------------------------------------------------

                if (
                    call.name
                    == "computer.type_text"
                    and tool_result.success
                ):

                    logger.info(
                        "Follow-up computer.type_text "
                        "completed successfully."
                    )

                    result.final_text = (
                        "Done. I typed the requested text."
                    )

                    result.stopped_reason = (
                        "completed"
                    )

                    return result

        # ======================================================
        # MAX STEPS AFTER CONFIRMATION
        # ======================================================

        result.stopped_reason = (
            "max_steps"
        )

        result.final_text = (
            "Task stopped because the maximum "
            f"number of actions "
            f"({settings.max_agent_steps}) "
            "was reached."
        )

        logger.warning(
            "Agent hit MAX_AGENT_STEPS (%s) "
            "after confirmation.",
            settings.max_agent_steps,
        )

        return result
