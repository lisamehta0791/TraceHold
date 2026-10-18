"""Makes sure the AI tables exist before any AI feature uses them.

Reloading the data with `app.load --fresh` rebuilds the whole TRACEHOLD schema,
which also removes the AI tables. Instead of failing, the AI features recreate
them (and reload the synthetic letters) the first time they are needed.
"""
from __future__ import annotations

import threading

from app import db

_lock = threading.Lock()
_REQUIRED = {"SRC": ("REQUEST_DOCUMENTS",), "A": ("EXTRACTION_RESULTS", "EXTRACTION_CONFIRMATIONS", "AI_LOG", "ASK_LOG")}


def ensure_ai_tables(conn=None) -> bool:
    """Returns True if the tables had to be (re)created."""
    own = conn is None
    conn = conn or db.connect(admin=True)  # creating tables needs the administrator
    try:
        with _lock:
            def names(schema):
                return {r[0] if not isinstance(r, dict) else list(r.values())[0] for r in conn.execute(
                    "SELECT TABLE_NAME FROM EXA_ALL_TABLES WHERE TABLE_SCHEMA = {s}", {"s": schema}).fetchall()}
            if all(t in names(db.SRC_SCHEMA) for t in _REQUIRED["SRC"]) and \
                    all(t in names(db.AUDIT_SCHEMA) for t in _REQUIRED["A"]):
                # app.load --fresh recreates the letters table empty with the layout
                if conn.execute(f"SELECT COUNT(*) FROM {db.SRC_SCHEMA}.REQUEST_DOCUMENTS").fetchval():
                    return False
            from app.ai_setup import load_letters
            from app.secure import ensure_layout
            ensure_layout(log=lambda m: None)  # creates the AI tables, views and grants
            try:
                load_letters(conn, db.ROOT / "data" / "L")
                conn.commit()
            except FileNotFoundError:
                pass  # no generated data folder: letters can still be pasted
            return True
    finally:
        if own:
            conn.close()
