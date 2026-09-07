"""
Task scheduler (spec section 22) — runs scheduled_tasks rows (once/daily/
weekly/monthly/custom cron) by handing them to TaskManager at the right
time. Built on APScheduler's AsyncIOScheduler so it shares the FastAPI
process's event loop rather than spawning a separate process.
"""

from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from backend.core.logging import logger
from backend.database.models import ScheduledTask
from backend.database.session import SessionLocal
from backend.tasks.task_manager import task_manager

scheduler = AsyncIOScheduler()


def _run_scheduled_task(scheduled_task_id: str) -> None:
    db = SessionLocal()
    try:
        scheduled = db.get(ScheduledTask, scheduled_task_id)
        if scheduled is None or not scheduled.enabled:
            return
        task = task_manager.create_task(name=scheduled.name, description=scheduled.description or scheduled.name)
        task_manager.start(task.id)
        scheduled.last_run_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def _add_job(scheduled: ScheduledTask) -> None:
    if scheduled.schedule_type == "once" and scheduled.run_at:
        trigger = DateTrigger(run_date=scheduled.run_at)
    elif scheduled.schedule_type == "daily" and scheduled.run_at:
        trigger = CronTrigger(hour=scheduled.run_at.hour, minute=scheduled.run_at.minute)
    elif scheduled.schedule_type == "weekly" and scheduled.run_at:
        trigger = CronTrigger(day_of_week=scheduled.run_at.weekday(), hour=scheduled.run_at.hour, minute=scheduled.run_at.minute)
    elif scheduled.schedule_type == "custom" and scheduled.cron_expression:
        trigger = CronTrigger.from_crontab(scheduled.cron_expression)
    else:
        logger.warning(f"Scheduled task {scheduled.id} has no valid trigger configuration — skipped.")
        return

    scheduler.add_job(_run_scheduled_task, trigger=trigger, args=[scheduled.id], id=scheduled.id, replace_existing=True)


def load_all_scheduled_tasks() -> None:
    """Call once at startup so schedules persist across backend restarts."""
    db = SessionLocal()
    try:
        for scheduled in db.query(ScheduledTask).filter(ScheduledTask.enabled == True).all():  # noqa: E712
            _add_job(scheduled)
        logger.info(f"Scheduler loaded {len(scheduler.get_jobs())} job(s).")
    finally:
        db.close()


def schedule_task(scheduled: ScheduledTask) -> None:
    """Call when a new scheduled task is created via the API."""
    _add_job(scheduled)


def unschedule_task(scheduled_task_id: str) -> None:
    if scheduler.get_job(scheduled_task_id):
        scheduler.remove_job(scheduled_task_id)
