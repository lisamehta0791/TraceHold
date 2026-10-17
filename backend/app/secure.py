"""Protected database layout: Exasol itself guarantees that the analysis cannot
damage the source data or the history.

    python -m app.secure          # from the backend folder (safe to repeat)

Schemas and who may do what:

    TRACEHOLD_SRC    source data (transactions, accounts, requests ...)   engine: SELECT only
    TRACEHOLD        views of the source + disposable calculation tables  engine: owner (rebuilds them each run)
    TH_PLAYGROUND    scratch area for live analyses                       engine: owner
    TRACEHOLD_AUDIT  run log, results history, fingerprints, AI logs      engine: SELECT + INSERT (UPDATE run status)
    TRACEHOLD_GT     the generator's answer key                           engine: scenario labels only

The app and the analysis connect as TH_ENGINE. Loading, this set-up and the
evaluation against the answer key connect as the administrator.

An existing installation (source tables inside TRACEHOLD) is migrated: every
table is copied, the copy is counted, and only then is the old table removed.
"""
from __future__ import annotations

import re
import secrets
import ssl

import pyexasol

from app import ENV_FILE, db

PLAYGROUND = "TH_PLAYGROUND"
RETRACE = "TH_RETRACE"   # scratch area for live re-traces of one case
LEGACY_AUDIT = ("RUNS", "RUN_STEPS")
LEGACY_AI = ("EXTRACTION_RESULTS", "EXTRACTION_CONFIRMATIONS", "AI_LOG", "ASK_LOG")
INSERT_ONLY = ("RUN_STEPS", "SOURCE_FINGERPRINTS", "SIZING_HISTORY", "REVIEW_HISTORY", "CASE_SUMMARY_HISTORY",
               "TRAIL_HISTORY", "LIVE_ANALYSES") + LEGACY_AI


def _set_env(key: str, value: str) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [ln for ln in lines if not ln.strip().startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _objects(conn, schema: str) -> dict[str, str]:
    """name -> TABLE / VIEW for one schema."""
    rows = conn.execute("SELECT OBJECT_NAME, OBJECT_TYPE FROM EXA_DBA_OBJECTS WHERE ROOT_NAME = {s} "
                        "AND OBJECT_TYPE IN ('TABLE', 'VIEW')", {"s": schema}).fetchall()
    return {r[0]: r[1] for r in rows}


def _count(conn, obj: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {obj}").fetchval())


def _ddl_by_table(sql_file: str, **params) -> dict[str, str]:
    out = {}
    for stmt in db.load_sql(sql_file, **params):
        m = re.search(r"CREATE (?:OR REPLACE )?TABLE (?:IF NOT EXISTS )?\S+?\.(\w+)", stmt)
        if m:
            out[m.group(1).upper()] = stmt
    return out


def _move(conn, src: str, dst: str, log):
    """Copy a legacy table into its new home, check the count, then drop the old one."""
    n_old = _count(conn, src)
    n_new_before = _count(conn, dst)
    if n_new_before == 0 and n_old:
        conn.execute(f"INSERT INTO {dst} SELECT * FROM {src}")
    n_new = _count(conn, dst)
    if n_new < n_old:
        raise RuntimeError(f"Copy of {src} is incomplete ({n_new} of {n_old} rows); nothing was removed.")
    conn.execute(f"DROP TABLE {src}")
    conn.commit()
    log(f"[secure] moved {src} -> {dst} ({n_old:,} rows, copy verified)")


def ensure_layout(conn=None, log=print) -> dict:
    """Idempotent. Always uses its own administrator connection (the conn argument is accepted for compatibility)."""
    own = True
    conn = db.connect(admin=True, fetch_dict=False)
    S, SRC, A, GT = db.SCHEMA, db.SRC_SCHEMA, db.AUDIT_SCHEMA, db.GT_SCHEMA
    try:
        for sch in (SRC, A, S, PLAYGROUND, PLAYGROUND + "_GT", RETRACE, GT):
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {sch}")
        conn.commit()

        # 1. source tables live in TRACEHOLD_SRC
        src_ddl = _ddl_by_table("00_schema.sql", S=SRC)
        have_src = _objects(conn, SRC)
        for t, stmt in src_ddl.items():
            if t not in have_src:
                conn.execute(stmt.replace("CREATE OR REPLACE TABLE", "CREATE TABLE"))
        conn.commit()
        work = _objects(conn, S)
        for t in src_ddl:
            if work.get(t) == "TABLE":
                _move(conn, f"{S}.{t}", f"{SRC}.{t}", log)

        # 2. history lives in TRACEHOLD_AUDIT
        for stmt in db.load_sql("01_audit.sql", A=A):
            conn.execute(stmt)
        conn.commit()
        for stmt in db.load_sql("90_ai.sql", S=S, SRC=SRC, A=A, GT=GT, R="TH_RESULTS"):
            if "CREATE OR REPLACE VIEW" in stmt:
                continue  # results views are created below, once the work tables exist
            conn.execute(stmt)
        conn.commit()
        work = _objects(conn, S)
        for t in LEGACY_AUDIT + LEGACY_AI:
            if work.get(t) == "TABLE":
                _move(conn, f"{S}.{t}", f"{A}.{t}", log)
        if work.get("REQUEST_DOCUMENTS") == "TABLE":
            _move(conn, f"{S}.REQUEST_DOCUMENTS", f"{SRC}.REQUEST_DOCUMENTS", log)

        # 3. the limited engine user
        import os
        pw = os.environ.get("TRACEHOLD_ENGINE_PASSWORD") or ("Te" + secrets.token_urlsafe(20).replace("-", "x").replace("_", "y"))
        exists = conn.execute("SELECT COUNT(*) FROM EXA_DBA_USERS WHERE USER_NAME = {u}", {"u": db.ENGINE_USER}).fetchval()
        conn.execute(f'{"ALTER" if exists else "CREATE"} USER {db.ENGINE_USER} IDENTIFIED BY "{pw}"')
        # IMPORT still needs INSERT on the target table, which the engine has only in its own schemas and the audit log
        # SELECT ANY DICTIONARY: read-only access to Exasol's system statistics ("Exasol at work" page)
        for priv in ("CREATE SESSION", "CREATE TABLE", "CREATE VIEW", "IMPORT", "SELECT ANY DICTIONARY", "CREATE SCRIPT"):
            conn.execute(f"GRANT {priv} TO {db.ENGINE_USER}")
        for sch in (S, PLAYGROUND, PLAYGROUND + "_GT", RETRACE):
            conn.execute(f"ALTER SCHEMA {sch} CHANGE OWNER {db.ENGINE_USER}")
        conn.execute(f"GRANT SELECT ON SCHEMA {SRC} TO {db.ENGINE_USER}")
        conn.execute(f"GRANT SELECT ON SCHEMA {A} TO {db.ENGINE_USER}")
        conn.execute(f"GRANT INSERT, UPDATE ON {A}.RUNS TO {db.ENGINE_USER}")
        for t in INSERT_ONLY:
            conn.execute(f"GRANT INSERT ON {A}.{t} TO {db.ENGINE_USER}")
        if "CASE_SCENARIO" in _objects(conn, GT):
            conn.execute(f"GRANT SELECT ON {GT}.CASE_SCENARIO TO {db.ENGINE_USER}")
        conn.commit()
        _set_env("TRACEHOLD_ENGINE_PASSWORD", pw)
        os.environ["TRACEHOLD_ENGINE_PASSWORD"] = pw

        # 4. the analysis reads the source through views in its own schema
        for t in src_ddl:
            conn.execute(f"CREATE OR REPLACE VIEW {S}.{t} AS SELECT * FROM {SRC}.{t}")
        conn.execute(f"CREATE OR REPLACE VIEW {S}.REQUEST_DOCUMENTS AS SELECT * FROM {SRC}.REQUEST_DOCUMENTS")
        conn.commit()

        # 5. results views for the question user (only once the analysis has produced its tables)
        if "CASE_SUMMARY" in _objects(conn, S):
            for stmt in db.load_sql("90_ai.sql", S=S, SRC=SRC, A=A, GT=GT, R="TH_RESULTS"):
                if "CREATE OR REPLACE VIEW" in stmt or "CREATE SCHEMA" in stmt:
                    conn.execute(stmt)
            conn.commit()
        return {"engine_user": db.ENGINE_USER}
    finally:
        if own:
            conn.close()


# ---------------------------------------------------------------- proof
FORBIDDEN = [
    ("Delete the transactions", "DROP TABLE {SRC}.TRANSACTIONS"),
    ("Delete rows from the transactions", "DELETE FROM {SRC}.TRANSACTIONS WHERE 1 = 0"),
    ("Change an account", "UPDATE {SRC}.ACCOUNTS SET opening_balance = 0 WHERE 1 = 0"),
    ("Empty the requests", "TRUNCATE TABLE {SRC}.REQUESTS"),
    ("Add rows to the transactions", "INSERT INTO {SRC}.TRANSACTIONS SELECT * FROM {SRC}.TRANSACTIONS WHERE 1 = 0"),
    ("Delete the whole source schema", "DROP SCHEMA {SRC} CASCADE"),
    ("Delete the run history", "DELETE FROM {A}.RUNS WHERE 1 = 0"),
    ("Drop the results history", "DROP TABLE {A}.SIZING_HISTORY"),
    ("Empty the AI log", "TRUNCATE TABLE {A}.AI_LOG"),
    ("Read the answer key", "SELECT COUNT(*) FROM {GT}.LEDGER"),
]
ALLOWED = [
    ("Read the transactions (through the view)", "SELECT COUNT(*) FROM {S}.TRANSACTIONS"),
    ("Read the run history", "SELECT COUNT(*) FROM {A}.RUNS"),
]


def prove_protection() -> list[dict]:
    """Connects as the engine user and tries every forbidden statement; Exasol must refuse each one."""
    import os
    p = {"S": db.SCHEMA, "SRC": db.SRC_SCHEMA, "A": db.AUDIT_SCHEMA, "GT": db.GT_SCHEMA}
    c = pyexasol.connect(dsn=db.DSN, user=db.ENGINE_USER, password=os.environ["TRACEHOLD_ENGINE_PASSWORD"],
                         encryption=True, websocket_sslopt={"cert_reqs": ssl.CERT_NONE}, fetch_dict=False,
                         autocommit=False)
    out = []
    try:
        for label, sql in FORBIDDEN + ALLOWED:
            stmt = sql.format(**p)
            expect_refused = (label, sql) in FORBIDDEN
            try:
                r = c.execute(stmt)
                detail = f"allowed ({r.fetchval():,} rows)" if stmt.startswith("SELECT") else "allowed"
                refused = False
            except pyexasol.ExaQueryError as e:
                msg = str(e.message) if hasattr(e, "message") else str(e)
                detail = re.sub(r"\s*\(Session: \d+\)", "", msg).strip()
                refused = True
            finally:
                c.rollback()
            out.append({"action": label, "statement": stmt, "expected": "refused" if expect_refused else "allowed",
                        "result": "refused" if refused else "allowed", "ok": refused == expect_refused,
                        "exasol_says": detail[:200]})
    finally:
        c.close()
    return out


def main():
    ensure_layout()
    print(f"[secure] the app and the analysis now connect as {db.ENGINE_USER} (password stored in .env)")
    for r in prove_protection():
        mark = "OK " if r["ok"] else "!! "
        print(f"[secure] {mark}{r['action']:45s} {r['result']:8s} {r['exasol_says'][:90]}")


if __name__ == "__main__":
    main()
