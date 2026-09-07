from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.models import ScheduledTask, Task
from backend.database.session import get_db
from backend.scheduler.scheduler import schedule_task, unschedule_task
from backend.tasks.task_manager import task_manager

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
# Scheduled-task routes live under /api/scheduled-tasks (a separate prefix,
# not /api/tasks/scheduled/...) specifically so they can never collide with
# the /api/tasks/{task_id} pattern above regardless of route registration
# order — a "scheduled" task_id would otherwise be ambiguous with a literal
# path segment.
scheduled_router = APIRouter(prefix="/api/scheduled-tasks", tags=["scheduled-tasks"])


class CreateTaskRequest(BaseModel):
    name: str
    description: str


class TaskOut(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    created_at: datetime
    completed_at: datetime | None
    result: dict | None
    error: str | None

    class Config:
        from_attributes = True


@router.get("", response_model=list[TaskOut])
def list_tasks(db: Session = Depends(get_db)):
    return db.query(Task).order_by(Task.created_at.desc()).limit(100).all()


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("", response_model=TaskOut)
def create_and_run_task(request: CreateTaskRequest):
    task = task_manager.create_task(request.name, request.description)
    task_manager.start(task.id)
    return task


@router.post("/{task_id}/cancel")
def cancel_task(task_id: str):
    if not task_manager.cancel(task_id):
        raise HTTPException(status_code=404, detail="Task is not currently running")
    return {"cancelled": task_id}


# --- Scheduled tasks ---

class CreateScheduledTaskRequest(BaseModel):
    name: str
    description: str
    schedule_type: str  # once|daily|weekly|monthly|custom
    cron_expression: str | None = None
    run_at: datetime | None = None


class ScheduledTaskOut(BaseModel):
    id: str
    name: str
    schedule_type: str
    enabled: bool
    last_run_at: datetime | None

    class Config:
        from_attributes = True


@scheduled_router.get("", response_model=list[ScheduledTaskOut])
def list_scheduled(db: Session = Depends(get_db)):
    return db.query(ScheduledTask).all()


@scheduled_router.post("", response_model=ScheduledTaskOut)
def create_scheduled(request: CreateScheduledTaskRequest, db: Session = Depends(get_db)):
    import uuid
    scheduled = ScheduledTask(id=str(uuid.uuid4()), **request.model_dump())
    db.add(scheduled)
    db.commit()
    db.refresh(scheduled)
    schedule_task(scheduled)
    return scheduled


@scheduled_router.delete("/{scheduled_id}")
def delete_scheduled(scheduled_id: str, db: Session = Depends(get_db)):
    scheduled = db.get(ScheduledTask, scheduled_id)
    if scheduled is None:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    unschedule_task(scheduled_id)
    db.delete(scheduled)
    db.commit()
    return {"deleted": scheduled_id}
