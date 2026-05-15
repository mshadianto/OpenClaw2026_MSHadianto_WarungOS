"""Database utilities for all agents."""
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "data" / "warungos.db"


@contextmanager
def get_db():
    """Context manager for SQLite connection with dict rows."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def execute(sql: str, params: tuple = ()) -> int:
    with get_db() as conn:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.lastrowid


def log_agent_action(agent_name: str, action: str, details: dict | str = ""):
    """Audit log — every agent action is recorded for transparency."""
    if isinstance(details, dict):
        details = json.dumps(details, ensure_ascii=False)
    execute(
        "INSERT INTO agent_activity_log (agent_name, action, details) VALUES (?, ?, ?)",
        (agent_name, action, str(details))
    )


def get_recent_activity(limit: int = 20) -> list[dict]:
    return query_all(
        "SELECT * FROM agent_activity_log ORDER BY id DESC LIMIT ?",
        (limit,)
    )
