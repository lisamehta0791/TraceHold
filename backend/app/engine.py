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
import re
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
    orchestration: str = "python"   # python (steps sent from Python) or lua (one Exasol script)

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


class ProtectedObjectError(RuntimeError):
    """An analysis statement tried to change source data, history or the answer key."""


_MUTATING = re.compile(
    r"^\s*(?:DROP\s+(?:TABLE|VIEW|SCHEMA)(?:\s+IF\s+EXISTS)?|DELETE\s+FROM|TRUNCATE\s+TABLE|UPDATE|MERGE\s+INTO|"
    r"INSERT\s+INTO|ALTER\s+TABLE|CREATE\s+(?:OR\s+REPLACE\s+)?(?:TABLE|VIEW)(?:\s+IF\s+NOT\s+EXISTS)?|RENAME\s+\w+)"
    r"\s+([\w\"]+(?:\.[\w\"]+)?)", re.I)


def check_statement(sql: str) -> None:
    """Second line of defence behind Exasol's privileges: analysis SQL may only create, change or drop its own
    calculation tables. Anything aimed at a source table, the audit history or the answer key is refused."""
    for part in [p for p in re.split(r";\s*\n", sql) if p.strip()]:
        body = "\n".join(ln for ln in part.splitlines() if not ln.strip().startswith("--"))
        m = _MUTATING.match(body)
        if not m:
            continue
        if re.match(r"\s*DROP\s+SCHEMA", body, re.I):
            raise ProtectedObjectError(f"Refused: the analysis never drops a schema. Statement: {body.strip()[:160]}")
        target = m.group(1).replace('"', "").upper()
        schema, _, name = target.rpartition(".")
        if schema in (db.SRC_SCHEMA, db.AUDIT_SCHEMA, db.GT_SCHEMA) or name in db.SOURCE_TABLES:
            raise ProtectedObjectError(f"Refused: the analysis may not change {target} (source data, history or "
                                       f"answer key). Statement: {body.strip()[:160]}")


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
        check_statement(sql)
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
        self.layers_used = layers
        self.request_checks()
        self.run_file("50_review.sql", "CF5 scope review, CF4 dilution")
        self.run_file("60_additional.sql", "AF1 lien review, AF4 speed")
        if self.dialect == "exasol":
            self.run_file("70_evidence.sql", "CF7 evidence items")
        self.run_file("80_summary.sql", "Case summaries")
        return layers

    def request_checks(self):
        """CF1: the checklist lives in a table so it can change per jurisdiction."""
        t = time.perf_counter()
        self.params["MISSING_SQL"] = missing_sql(self.conn, self.schema)
        for s in db.load_sql("40_requests.sql", **self.params):
            self.exec(s)
        self._record("CF1 request completeness and consistency", (time.perf_counter() - t) * 1000, file="40_requests.sql")


def missing_sql(conn, S: str) -> str:
    """One SELECT per required checklist item (CHECKLIST_ITEMS), joined with UNION ALL."""
    allowed = {"issuing_officer", "designation", "agency", "agency_contact", "case_reference",
               "legal_provision", "action_type", "stated_amount", "quoted_txn_id"}
    items = conn.execute(
        f"SELECT item_code, field_name, label FROM {S}.CHECKLIST_ITEMS WHERE required = TRUE ORDER BY sort_order"
    ).fetchall()
    parts = []
    for it in items:
        it = {k.lower(): v for k, v in it.items()} if isinstance(it, dict) else \
            dict(zip(("item_code", "field_name", "label"), it))
        f = it["field_name"].lower()
        if f not in allowed:
            continue
        label = it["label"].replace("'", "''")
        parts.append(
            f"SELECT request_id, '{it['item_code']}' AS item_code, '{label}' AS label, 'MISSING' AS kind, "
            f"'{label} is not stated' AS detail FROM {S}.REQUESTS "
            f"WHERE NULLIF(TRIM(CAST({f} AS VARCHAR(200))), '') IS NULL")
    return " UNION ALL ".join(parts) if parts else \
        f"SELECT request_id, '' , '', 'MISSING', '' FROM {S}.REQUESTS WHERE 1 = 0"


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


def audit_schema(schema: str) -> str:
    """The full dataset keeps its history in TRACEHOLD_AUDIT; other schemas (benchmark tiers) keep their own."""
    return db.AUDIT_SCHEMA if schema == db.SCHEMA else schema


def start_run(conn, schema: str, cfg: Config) -> int:
    S, A = schema, audit_schema(schema)
    # A run that never finished (process stopped) is closed off as failed.
    conn.execute(f"UPDATE {A}.RUNS SET run_status = 'FAILED', error_text = 'Interrupted before it finished' "
                 f"WHERE run_status = 'RUNNING'")
    rid = conn.execute(f"SELECT COALESCE(MAX(run_id), 0) + 1 AS N FROM {A}.RUNS").fetchval()
    snap = conn.execute(f"SELECT info_value FROM {S}.DATASET_INFO WHERE info_key = 'snapshot_id'").fetchval()
    conn.execute(
        f"INSERT INTO {A}.RUNS (run_id, started, run_status, snapshot_id, software_version, config_json) "
        f"VALUES ({{rid}}, CURRENT_TIMESTAMP, 'RUNNING', {{snap}}, {{ver}}, {{cfg}})",
        {"rid": rid, "snap": snap, "ver": SOFTWARE_VERSION, "cfg": json.dumps(asdict(cfg))})
    return int(rid)


SOURCE_FOR_FINGERPRINT = ("INSTITUTIONS", "ACCOUNTS", "TRANSACTIONS", "CASES", "CASE_DISPUTED_TXNS", "REQUESTS",
                          "REQUEST_TARGETS", "RESTRAINTS", "CHECKLIST_ITEMS", "DATASET_INFO")


def source_fingerprints(conn, schema: str) -> dict[str, tuple[int, int]]:
    """Row count and an order-independent fingerprint (sum of per-row MD5 hashes) of every source table."""
    out = {}
    for t in SOURCE_FOR_FINGERPRINT:
        cols = [r[0] if not isinstance(r, dict) else list(r.values())[0] for r in conn.execute(
            "SELECT COLUMN_NAME FROM EXA_ALL_COLUMNS WHERE COLUMN_SCHEMA = {s} AND COLUMN_TABLE = {t} "
            "ORDER BY COLUMN_ORDINAL_POSITION", {"s": schema, "t": t}).fetchall()]
        if not cols:
            continue
        row = " || '|' || ".join(f"COALESCE(CAST(\"{c}\" AS VARCHAR(4000)), '~')" for c in cols)
        r = conn.execute(f"SELECT COUNT(*), COALESCE(SUM(TO_NUMBER(SUBSTR(HASH_MD5({row}), 1, 15), "
                         f"'XXXXXXXXXXXXXXX')), 0) FROM {schema}.{t}").fetchone()
        vals = list(r.values()) if isinstance(r, dict) else list(r)
        out[t] = (int(vals[0]), int(vals[1]))
    return out


HISTORY = [
    ("SIZING_HISTORY", "SIZING", "case_id, account_id, layer, balance_ref, retained_pr, retained_fifo, retained_lifo, "
                                 "lower_amt, upper_amt, share_lo, share_hi, status"),
    ("REVIEW_HISTORY", "REVIEW", "request_id, case_id, account_id, requested_scope, requested_amount, lower_amt, "
                                 "upper_amt, classification, ratio_to_upper"),
    ("CASE_SUMMARY_HISTORY", "CASE_SUMMARY", "case_id, request_status, requested_total, supported_lower, supported_upper, "
                                             "whole_balance, excess, conservation_ok"),
    ("TRAIL_HISTORY", "TRAIL_EDGES", "case_id, txn_id, from_acct, to_acct, layer, carried_pr, carried_fifo, carried_lifo, "
                                     "terminal_state"),
]


def run_full(schema: str | None = None, cfg: Config | None = None, log=print, run_id: int | None = None,
             on_step=None, mode: str = "python") -> dict:
    """mode="python": steps orchestrated from Python. mode="lua": the whole analysis runs as one Exasol Lua
    script (EXECUTE SCRIPT TRACEHOLD.RUN_ANALYSIS()); fingerprints, history and checksum are the same."""
    schema = (schema or db.SCHEMA).upper()
    A = audit_schema(schema)
    src = db.SRC_SCHEMA if schema == db.SCHEMA else schema
    cfg = cfg or Config()
    cfg.orchestration = mode
    conn = db.connect()
    rid = run_id or start_run(conn, schema, cfg)
    t0 = time.perf_counter()
    steps = [0]

    def record(no, step):
        steps[0] = no
        conn.execute(f"INSERT INTO {A}.RUN_STEPS VALUES ({{r}}, {{n}}, {{s}}, {{ms}}, {{rows}})",
                     {"r": rid, "n": no, "s": step["step"], "ms": step["ms"], "rows": step["rows"]})
        if on_step:
            on_step(no, step)

    def fingerprint(phase):
        t = time.perf_counter()
        fps = source_fingerprints(conn, src)
        for name, (n, fp) in fps.items():
            conn.execute(f"INSERT INTO {A}.SOURCE_FINGERPRINTS VALUES ({{r}}, {{p}}, {{t}}, {{n}}, {{f}}, CURRENT_TIMESTAMP)",
                         {"r": rid, "p": phase, "t": name, "n": n, "f": fp})
        conn.commit()
        record(steps[0] + 1, {"step": f"Fingerprint source data ({phase.lower()})", "ms": round((time.perf_counter() - t) * 1000, 1),
                              "rows": sum(n for n, _ in fps.values()), "file": None})
        return fps

    try:
        log(f"[run {rid}] {schema} started")
        before = fingerprint("BEFORE")
        if mode == "lua":
            from app.lua_script import SCRIPT, install
            install()
            log(f"  ...  EXECUTE SCRIPT {SCRIPT}() (the whole analysis inside Exasol)")
            rows = conn.execute(f"EXECUTE SCRIPT {SCRIPT}()").fetchall()
            layers = 0
            for r in rows:
                vals = list(r.values()) if isinstance(r, dict) else list(r)
                label, n, ms = vals[0], vals[1], float(vals[2])
                layers += label.startswith("CF2/CF3 layer pass")
                record(steps[0] + 1, {"step": label, "ms": round(ms, 1), "rows": None if n is None else int(n),
                                      "file": step_file(label)})
                log(f"  {label:42s} {ms / 1000:7.2f}s (Lua script)")
        else:
            eng = Engine(conn, schema, cfg, log=log, run_id=rid, on_step=record)
            eng.full()
            layers = eng.layers_used
        t = time.perf_counter()
        for hist, table, cols in HISTORY:
            conn.execute(f"INSERT INTO {A}.{hist} SELECT {rid}, {cols} FROM {schema}.{table}")
        conn.commit()
        record(steps[0] + 1, {"step": "Save results to history", "ms": round((time.perf_counter() - t) * 1000, 1),
                              "rows": None, "file": None})
        after = fingerprint("AFTER")
        if before != after:
            changed = [k for k in before if before[k] != after.get(k)]
            raise RuntimeError(f"Source data changed during the run: {', '.join(changed)}")
        checksum = results_checksum(conn, schema)
        dur = time.perf_counter() - t0
        conn.execute(
            f"UPDATE {A}.RUNS SET finished = CURRENT_TIMESTAMP, run_status = 'DONE', checksum = {{c}}, "
            f"duration_s = {{d}} WHERE run_id = {{r}}", {"c": checksum, "d": dur, "r": rid})
        conn.commit()
        log(f"[run {rid}] done in {dur:.1f}s, {layers} layer passes, {checksum[:23]}; source data unchanged")
        return {"run_id": rid, "duration_s": dur, "checksum": checksum, "layers": layers}
    except Exception as e:  # record the failure, then re-raise
        conn.execute(f"UPDATE {A}.RUNS SET finished = CURRENT_TIMESTAMP, run_status = 'FAILED', "
                     f"error_text = {{e}} WHERE run_id = {{r}}", {"e": str(e)[:1900], "r": rid})
        conn.commit()
        raise
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schema", default=db.SCHEMA)
    ap.add_argument("--ref-rule", default="REQUEST")
    ap.add_argument("--lua", action="store_true", help="run the whole analysis as one Exasol Lua script")
    a = ap.parse_args()
    run_full(a.schema, Config(ref_rule=a.ref_rule), mode="lua" if a.lua else "python")


if __name__ == "__main__":
    main()
