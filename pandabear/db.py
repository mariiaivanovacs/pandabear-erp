"""SQLite access — one connection per call, rows as dicts, schema applied on first use."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .config import settings

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    return {d[0]: row[i] for i, d in enumerate(cursor.description)}


@contextmanager
def get_conn():
    conn = sqlite3.connect(settings.metadata_db)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA_PATH.read_text())


def loads_field(row: dict, *fields: str) -> dict:
    """Parse JSON-string columns in place; tolerate already-parsed/None values."""
    for f in fields:
        v = row.get(f)
        if isinstance(v, str):
            try:
                row[f] = json.loads(v)
            except json.JSONDecodeError:
                pass
    return row
