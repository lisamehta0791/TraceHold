"""The whole analysis as one Exasol Lua script: EXECUTE SCRIPT TRACEHOLD.RUN_ANALYSIS()

The same SQL files the Python engine runs are rendered once and embedded in a
Lua script, including the two loops that repeat until nothing changes (trail
expansion and abstention). Every statement passes the engine's guard before it
is embedded. Running the script needs nothing but Exasol: no Python, no client.

    python -m app.lua_script install      # (re)create the script
    python -m app.lua_script run          # full run through the script (recorded like any run)
"""
from __future__ import annotations

import sys

from app import db
from app.engine import Config, check_statement, missing_sql

SCRIPT = f"{db.SCHEMA}.RUN_ANALYSIS"

STEPS = [  # (label, file) in the same order as Engine.full()
    ("Prepare: clean postings, balances, skew", "10_prepare.sql"),
    ("Cases in scope, reference times", "11_case_ref.sql"),
    ("CF2 seed disputed transfers", "20_trace_seed.sql"),
    ("@TRACE_LOOP", None),
    ("CF2 trail edges", "30_trail.sql"),
    ("@TAINT_LOOP", None),
    ("CF3 sizing, CF6 status, conservation", "32_sizing.sql"),
    ("CF1 request completeness and consistency", "40_requests.sql"),
    ("CF5 scope review, CF4 dilution", "50_review.sql"),
    ("AF1 lien review, AF4 speed", "60_additional.sql"),
    ("CF7 evidence items", "70_evidence.sql"),
    ("Case summaries", "80_summary.sql"),
]


def _lua_block(stmts: list[str]) -> str:
    out = []
    for s in stmts:
        check_statement(s)
        if "]==]" in s:
            raise ValueError("statement contains the Lua long-string terminator")
        out.append(f"    query([==[{s}]==])")
    return "\n".join(out)


def build(conn) -> str:
    S = db.SCHEMA
    params = Config().sql_params(S)
    params["MISSING_SQL"] = missing_sql(conn, S)
    sig = (f"SELECT (SELECT COUNT(*) FROM {S}.PR_IN_NEW) || '|' || (SELECT COALESCE(SUM(d), 0) FROM {S}.PR_IN_NEW) || '|' || "
           f"(SELECT COUNT(*) FROM {S}.FIFO_SEG_NEW) || '|' || (SELECT COALESCE(SUM(hi - lo), 0) FROM {S}.FIFO_SEG_NEW) || '|' || "
           f"(SELECT COUNT(*) FROM {S}.LIFO_SEG_NEW) || '|' || (SELECT COALESCE(SUM(hi - lo), 0) FROM {S}.LIFO_SEG_NEW) AS SIG, "
           f"(SELECT COUNT(*) FROM {S}.PR_IN_NEW) + (SELECT COUNT(*) FROM {S}.FIFO_SEG_NEW) + "
           f"(SELECT COUNT(*) FROM {S}.LIFO_SEG_NEW) AS N FROM DUAL")
    body = []
    for label, file in STEPS:
        if label == "@TRACE_LOOP":
            step = _lua_block(db.load_sql("21_trace_step.sql", **params))
            swap = _lua_block(db.load_sql("22_trace_swap.sql", **params))
            body.append(f"""  local prev = nil
  local layers = 0
  for i = 1, {Config().max_iter} do
    local t = now()
{step}
    local r = query([==[{sig}]==])[1]
{swap}
    query([[COMMIT]])
    log("CF2/CF3 layer pass " .. i, r.N, t)
    layers = i
    if prev ~= nil and r.SIG == prev then break end
    prev = r.SIG
  end""")
        elif label == "@TAINT_LOOP":
            step = _lua_block(db.load_sql("31_taint_step.sql", **params))
            body.append(f"""  local prev_t = -1
  for i = 1, {Config().max_iter} do
    local t = now()
{step}
    local n = query([[SELECT COUNT(*) AS N FROM {S}.TAINT]])[1].N
    query([[COMMIT]])
    log("CF6 abstention pass " .. i, n, t)
    if n == prev_t then break end
    prev_t = n
  end""")
        else:
            block = _lua_block(db.load_sql(file, **params))
            body.append(f"""  do
    local t = now()
{block}
    query([[COMMIT]])
    log("{label}", null, t)
  end""")
    steps_lua = "\n".join(body)
    return f"""CREATE OR REPLACE LUA SCRIPT {SCRIPT}() RETURNS TABLE AS
-- TraceHold: the complete analysis, generated from database/*.sql. Every figure is computed here, in Exasol.
local out = {{}}
function now()
  return query([[SELECT SECONDS_BETWEEN(SYSTIMESTAMP, TIMESTAMP '2026-01-01 00:00:00') AS T FROM DUAL]])[1].T
end
function log(label, n, t0)
  out[#out + 1] = {{label, n, (now() - t0) * 1000}}
end
{steps_lua}
exit(out, "step VARCHAR(100), row_count DECIMAL(18,0), ms DOUBLE")
"""


def install() -> int:
    conn = db.connect(fetch_dict=False)
    try:
        sql = build(conn)
        conn.execute(sql)
        conn.commit()
        return len(sql)
    finally:
        conn.close()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "install"
    n = install()
    print(f"[lua] installed {SCRIPT}() ({n:,} characters, generated from database/*.sql)")
    if cmd == "run":
        from app.engine import run_full
        r = run_full(mode="lua")
        print(f"[lua] run {r['run_id']} done in {r['duration_s']:.1f}s, {r['checksum'][:23]}")


if __name__ == "__main__":
    main()
