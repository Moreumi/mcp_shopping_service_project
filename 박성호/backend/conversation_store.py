"""Small durable conversation state for demo follow-up continuity."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from threading import Lock
import time
from contextlib import closing


DB_PATH = Path(os.getenv("CONVERSATION_DB", "data/conversations.sqlite3"))
RETENTION_DAYS = int(os.getenv("CONVERSATION_RETENTION_DAYS", "7"))
_lock = Lock()
_initialized = False


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _initialize():
    global _initialized
    if _initialized:
        return
    with _lock:
        if _initialized:
            return
        with closing(_connect()) as connection:
            with connection:
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS conversations (
                        user_id TEXT NOT NULL,
                        thread_id TEXT NOT NULL,
                        state_json TEXT NOT NULL,
                        updated_at INTEGER NOT NULL,
                        PRIMARY KEY (user_id, thread_id)
                    )"""
                )
                cutoff = int(time.time()) - RETENTION_DAYS * 86400
                connection.execute("DELETE FROM conversations WHERE updated_at < ?", (cutoff,))
        _initialized = True


def load_conversation(user_id: str, thread_id: str) -> dict:
    _initialize()
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT state_json FROM conversations WHERE user_id = ? AND thread_id = ?",
            (user_id, thread_id),
        ).fetchone()
    if not row:
        return {}
    try:
        value = json.loads(row[0])
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def save_conversation(user_id: str, thread_id: str, state: dict) -> None:
    _initialize()
    payload = json.dumps(
        {
            "products": state.get("products", [])[:3],
            "history": state.get("history", [])[-20:],
        },
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    with closing(_connect()) as connection:
        with connection:
            connection.execute(
                """INSERT INTO conversations(user_id, thread_id, state_json, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(user_id, thread_id) DO UPDATE SET
                       state_json = excluded.state_json,
                       updated_at = excluded.updated_at""",
                (user_id, thread_id, payload, int(time.time())),
            )
