"""Database connection abstraction.

SQLite is the default backend (zero setup). The same SQL runs on PostgreSQL:
set ``DATABASE_URL=postgresql://...`` and install ``psycopg2-binary``. The
only dialect difference handled here is the parameter placeholder (``?`` for
sqlite3 vs ``%s`` for psycopg2) -- repositories always write ``?`` and the
:class:`Database` translates when talking to PostgreSQL.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from scraper.config.settings import PROJECT_ROOT
from scraper.db.schema import ALL_TABLES

logger = logging.getLogger(__name__)


class Database:
    """Thin connection wrapper hiding the sqlite/postgres dialect difference."""

    def __init__(self, database_url: str) -> None:
        self._url = database_url
        self._is_postgres = database_url.startswith(("postgres://", "postgresql://"))
        self._conn = self._connect()

    # -- connection -----------------------------------------------------------
    def _connect(self) -> Any:
        if self._is_postgres:
            try:
                import psycopg2  # type: ignore[import-untyped]
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise RuntimeError(
                    "DATABASE_URL points at PostgreSQL but psycopg2 is not "
                    "installed. Run: pip install psycopg2-binary"
                ) from exc
            logger.info("Connecting to PostgreSQL")
            return psycopg2.connect(self._url)

        path_part = urlparse(self._url).path if "://" in self._url else self._url
        db_path = Path(path_part.lstrip("/")) if path_part else Path("data/scraper.db")
        if not db_path.is_absolute():
            db_path = PROJECT_ROOT / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Opening SQLite database at %s", db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    # -- SQL execution ----------------------------------------------------------
    def _translate(self, sql: str) -> str:
        return sql.replace("?", "%s") if self._is_postgres else sql

    def execute(self, sql: str, params: Iterable[Any] = ()) -> Any:
        """Execute a statement and return the cursor."""
        cur = self._conn.cursor()
        cur.execute(self._translate(sql), tuple(params))
        return cur

    def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> tuple | None:
        return self.execute(sql, params).fetchone()

    def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[tuple]:
        return self.execute(sql, params).fetchall()

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- schema -----------------------------------------------------------------
    def create_schema(self) -> None:
        """Create all tables if they do not exist yet (idempotent)."""
        for ddl in ALL_TABLES:
            self.execute(ddl)
        self.commit()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
