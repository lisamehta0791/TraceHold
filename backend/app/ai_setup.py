"""One-time setup for the AI features (CF9, AF7, AF8).

    python -m app.ai_setup            # from the backend folder

1. Creates the AI tables and the results-only view schema (database/90_ai.sql).
2. Generates the synthetic letters (if missing) and loads them into Exasol;
   their answer key goes to the ground-truth schema.
3. Installs Exasol's open-source MCP server in the project's own environment
   (.venv-mcp; it needs an older database driver than the app, so it is kept apart).
4. Creates the read-only user the question-answering page connects as through
   Exasol's MCP server, stores its password in .env, and proves it can read the
   results views and nothing else.
"""
from __future__ import annotations

import csv
import secrets
import sys
from pathlib import Path

from app import ENV_FILE, db

RESULTS_SCHEMA = "TH_RESULTS"
READER = "TH_ASK"


def _set_env(key: str, value: str) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [ln for ln in lines if not ln.strip().startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_letters(conn, data_dir: Path) -> int:
    docs = data_dir / "request_documents.csv"
    if not docs.exists():
        sys.path.insert(0, str(db.BACKEND / "generator"))
        from letters import build  # noqa: E402
        build(data_dir, 24, 60)
    S, GT = db.SCHEMA, db.GT_SCHEMA
    rows = list(csv.DictReader(open(docs, encoding="utf-8")))
    conn.execute(f"TRUNCATE TABLE {S}.REQUEST_DOCUMENTS")
    conn.import_from_iterable(
        [(int(r["doc_id"]), int(r["request_id"]), int(r["case_id"]), r["split"], r["body"]) for r in rows],
        (S, "REQUEST_DOCUMENTS"))
    truth = list(csv.DictReader(open(data_dir / "gt" / "letter_truth.csv", encoding="utf-8")))
    conn.execute(f"TRUNCATE TABLE {GT}.LETTER_TRUTH")
    conn.import_from_iterable([(int(t["doc_id"]), t["field"], t["true_value"] or None) for t in truth],
                              (GT, "LETTER_TRUTH"))
    return len(rows)


def create_reader(conn) -> str:
    import os
    pw = os.environ.get("TRACEHOLD_ASK_PASSWORD") or ("Th" + secrets.token_urlsafe(18).replace("-", "x").replace("_", "y"))
    exists = conn.execute("SELECT COUNT(*) FROM EXA_DBA_USERS WHERE USER_NAME = {u}", {"u": READER}).fetchval()
    if exists:
        conn.execute(f'ALTER USER {READER} IDENTIFIED BY "{pw}"')
    else:
        conn.execute(f'CREATE USER {READER} IDENTIFIED BY "{pw}"')
    conn.execute(f"GRANT CREATE SESSION TO {READER}")
    conn.execute(f"GRANT SELECT ON SCHEMA {RESULTS_SCHEMA} TO {READER}")
    conn.commit()
    _set_env("TRACEHOLD_ASK_PASSWORD", pw)
    return pw


def prove_read_only(pw: str) -> list[str]:
    import pyexasol
    import ssl
    c = pyexasol.connect(dsn=db.DSN, user=READER, password=pw, encryption=True,
                         websocket_sslopt={"cert_reqs": ssl.CERT_NONE}, fetch_dict=False)
    out = []
    try:
        n = c.execute(f"SELECT COUNT(*) FROM {RESULTS_SCHEMA}.CASES").fetchval()
        out.append(f"can read {RESULTS_SCHEMA}.CASES ({n} rows)")
        for blocked in (f"{db.SCHEMA}.TRANSACTIONS", f"{db.GT_SCHEMA}.LEDGER", f"{db.GT_SCHEMA}.LETTER_TRUTH"):
            try:
                c.execute(f"SELECT COUNT(*) FROM {blocked}")
                raise RuntimeError(f"reader can read {blocked}: privileges are too wide")
            except pyexasol.ExaQueryError:
                out.append(f"cannot read {blocked} (as intended)")
        try:
            c.execute(f"CREATE TABLE {RESULTS_SCHEMA}.ZZ (a INT)")
            raise RuntimeError("reader can create tables")
        except pyexasol.ExaQueryError:
            out.append("cannot create or change tables (as intended)")
    finally:
        c.close()
    return out


def install_mcp_server() -> str:
    import subprocess
    from app.ai.mcp_client import MCP_VENV, SERVER_PACKAGE
    exe = MCP_VENV / ("Scripts/exasol-mcp-server.exe" if sys.platform == "win32" else "bin/exasol-mcp-server")
    if exe.exists():
        return f"already installed in {MCP_VENV.name}"
    subprocess.run([sys.executable, "-m", "venv", str(MCP_VENV)], check=True)
    pip = MCP_VENV / ("Scripts/pip.exe" if sys.platform == "win32" else "bin/pip")
    version = SERVER_PACKAGE.split("@")[-1]
    subprocess.run([str(pip), "install", "-q", f"exasol-mcp-server=={version}"], check=True)
    return f"installed exasol-mcp-server {version} in {MCP_VENV.name}"


def main():
    print(f"[ai] MCP server: {install_mcp_server()}")
    conn = db.connect()
    try:
        for stmt in db.load_sql("90_ai.sql", S=db.SCHEMA, GT=db.GT_SCHEMA, R=RESULTS_SCHEMA):
            conn.execute(stmt)
        conn.commit()
        print(f"[ai] tables and {RESULTS_SCHEMA} views ready")
        n = load_letters(conn, db.ROOT / "data" / "L")
        conn.commit()
        print(f"[ai] {n} synthetic letters loaded (answer key in {db.GT_SCHEMA}.LETTER_TRUTH)")
        pw = create_reader(conn)
        for line in prove_read_only(pw):
            print(f"[ai] {READER}: {line}")
        print("[ai] reader password stored in .env (TRACEHOLD_ASK_PASSWORD)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
