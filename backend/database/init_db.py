"""
Run once to create all tables from the models in `backend/database/models.py`.

For anything beyond Phase 1, prefer Alembic migrations (see `alembic/`)
instead of calling this repeatedly — this script is a convenience for first
setup only and does not handle schema changes to existing tables.

Usage (from repo root, with venv active and .env configured):
    python -m backend.database.init_db
"""

from backend.core.logging import logger
from backend.database.session import Base, engine
from backend.database import models  # noqa: F401
# Importing models registers all database models with Base.


def init_db() -> None:
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized: all tables created.")


if __name__ == "__main__":
    init_db()