"""
Database Connection & Session Management
----------------------------------------
Configures SQLite with Write-Ahead Logging (WAL) and thread-safe connection pooling.
Auto-initializes all tables on startup.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session

logger = logging.getLogger(__name__)

# Base directory for database file: backend/data/
_BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = _BACKEND_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "surveillance.db"
DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

# Create SQLite engine with multithreading support and WAL mode
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)

# Enable SQLite foreign keys & WAL mode on each connection
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)
Base = declarative_base()


def init_db():
    """Create all database tables defined in models.py if they don't exist."""
    try:
        # Import models so Base.metadata is populated
        import app.db.models  # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("[Database] Initialized SQLite database tables at %s (WAL mode enabled)", DB_PATH)
    except Exception as exc:
        logger.error("[Database] Failed to initialize database: %s", exc, exc_info=True)


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for scoped database sessions."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
