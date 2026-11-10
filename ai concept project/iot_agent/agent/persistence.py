"""Durable LangGraph checkpoints and case-scoped structured memory."""
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from langgraph.checkpoint.sqlite import SqliteSaver

import config

MEMORY_DB = config.CACHE_DIR / "agent_memory.sqlite"
CHECKPOINT_DB = config.CACHE_DIR / "agent_checkpoints.sqlite"


def _connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


@contextmanager
def _database(path: Path):
    connection = _connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _ensure_case_facts(connection):
    connection.execute(
        """CREATE TABLE IF NOT EXISTS case_facts (
            case_id TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (case_id, question)
        )"""
    )


@lru_cache(maxsize=1)
def get_checkpointer():
    connection = _connect(CHECKPOINT_DB)
    checkpointer = SqliteSaver(connection)
    checkpointer.setup()
    return checkpointer


def load_case_facts(case_id):
    with _database(MEMORY_DB) as connection:
        _ensure_case_facts(connection)
        rows = connection.execute(
            """SELECT question, answer FROM case_facts
               WHERE case_id = ? ORDER BY updated_at DESC LIMIT 50""",
            (case_id,),
        ).fetchall()
    return [{"question": question, "answer": answer} for question, answer in rows]


def save_case_facts(case_id, facts):
    if not facts:
        return
    with _database(MEMORY_DB) as connection:
        _ensure_case_facts(connection)
        connection.executemany(
            """INSERT INTO case_facts (case_id, question, answer)
               VALUES (?, ?, ?)
               ON CONFLICT(case_id, question) DO UPDATE SET
                   answer = excluded.answer,
                   updated_at = CURRENT_TIMESTAMP""",
            [
                (case_id, fact["question"], fact["answer"])
                for fact in facts
            ],
        )


def get_or_create_interactive_thread(case_id):
    with _database(MEMORY_DB) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS interactive_sessions (
                case_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        row = connection.execute(
            "SELECT thread_id FROM interactive_sessions WHERE case_id = ? AND status = 'active'",
            (case_id,),
        ).fetchone()
        if row:
            return row[0]
        thread_id = str(uuid4())
        connection.execute(
            """INSERT INTO interactive_sessions (case_id, thread_id, status)
               VALUES (?, ?, 'active')
               ON CONFLICT(case_id) DO UPDATE SET
                   thread_id = excluded.thread_id,
                   status = 'active',
                   updated_at = CURRENT_TIMESTAMP""",
            (case_id, thread_id),
        )
        return thread_id


def close_interactive_thread(case_id, thread_id, status="completed"):
    """Mark a thread finished; `status` is 'completed' or 'abandoned'."""
    with _database(MEMORY_DB) as connection:
        connection.execute(
            """UPDATE interactive_sessions SET status = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE case_id = ? AND thread_id = ?""",
            (status, case_id, thread_id),
        )
