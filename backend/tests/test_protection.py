"""Source data and history cannot be damaged by the analysis.

- Every analysis SQL statement passes the engine's guard (no statement aimed at source tables, history or answer key).
- The guard refuses such statements.
- Exasol itself refuses them for the analysis user (privileges).
- Source fingerprints are stable when nothing changes.
"""
import pytest

from app import db
from app.engine import Config, ProtectedObjectError, check_statement

ANALYSIS_SQL = ["10_prepare.sql", "11_case_ref.sql", "20_trace_seed.sql", "21_trace_step.sql", "22_trace_swap.sql",
                "30_trail.sql", "31_taint_step.sql", "32_sizing.sql", "40_requests.sql", "50_review.sql",
                "60_additional.sql", "70_evidence.sql", "80_summary.sql"]


def test_every_analysis_statement_passes_the_guard():
    params = Config().sql_params(db.SCHEMA)
    params["MISSING_SQL"] = "SELECT 1 FROM DUAL WHERE 1 = 0"
    n = 0
    for name in ANALYSIS_SQL:
        for stmt in db.load_sql(name, **params):
            check_statement(stmt)
            n += 1
    assert n > 100


@pytest.mark.parametrize("sql", [
    "DROP TABLE IF EXISTS TRACEHOLD.TRANSACTIONS", "DELETE FROM TRACEHOLD_SRC.ACCOUNTS", "UPDATE TRACEHOLD.REQUESTS SET x = 1",
    "TRUNCATE TABLE TRACEHOLD_AUDIT.RUNS", "CREATE OR REPLACE TABLE TRACEHOLD.CASES AS SELECT 1", "DROP SCHEMA TRACEHOLD_SRC CASCADE",
    "INSERT INTO TRACEHOLD_GT.LEDGER VALUES (1)", "-- harmless comment\nDROP TABLE TRACEHOLD_SRC.RESTRAINTS",
])
def test_guard_refuses_damaging_statements(sql):
    with pytest.raises(ProtectedObjectError):
        check_statement(sql)


def test_guard_allows_calculation_tables():
    check_statement("DROP TABLE IF EXISTS TRACEHOLD.EV")
    check_statement("CREATE TABLE TH_PLAYGROUND.SIZING AS SELECT * FROM TH_PLAYGROUND.TRANSACTIONS")


@pytest.mark.db
def test_exasol_refuses_the_analysis_user():
    if not db.engine_ready():
        pytest.skip("run python -m app.secure first")
    from app.secure import prove_protection
    checks = prove_protection()
    assert all(c["ok"] for c in checks), [c for c in checks if not c["ok"]]
    assert sum(c["result"] == "refused" for c in checks) >= 9


@pytest.mark.db
def test_fingerprints_are_stable():
    from app.engine import source_fingerprints
    c = db.connect(admin=True)
    try:
        a = source_fingerprints(c, db.SRC_SCHEMA)
        b = source_fingerprints(c, db.SRC_SCHEMA)
    finally:
        c.close()
    assert a == b and a["TRANSACTIONS"][0] > 0


@pytest.mark.db
def test_lua_script_is_generated_from_the_same_sql():
    from app.lua_script import build
    c = db.connect(fetch_dict=False)
    try:
        lua = build(c)
    finally:
        c.close()
    assert "CREATE OR REPLACE LUA SCRIPT TRACEHOLD.RUN_ANALYSIS()" in lua
    assert "CF2/CF3 layer pass" in lua and "CF6 abstention pass" in lua   # both repeat-until-stable loops
    assert "TRACEHOLD_SRC" not in lua and "TRACEHOLD_GT" not in lua         # reads source only through views
