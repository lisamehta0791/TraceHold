"""Exasol connection helpers.

Connection settings come from environment variables, falling back to the
Exasol Personal starter-kit defaults (local nano runtime on 127.0.0.1:8563,
SYS password stored by the starter kit).
"""
from __future__ import annotations

import os
import re
import ssl
from pathlib import Path

import pyexasol

ROOT = Path(__file__).resolve().parents[2]          # repository root
BACKEND = ROOT / "backend"
RESULTS = BACKEND / "results"
SQL_DIR = ROOT / "database"

DSN = os.environ.get("TRACEHOLD_DSN", "127.0.0.1:8563")
USER = os.environ.get("TRACEHOLD_USER", "sys")
_PW_FILE = Path(os.environ.get(
    "TRACEHOLD_PASSWORD_FILE",
    Path.home() / ".exasol-starter-kit" / "credentials" / "nano_sys_password",
))
SCHEMA = os.environ.get("TRACEHOLD_SCHEMA", "TRACEHOLD")
GT_SCHEMA = os.environ.get("TRACEHOLD_GT_SCHEMA", "TRACEHOLD_GT")


def _password() -> str:
    if "TRACEHOLD_PASSWORD" in os.environ:
        return os.environ["TRACEHOLD_PASSWORD"]
    if _PW_FILE.exists():
        return _PW_FILE.read_text().strip()
    raise RuntimeError(
        f"No Exasol password: set TRACEHOLD_PASSWORD or create {_PW_FILE}")


def connect(schema: str | None = None, **kw) -> pyexasol.ExaConnection:
    return pyexasol.connect(
        dsn=DSN,
        user=USER,
        password=_password(),
        schema=schema or "",
        encryption=True,
        # The local runtime uses a self-signed certificate.
        websocket_sslopt={"cert_reqs": ssl.CERT_NONE},
        compression=True,
        fetch_dict=kw.pop("fetch_dict", True),
        **kw,
    )


def split_sql(text: str) -> list[str]:
    """Split a script into statements on ';' at line end, skipping comments."""
    stmts, buf = [], []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") and not buf:
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            if stmt and not all(l.strip().startswith("--") for l in stmt.splitlines()):
                stmts.append(stmt)
            buf = []
    tail = "\n".join(buf).strip()
    if tail and not all(l.strip().startswith("--") for l in tail.splitlines()):
        stmts.append(tail)
    return stmts


def render(sql: str, **params) -> str:
    """Substitute {NAME} placeholders (schema names, config constants)."""
    def sub(m):
        key = m.group(1)
        if key not in params:
            raise KeyError(f"Missing SQL parameter {key}")
        return str(params[key])
    return re.sub(r"\{([A-Z_][A-Z0-9_]*)\}", sub, sql)


def load_sql(name: str, **params) -> list[str]:
    return split_sql(render((SQL_DIR / name).read_text(encoding="utf-8"), **params))
