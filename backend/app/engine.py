"""TraceHold analysis orchestrator.

The application layer only sequences SQL; every calculation runs inside the
database as set-based SQL. Trail expansion is iterative (one pass per layer)
because Exasol Personal does not support WITH RECURSIVE and the design does not
depend on UDFs.

    python -m app.engine                 # full run on TRACEHOLD, recorded in RUNS
    python -m app.engine --schema LL_XS  # run against another schema
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime

from app import db

SOFTWARE_VERSION = "1.0.0"


@dataclass
class Config:
    dust: float = 1.0                # rupees; smaller flows are not traced further
    dup_window_s: int = 600          # duplicate posting window
    skew_tol_s: int = 120            # clock-skew tolerance
    ref_rule: str = "REQUEST"        # REQUEST | ANALYSIS | FIXED
    ref_fixed_epoch: int = 0         # used when ref_rule == FIXED
    max_iter: int = 60
    fast_minutes: int = 30           # "moved onward within N minutes" fact
    share_alert: float = 0.10        # CF4 dilution alert threshold
    review_interval_days: int = 90   # AF1, restraints above the lien threshold
    lien_threshold: float = 50000.0  # AF1 band boundary (2 Jan 2026 procedure as reported)
    as_of: str = "2026-10-15"        # AF1 "today"
    conventions: list = field(default_factory=lambda: ["PR", "FIFO", "LIFO"])

    def sql_params(self, schema: str) -> dict:
        if self.ref_rule == "REQUEST":
            ref = (f"COALESCE((SELECT MIN(r.received_epoch) FROM {schema}.REQUESTS r "
                   f"WHERE r.case_id = c.case_id), c.fraud_epoch + 86400)")
        elif self.ref_rule == "ANALYSIS":
            ref = f"(SELECT MAX(ts_epoch) FROM {schema}.TRANSACTIONS)"
        else:
            ref = str(int(self.ref_fixed_epoch))
        return dict(S=schema, DUST=repr(float(self.dust)), DUP_WINDOW=int(self.dup_window_s),
                    SKEW_TOL=int(self.skew_tol_s), REF_EXPR=ref, FAST_MIN=int(self.fast_minutes),
                    SHARE_ALERT=repr(float(self.share_alert)),
                    REVIEW_DAYS=int(self.review_interval_days), LIEN_THRESHOLD=repr(float(self.lien_threshold)),
                    AS_OF=self.as_of, CASE_FILTER="1 = 1")


# Step label (as stored in RUN_STEPS) -> the SQL script it ran.
_STEP_FILES = [
    ("Prepare", "10_prepare.sql"), ("Cases in scope", "11_case_ref.sql"), ("CF2 seed", "20_trace_seed.sql"),
    ("CF2/CF3 layer pass", "21_trace_step.sql"), ("CF2 trail edges", "30_trail.sql"),
    ("CF6 abstention pass", "31_taint_step.sql"), ("CF3 sizing", "32_sizing.sql"),
    ("CF1 request", "40_requests.sql"), ("CF5 scope review", "50_review.sql"), ("AF1 lien review", "60_additional.sql"),
    ("CF7 evidence", "70_evidence.sql"), ("Case summaries", "80_summary.sql"),
]


def step_file(label: str) -> str | None:
    return next((f for prefix, f in _STEP_FILES if label.startswith(prefix)), None)


class Engine:
    def __init__(self, conn, schema: str, cfg: Config | None = None, log=print, dialect="exasol",
                 run_id: int | None = None, on_step=None):
        self.conn = conn
        self.schema = schema
        self.cfg = cfg or Config()
        self.params = self.cfg.sql_params(schema)
        self.log = log
        self.dialect = dialect
        self.steps: list[dict] = []
        self.run_id = run_id
        self.on_step = on_step
        # With autocommit off, commit once per step instead of once per
        # statement (used by the benchmark on both engines).
        self.step_commit = False

    # ------------------------------------------------------------ helpers
    def exec(self, sql: str):
        if self.dialect == "exasol":
            return self.conn.execute(sql)
        cur = self.conn.cursor()
        cur.execute(sql)
        return cur

    def scalar_row(self, sql: str):
        if self.dialect == "exasol":
            return self.conn.execute(sql).fetchone()
        cur = self.conn.cursor()
        cur.execute(sql)
        return cur.fetchone()

    def run_file(self, name: str, label: str):
        self.log(f"  ...  {label}")
        t = time.perf_counter()
        stmts = db.load_sql(name, **self.params)
        for s in stmts:
            self.exec(s)
        self._record(label, (time.perf_counter() - t) * 1000, file=name)

    def _commit(self):
        if self.step_commit:
            self.conn.commit()

    def _record(self, label, ms, rows=None, file=None):
        self._commit()
        step = {"step": label, "ms": round(ms, 1), "rows": rows, "file": file or step_file(label)}
        self.steps.append(step)
        self.log(f"  {label:42s} {ms / 1000:7.2f}s" + (f"  rows={rows}" if rows is not None else ""))
        if self.on_step:
            self.on_step(len(self.steps), step)

    def _state_signature(self):
        S = self.schema
        row = self.scalar_row(
            f"SELECT (SELECT COUNT(*) FROM {S}.PR_IN_NEW), (SELECT COALESCE(SUM(d), 0) FROM {S}.PR_IN_NEW),"
            f" (SELECT COUNT(*) FROM {S}.FIFO_SEG_NEW), (SELECT COALESCE(SUM(hi - lo), 0) FROM {S}.FIFO_SEG_NEW),"
            f" (SELECT COUNT(*) FROM {S}.LIFO_SEG_NEW), (SELECT COALESCE(SUM(hi - lo), 0) FROM {S}.LIFO_SEG_NEW)")
        return tuple(float(v) if isinstance(v, (int, float)) or v is not None else 0.0 for v in
                     (row.values() if isinstance(row, dict) else row))

    @staticmethod
    def _same(a, b):
        return a is not None and all(abs(x - y) <= 1e-6 * max(1.0, abs(x)) for x, y in zip(a, b))

    # ------------------------------------------------------------ pipeline
    def trace(self):
        self.run_file("20_trace_seed.sql", "CF2 seed disputed transfers")
        prev = None
        for i in range(1, self.cfg.max_iter + 1):
            t = time.perf_counter()
            for s in db.load_sql("21_trace_step.sql", **self.params):
                self.exec(s)
            sig = self._state_signature()
            converged = self._same(prev, sig)
            for s in db.load_sql("22_trace_swap.sql", **self.params):
                self.exec(s)
            self._record(f"CF2/CF3 layer pass {i}", (time.perf_counter() - t) * 1000, rows=int(sig[0] + sig[2] + sig[4]),
                         file="21_trace_step.sql")
            if converged:
                return i
            prev = sig
        raise RuntimeError(f"Trail expansion did not converge in {self.cfg.max_iter} passes")

    def taint(self):
        self.run_file("30_trail.sql", "CF2 trail edges")
        S = self.schema
        prev = -1
        for i in range(1, self.cfg.max_iter + 1):
            t = time.perf_counter()
            for s in db.load_sql("31_taint_step.sql", **self.params):
                self.exec(s)
            n = self.scalar_row(f"SELECT COUNT(*) FROM {S}.TAINT")
            n = int(list(n.values())[0] if isinstance(n, dict) else n[0])
            self._record(f"CF6 abstention pass {i}", (time.perf_counter() - t) * 1000, rows=n, file="31_taint_step.sql")
            if n == prev:
                break
            prev = n

    # Indexes a reasonable engineer would add on a row store. Exasol creates
    # and maintains its indexes automatically, so it needs none of these.
    PG_INDEXES = [
        "CREATE INDEX ON {S}.EV (account_id, kind, ev_rank)",
        "CREATE INDEX ON {S}.EV (txn_id, kind, account_id)",
        "CREATE INDEX ON {S}.EV (account_id, ord_epoch)",
        "CREATE INDEX ON {S}.TXN_CLEAN (txn_id)",
        "ANALYZE {S}.EV",
        "ANALYZE {S}.TXN_CLEAN",
    ]

    def prepare(self):
        self.run_file("10_prepare.sql", "Prepare: clean postings, balances, skew (longest step, 2-4 minutes)")
        if self.dialect == "postgres":
            t = time.perf_counter()
            for s in self.PG_INDEXES:
                self.exec(s.format(S=self.schema))
            self._record("Baseline: create indexes", (time.perf_counter() - t) * 1000)

    def size_cases(self, case_filter: str = "1 = 1"):
        """Trace and size the cases matching the filter, on a prepared ledger."""
        self.params["CASE_FILTER"] = case_filter
        self.run_file("11_case_ref.sql", "Cases in scope, reference times")
        layers = self.trace()
        self.taint()
        self.run_file("32_sizing.sql", "CF3 sizing, CF6 status, conservation")
        return layers

    def core(self):
        """The portable core workload (also run on the benchmark baseline)."""
        self.prepare()
        return self.size_cases()

    def full(self):
        layers = self.core()
        self.request_checks()
        self.run_file("50_review.sql", "CF5 scope review, CF4 dilution")
        self.run_file("60_additional.sql", "AF1 lien review, AF4 speed")
        if self.dialect == "exasol":
            self.run_file("70_evidence.sql", "CF7 evidence items")
        self.run_file("80_summary.sql", "Case summaries")
        return layers

    def request_checks(self):
        """CF1: the checklist lives in a table so it can change per jurisdiction."""
        S = self.schema
        t = time.perf_counter()
        allowed = {"issuing_officer", "designation", "agency", "agency_contact", "case_reference",
                   "legal_provision", "action_type", "stated_amount", "quoted_txn_id"}
        items = self.conn.execute(
            f"SELECT item_code, field_name, label FROM {S}.CHECKLIST_ITEMS WHERE required = TRUE ORDER BY sort_order"
        ).fetchall()
        parts = []
        for it in items:
            it = {k.lower(): v for k, v in it.items()}
            f = it["field_name"].lower()
            if f not in allowed:
                continue
            label = it["label"].replace("'", "''")
            parts.append(
                f"SELECT request_id, '{it['item_code']}' AS item_code, '{label}' AS label, 'MISSING' AS kind, "
                f"'{label} is not stated' AS detail FROM {S}.REQUESTS "
                f"WHERE NULLIF(TRIM(CAST({f} AS VARCHAR(200))), '') IS NULL")
        missing_sql = " UNION ALL ".join(parts) if parts else \
            f"SELECT request_id, '' , '', 'MISSING', '' FROM {S}.REQUESTS WHERE 1 = 0"
        self.params["MISSING_SQL"] = missing_sql
        for s in db.load_sql("40_requests.sql", **self.params):
            self.exec(s)
        self._record("CF1 request completeness and consistency", (time.perf_counter() - t) * 1000, file="40_requests.sql")


# ---------------------------------------------------------------- run log
def results_checksum(conn, schema: str) -> str:
    """Deterministic digest of the derived results (sizing + edges + review)."""
    S = schema
    h = hashlib.sha256()
    for q in (
        f"SELECT case_id, account_id, retained_pr, retained_fifo, retained_lifo, status FROM {S}.SIZING ORDER BY 1, 2",
        f"SELECT case_id, txn_id, CAST(carried_pr AS DECIMAL(18,2)), CAST(carried_fifo AS DECIMAL(18,2)),"
        f" CAST(carried_lifo AS DECIMAL(18,2)) FROM {S}.TRAIL_EDGES ORDER BY 1, 2",
        f"SELECT request_id, account_id, classification FROM {S}.REVIEW ORDER BY 1, 2",
        f"SELECT request_id, status FROM {S}.REQ_STATUS ORDER BY 1",
    ):
        st = conn.execute(q)
        for row in st:
            h.update(repr(tuple(row.values()) if isinstance(row, dict) else tuple(row)).encode())
    return "sha256:" + h.hexdigest()


def start_run(conn, schema: str, cfg: Config) -> int:
    S = schema
    # A run that never finished (process stopped) is closed off as failed.
    conn.execute(f"UPDATE {S}.RUNS SET run_status = 'FAILED', error_text = 'Interrupted before it finished' "
                 f"WHERE run_status = 'RUNNING'")
    rid = conn.execute(f"SELECT COALESCE(MAX(run_id), 0) + 1 AS N FROM {S}.RUNS").fetchval()
    snap = conn.execute(f"SELECT info_value FROM {S}.DATASET_INFO WHERE info_key = 'snapshot_id'").fetchval()
    conn.execute(
        f"INSERT INTO {S}.RUNS (run_id, started, run_status, snapshot_id, software_version, config_json) "
        f"VALUES ({{rid}}, CURRENT_TIMESTAMP, 'RUNNING', {{snap}}, {{ver}}, {{cfg}})",
        {"rid": rid, "snap": snap, "ver": SOFTWARE_VERSION, "cfg": json.dumps(asdict(cfg))})
    return int(rid)


def run_full(schema: str | None = None, cfg: Config | None = None, log=print, run_id: int | None = None,
             on_step=None) -> dict:
    schema = (schema or db.SCHEMA).upper()
    cfg = cfg or Config()
    conn = db.connect()
    rid = run_id or start_run(conn, schema, cfg)
    t0 = time.perf_counter()

    def record(no, step):
        conn.execute(f"INSERT INTO {schema}.RUN_STEPS VALUES ({{r}}, {{n}}, {{s}}, {{ms}}, {{rows}})",
                     {"r": rid, "n": no, "s": step["step"], "ms": step["ms"], "rows": step["rows"]})
        if on_step:
            on_step(no, step)

    try:
        eng = Engine(conn, schema, cfg, log=log, run_id=rid, on_step=record)
        log(f"[run {rid}] {schema} started")
        layers = eng.full()
        checksum = results_checksum(conn, schema)
        dur = time.perf_counter() - t0
        conn.execute(
            f"UPDATE {schema}.RUNS SET finished = CURRENT_TIMESTAMP, run_status = 'DONE', checksum = {{c}}, "
            f"duration_s = {{d}} WHERE run_id = {{r}}", {"c": checksum, "d": dur, "r": rid})
        log(f"[run {rid}] done in {dur:.1f}s, {layers} layer passes, {checksum[:23]}")
        return {"run_id": rid, "duration_s": dur, "checksum": checksum, "layers": layers}
    except Exception as e:  # record the failure, then re-raise
        conn.execute(f"UPDATE {schema}.RUNS SET finished = CURRENT_TIMESTAMP, run_status = 'FAILED', "
                     f"error_text = {{e}} WHERE run_id = {{r}}", {"e": str(e)[:1900], "r": rid})
        raise
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", default=db.SCHEMA)
    ap.add_argument("--ref-rule", default="REQUEST")
    a = ap.parse_args()
    run_full(a.schema, Config(ref_rule=a.ref_rule))


if __name__ == "__main__":
    main()
