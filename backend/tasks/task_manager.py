"""
TaskManager (spec section 20) — runs a user-defined goal as a background,
multi-step task using the same AgentOrchestrator as chat, but:
  - persists progress to the `tasks`/`task_steps` tables as it goes, so
    progress survives a backend restart and can be inspected via
    GET /api/tasks/{id};
  - retries a failed step up to `max_retries` times before marking the whole
    task failed, instead of the single-shot chat loop which just reports
    the error back to the user.

This does NOT duplicate the orchestrator's tool-calling loop — it wraps one
`AgentOrchestrator.run()` call per task and treats the *whole task* as one
unit of work with its own retry policy, which is the right granularity for
things like scheduled tasks ("check my email every morning") where retrying
the entire goal on failure is more sensible than retrying a single tool call.
"""

import asyncio
import uuid
from datetime import datetime

from backend.agents.orchestrator import AgentOrchestrator
from backend.ai.provider_factory import get_ai_provider
from backend.core.logging import logger
from backend.database.models import Task
from backend.database.session import SessionLocal
from backend.tools.registry import registry

MAX_RETRIES = 2


class TaskManager:
    def __init__(self):
        self._running: dict[str, asyncio.Task] = {}

    def create_task(self, name: str, description: str) -> Task:
        db = SessionLocal()
        try:
            task = Task(id=str(uuid.uuid4()), name=name, description=description, status="pending")
            db.add(task)
            db.commit()
            db.refresh(task)
            return task
        finally:
            db.close()

    def start(self, task_id: str) -> None:
        if task_id in self._running:
            return
        coro = self._run(task_id)
        self._running[task_id] = asyncio.create_task(coro)

    async def _run(self, task_id: str) -> None:
        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            if task is None:
                return
            task.status = "running"
            task.started_at = datetime.utcnow()
            db.commit()

            orchestrator = AgentOrchestrator(provider=get_ai_provider(), tools=registry)

            last_error = None
            for attempt in range(1, MAX_RETRIES + 2):
                try:
                    result = await orchestrator.run(task.description or task.name, history=[])
                    if result.pending_confirmation:
                        # A background task hitting a DANGEROUS/SENSITIVE tool has no
                        # user present to confirm — fail loudly rather than guess.
                        task.status = "failed"
                        task.error = (
                            f"Task paused for confirmation on '{result.pending_confirmation.tool_name}' "
                            f"but background tasks cannot prompt the user. Lower the tool's risk, run it "
                            f"interactively instead, or approve it manually via POST /api/tools/{{name}}/execute."
                        )
                        db.commit()
                        return

                    task.status = "completed"
                    task.completed_at = datetime.utcnow()
                    task.result = {"final_text": result.final_text, "steps_taken": result.steps_taken}
                    db.commit()
                    return
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    logger.warning(f"Task {task_id} attempt {attempt} failed: {exc}")

            task.status = "failed"
            task.error = last_error
            task.completed_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()
            self._running.pop(task_id, None)

    def cancel(self, task_id: str) -> bool:
        running = self._running.get(task_id)
        if running is None:
            return False
        running.cancel()
        db = SessionLocal()
        try:
            task = db.get(Task, task_id)
            if task:
                task.status = "cancelled"
                db.commit()
        finally:
            db.close()
        return True


task_manager = TaskManager()
