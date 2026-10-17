"""Makes sure the AI tables exist before any AI feature uses them.

Reloading the data with `app.load --fresh` rebuilds the whole TRACEHOLD schema,
which also removes the AI tables. Instead of failing, the AI features recreate
them (and reload the synthetic letters) the first time they are needed.
"""
from __future__ import annotations

import threading

from app import db

_lock = threading.Lock()
_REQUIRED = ("REQUEST_DOCUMENTS", "EXTRACTION_RESULTS", "EXTRACTION_CONFIRMATIONS", "AI_LOG", "ASK_LOG")


def ensure_ai_tables(conn=None) -> bool:
    """Returns True if the tables had to be (re)created."""
    own = conn is None
    conn = conn or db.connect()
    try:
        with _lock:
            found = {r[0] if not isinstance(r, dict) else list(r.values())[0] for r in conn.execute(
                "SELECT TABLE_NAME FROM EXA_ALL_TABLES WHERE TABLE_SCHEMA = {s}", {"s": db.SCHEMA}).fetchall()}
            if all(t in found for t in _REQUIRED):
                return False
            from app.ai_setup import RESULTS_SCHEMA, load_letters
            for stmt in db.load_sql("90_ai.sql", S=db.SCHEMA, GT=db.GT_SCHEMA, R=RESULTS_SCHEMA):
                conn.execute(stmt)
            conn.commit()
            try:
                load_letters(conn, db.ROOT / "data" / "L")
                conn.commit()
            except FileNotFoundError:
                pass  # no generated data folder: letters can still be pasted
            return True
    finally:
        if own:
            conn.close()
