"""
GET /api/system/status — used by the frontend to show connection health and
by you, during Phase 1 testing, to confirm the backend is actually up and
can reach the database, without needing anything else wired.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.database.session import get_db

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
def system_status(db: Session = Depends(get_db)):
    settings = get_settings()

    db_ok = True
    db_error = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — reporting status, not handling
        db_ok = False
        db_error = str(exc)

    return {
        "status": "ok" if db_ok else "degraded",
        "app_env": settings.app_env,
        "ai_provider": settings.ai_provider,
        "ai_model": settings.ai_model,
        "database": {"connected": db_ok, "error": db_error},
    }
