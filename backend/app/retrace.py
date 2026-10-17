"""Live re-trace of one case on the full ledger (2.4 million transactions), inside Exasol.

The full run cleans every posting and rebuilds every running balance once
(10_prepare.sql). A re-trace reuses that prepared ledger through views and
runs the case steps (11-32) for a single case in its own scratch schema,
TH_RETRACE, then compares the figures with the stored results. Nothing stored
is touched: the scratch schema holds only this re-trace's own tables.
"""
from __future__ import annotations

import threading
import time

from app import db
from app.basis import group_steps
from app.engine import Config, Engine

SCHEMA = "TH_RETRACE"
PREPARED = ("ACC_FLAGS", "EV", "OBS_ACC", "SKEW_FIX", "TXN_CLEAN", "TXN_DUP", "TXN_REV")
_lock = threading.Lock()
_views_ready = False


def _ensure_views(conn):
    global _views_ready
    if _views_ready:
        return
    for t in PREPARED:
        conn.execute(f"CREATE OR REPLACE VIEW {SCHEMA}.{t} AS SELECT * FROM {db.SCHEMA}.{t}")
    for t in db.SOURCE_TABLES:
        if t != "REQUEST_DOCUMENTS":
            conn.execute(f"CREATE OR REPLACE VIEW {SCHEMA}.{t} AS SELECT * FROM {db.SRC_SCHEMA}.{t}")
    conn.commit()
    _views_ready = True


def retrace(case_id: int) -> dict:
    if not _lock.acquire(blocking=False):
        raise RuntimeError("Another live re-trace is running; try again in a few seconds.")
    try:
        conn = db.connect(autocommit=False)
        try:
            running = conn.execute(f"SELECT COUNT(*) FROM {db.AUDIT_SCHEMA}.RUNS WHERE run_status = 'RUNNING'").fetchval()
            if running:
                raise RuntimeError("A full analysis run is rebuilding the ledger; re-trace when it has finished.")
            _ensure_views(conn)
            steps: list[dict] = []
            eng = Engine(conn, SCHEMA, Config(), log=lambda m: None, on_step=lambda i, s: steps.append(s))
            eng.step_commit = True
            t0 = time.perf_counter()
            layers = eng.size_cases(f"c.case_id = {int(case_id)}")
            ms = (time.perf_counter() - t0) * 1000
            rows = conn.execute(f"""
                SELECT n.account_id, n.layer, n.retained_pr, n.retained_fifo, n.retained_lifo, n.lower_amt, n.upper_amt,
                       n.status, o.retained_pr AS old_pr, o.retained_fifo AS old_fifo, o.retained_lifo AS old_lifo,
                       o.status AS old_status
                FROM {SCHEMA}.SIZING n
                LEFT JOIN {db.SCHEMA}.SIZING o ON o.case_id = n.case_id AND o.account_id = n.account_id
                WHERE n.case_id = {{c}} ORDER BY n.layer, n.account_id""", {"c": int(case_id)}).fetchall()
            ledger = conn.execute(f"SELECT COUNT(*) FROM {db.SRC_SCHEMA}.TRANSACTIONS").fetchval()
            conn.commit()
        finally:
            conn.close()
    finally:
        _lock.release()

    def close(a, b):
        return (a is None and b is None) or (a is not None and b is not None and abs(float(a) - float(b)) < 0.005)
    accounts = []
    for r in rows:
        r = {k.lower(): v for k, v in r.items()}
        same = close(r["retained_pr"], r["old_pr"]) and close(r["retained_fifo"], r["old_fifo"]) and \
            close(r["retained_lifo"], r["old_lifo"]) and r["status"] == r["old_status"]
        accounts.append({"account_id": r["account_id"], "layer": r["layer"],
                         "retained_pr": _f(r["retained_pr"]), "retained_fifo": _f(r["retained_fifo"]),
                         "lower": _f(r["lower_amt"]), "upper": _f(r["upper_amt"]), "status": r["status"],
                         "matches_stored": same})
    return {"case_id": case_id, "ms": round(ms), "layers": layers, "ledger_transactions": int(ledger),
            "steps": group_steps(steps), "accounts": accounts,
            "identical": bool(accounts) and all(a["matches_stored"] for a in accounts), "schema": SCHEMA}


def _f(x):
    return None if x is None else round(float(x), 2)
