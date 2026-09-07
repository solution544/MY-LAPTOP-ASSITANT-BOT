```python
"""
SQLAlchemy engine and session factory.

A single engine is created from `Settings.database_url`.
`get_db()` is a FastAPI dependency that yields a session per request
and always closes it, even when an error occurs.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.core.config import get_settings


settings = get_settings()

database_url = settings.database_url

# Render/PostgreSQL may provide a standard postgresql:// URL.
# Explicitly use the psycopg 3 SQLAlchemy driver.
if database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
