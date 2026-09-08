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
- Sensitive computer typing remembers the original foreground window.
"""

from dataclasses import dataclass, field
from typing import Optional
import platform
import time

from backend.ai.base import AIProvider, ChatMessage
from backend.core.config import get_settings
from backend.core.logging import logger
from backend.security.permissions import (
    ConfirmationRequired,
    PendingConfirmation,
)
from backend.tools.registry import ToolRegistry


# ==============================================================
# TOOL NAME HELPERS
# ==============================================================

TYPE_TEXT_TOOL_NAMES = {
    "computer.type_text",
    "computer_type_text",
}

OPEN_APPLICATION_TOOL_NAMES = {
    "computer.open_application",
    "computer_open_application",
}


def _is_type_text_tool(tool_name: str) -> bool:
    """
    Support both the internal registry name and the AI/provider name.
    """
    return tool_name in TYPE_TEXT_TOOL_NAMES


def _is_open_application_tool(tool_name: str) -> bool:
    """
    Support both the internal registry name and the AI/provider name.
    """
    return tool_name in OPEN_APPLICATION_TOOL_NAMES


# ==============================================================
# WINDOWS FOREGROUND WINDOW HELPERS
# ==============================================================

def _get_foreground_window_handle():
    """
    Capture the currently focused Windows window handle.

    This must happen BEFORE the confirmation request is returned
    because clicking the confirmation button can make the browser
    the active window.
    """

    if platform.system() != "Windows":
        return None

    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()

        logger.info(
            "Captured foreground window handle: %s",
            hwnd,
        )

        return hwnd

    except Exception as exc:
        logger.warning(
            "Could not capture foreground window: %s",
            exc,
        )

        return None


def _get_foreground_window_title():
    """
    Return the title of the currently focused Windows window.
    """

    if platform.system() != "Windows":
        return None

    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()

        if not hwnd:
            return None

        length = ctypes.windll.user32.GetWindowTextLengthW(
            hwnd
        )

        if length <= 0:
            return None

        buffer = ctypes.create_unicode_buffer(
            length + 1
        )

        ctypes.windll.user32.GetWindowTextW(
            hwnd,
            buffer,
            length + 1,
        )

        return buffer.value

    except Exception as exc:
        logger.warning(
            "Could not get foreground window title: %s",
            exc,
        )

        return None


def _restore_foreground_window(hwnd) -> bool:
    """
    Restore and activate a previously captured Windows window.

    This is used immediately before computer.type_text so that
    clicking the Solution AI confirmation button does not cause
    text to be typed into the browser instead of the original
    application.
    """

    if not hwnd:
        logger.warning(
            "No target window handle was available."
        )

        return False

    if platform.system() != "Windows":
        return False

    try:
        import ctypes

        user32 = ctypes.windll.user32

        SW_RESTORE = 9

        # ------------------------------------------------------
        # Restore minimized window
        # ------------------------------------------------------

        user32.ShowWindow(
            hwnd,
            SW_RESTORE,
        )

        time.sleep(0.2)

        # ------------------------------------------------------
        # Get current foreground window
        # ------------------------------------------------------

        foreground_hwnd = (
            user32.GetForegroundWindow()
        )

        # ------------------------------------------------------
        # Get Windows input threads
        # ------------------------------------------------------

        current_thread = (
            user32.GetWindowThreadProcessId(
                foreground_hwnd,
                None,
            )
        )

        target_thread = (
            user32.GetWindowThreadProcessId(
                hwnd,
                None,
            )
        )

        attached = False

        # ------------------------------------------------------
        # Temporarily attach input threads
        # ------------------------------------------------------

        if (
            current_thread
            and target_thread
            and current_thread != target_thread
        ):
            attached = bool(
                user32.AttachThreadInput(
                    current_thread,
                    target_thread,
                    True,
                )
            )

        # ------------------------------------------------------
        # Force window to foreground
        # ------------------------------------------------------

        user32.BringWindowToTop(
            hwnd
        )

        user32.SetForegroundWindow(
            hwnd
        )

        user32.SetFocus(
            hwnd
        )

        # ------------------------------------------------------
        # Detach input threads
        # ------------------------------------------------------

        if attached:
            user32.AttachThreadInput(
                current_thread,
                target_thread,
                False,
            )

        # Give Windows time to finish changing focus.
        time.sleep(0.4)

        # ------------------------------------------------------
        # Verify
        # ------------------------------------------------------

        active_hwnd = (
            user32.GetForegroundWindow()
        )

        success = (
            active_hwnd == hwnd
        )

        active_title = (
            _get_foreground_window_title()
        )

        logger.info(
            "Restored target window: hwnd=%s | "
            "active_hwnd=%s | title=%r | success=%s",
            hwnd,
            active_hwnd,
            active_title,
            success,
        )

        return success

    except Exception as exc:
        logger.exception(
            "Failed to restore foreground window: %s",
            exc,
        )

        return False


# ==============================================================
# SYSTEM PROMPT
# ==============================================================

SYSTEM_PROMPT = """
You are Solution AI, a computer-use AI agent running on the user's local computer.

You have access to tools for:
- Computer control
- Filesystem operations
- Web browsing
- Terminal
- Memory
- System information
- Screen analysis

IMPORTANT TOOL RULES:

1. You MUST use the available tools when the user asks you to perform an action or retrieve information from the computer.

2. NEVER claim that you cannot access the user's computer, files, folders, applications, or system if an appropriate tool exists.

3. For filesystem requests, ALWAYS use the filesystem tools.
   - Listing files/folders -> filesystem_list_files
   - Searching files -> filesystem_search_files
   - Reading a file -> filesystem_read_file
   - Creating a folder -> filesystem_create_folder
   - Writing a file -> filesystem_write_file
   - Copying a file -> filesystem_copy_file
   - Moving a file -> filesystem_move_file
   - Deleting a file -> filesystem_delete_file

4. When the user gives an exact filesystem path, pass that exact path to the appropriate filesystem tool.

5. Do NOT invent permission errors or allowed-folder errors yourself.
   The filesystem tool is responsible for checking whether a path is allowed.

6. If a filesystem tool returns an error, report the actual error returned by the tool.

7. For example, if the user says:
   "List the files in C:\\Users\\HomePC\\Desktop\\solution-ai"

   you should call:
   filesystem_list_files

   with:
   {
       "path": "C:\\Users\\HomePC\\Desktop\\solution-ai"
   }

8. Do not ask the user for a path when they have already provided an exact path.

9. Continue using tools until the user's request has actually been completed.

10. After a tool succeeds, explain the result clearly to the user.

11. When using computer.type_text:
    - Type into the currently active application.
    - The application that was active when the typing request was created should be treated as the target.
    - Do not claim success unless the tool reports success.

You are an agent, not just a chatbot. Prefer executing the appropriate tool over merely explaining how the user could do it.
"""


# ==============================================================
# HISTORY SETTINGS
# ==============================================================

MAX_HISTORY_MESSAGES = 30
MAX_HISTORY_MESSAGE_CHARS = 4000


def _trim_history(history: list) -> list:
    """
    Keep only a bounded amount of recent conversation history.

    Working tool history during an active task is never trimmed.
    """

    if not history:
        return []

    recent = history[
        -MAX_HISTORY_MESSAGES:
    ]

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


# ==============================================================
# RESULT
# ==============================================================

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


# ==============================================================
# ORCHESTRATOR
# ==============================================================

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

        messages = _trim_history(
            history
        )

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

            result.steps_taken = (
                step + 1
            )

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

                # ------------------------------------------------
                # CAPTURE TARGET WINDOW BEFORE CONFIRMATION
                # ------------------------------------------------

                target_window_handle = None
                target_window_title = None

                # IMPORTANT:
                # Groq returns "computer_type_text"
                # while the registry internally uses
                # "computer.type_text".
                #
                # We therefore support BOTH names here.

                if _is_type_text_tool(
                    call.name
                ):

                    target_window_handle = (
                        _get_foreground_window_handle()
                    )

                    target_window_title = (
                        _get_foreground_window_title()
                    )

                    logger.info(
                        "Captured typing target: "
                        "hwnd=%s | title=%r",
                        target_window_handle,
                        target_window_title,
                    )

                # ------------------------------------------------
                # EXECUTE TOOL
                # ------------------------------------------------

                try:

                    tool_result = (
                        await self._tools.execute(
                            call.name,
                            call.arguments,
                        )
                    )

                except ConfirmationRequired as exc:

                    # ------------------------------------------------
                    # PRESERVE EXACT WORKING STATE
                    # ------------------------------------------------

                    pending = exc.pending

                    pending.context = {
                        "source": "chat_api",
                        "tool_call_id": call.id,
                        "paused_messages": list(
                            messages
                        ),
                        "target_window_handle": (
                            target_window_handle
                        ),
                        "target_window_title": (
                            target_window_title
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
                        "%s | tool_call_id=%s | "
                        "target_window=%r | hwnd=%s",
                        pending.tool_name,
                        call.id,
                        target_window_title,
                        target_window_handle,
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

                # ------------------------------------------------
                # TOOL COMPLETED
                # ------------------------------------------------

                result.tool_events.append(
                    {
                        "type": "tool_completed",
                        "tool": call.name,
                        "success": tool_result.success,
                    }
                )

                # ------------------------------------------------
                # RETURN TOOL RESULT TO AI
                # ------------------------------------------------

                messages.append(
                    ChatMessage(
                        role="tool",
                        content=str(
                            tool_result.to_dict()
                        ),
                        tool_call_id=call.id,
                    )
                )

                # ------------------------------------------------
                # STOP AFTER SUCCESSFUL TYPING
                # ------------------------------------------------

                if (
                    _is_type_text_tool(call.name)
                    and tool_result.success
                ):

                    result.final_text = (
                        "Done. I typed the requested text."
                    )

                    result.stopped_reason = (
                        "completed"
                    )

                    return result

                # ------------------------------------------------
                # OPEN APPLICATION
                # ------------------------------------------------

                if (
                    _is_open_application_tool(call.name)
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

        settings = get_settings()

        # ------------------------------------------------------
        # RESTORE CONTEXT
        # ------------------------------------------------------

        context = (
            pending.context
            or {}
        )

        paused_messages = (
            context.get(
                "paused_messages"
            )
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

        tool_call_id = (
            context.get(
                "tool_call_id"
            )
        )

        if not tool_call_id:

            tool_call_id = pending.id

        # ------------------------------------------------------
        # TARGET WINDOW
        # ------------------------------------------------------

        target_window_handle = (
            context.get(
                "target_window_handle"
            )
        )

        target_window_title = (
            context.get(
                "target_window_title"
            )
        )

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
        # RESTORE ORIGINAL APPLICATION FOCUS
        # ------------------------------------------------------

        if _is_type_text_tool(
            pending.tool_name
        ):

            logger.info(
                "Restoring typing target: "
                "hwnd=%s | original_title=%r",
                target_window_handle,
                target_window_title,
            )

            restored = (
                _restore_foreground_window(
                    target_window_handle
                )
            )

            if not restored:

                logger.warning(
                    "Could not verify original "
                    "typing target window."
                )

            # Give Windows extra time to move
            # keyboard focus to the target.
            time.sleep(0.5)

            logger.info(
                "Foreground window immediately "
                "before typing: %r",
                _get_foreground_window_title(),
            )

        # ------------------------------------------------------
        # EXECUTE APPROVED TOOL
        # ------------------------------------------------------

        try:

            tool_result = (
                await self._tools.execute(
                    pending.tool_name,
                    pending.arguments,
                    pre_confirmed=True,
                )
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

        if _is_type_text_tool(
            pending.tool_name
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

        if _is_open_application_tool(
            pending.tool_name
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

                # ------------------------------------------------
                # CAPTURE TARGET WINDOW FOR FOLLOW-UP TYPING
                # ------------------------------------------------

                follow_up_window_handle = None
                follow_up_window_title = None

                if _is_type_text_tool(
                    call.name
                ):

                    follow_up_window_handle = (
                        _get_foreground_window_handle()
                    )

                    follow_up_window_title = (
                        _get_foreground_window_title()
                    )

                    logger.info(
                        "Captured follow-up typing target: "
                        "hwnd=%s | title=%r",
                        follow_up_window_handle,
                        follow_up_window_title,
                    )

                # ------------------------------------------------
                # EXECUTE FOLLOW-UP TOOL
                # ------------------------------------------------

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
                        "target_window_handle": (
                            follow_up_window_handle
                        ),
                        "target_window_title": (
                            follow_up_window_title
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
                        "tool_call_id=%s | "
                        "target_window=%r | hwnd=%s",
                        pending_next.tool_name,
                        call.id,
                        follow_up_window_title,
                        follow_up_window_handle,
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

                # ------------------------------------------------
                # FOLLOW-UP TOOL COMPLETED
                # ------------------------------------------------

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

                # ------------------------------------------------
                # STOP AFTER SUCCESSFUL TYPING
                # ------------------------------------------------

                if (
                    _is_type_text_tool(call.name)
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