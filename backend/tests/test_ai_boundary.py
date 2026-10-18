"""The AI boundary.

- The calculation path never imports the AI package.
- The analysis SQL never reads the ground-truth schema.
- With AI switched off, every figure is identical (AI-off test).
- The read-only question user cannot see raw data or the answer key.
"""
import json
import os
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
CALCULATION = ["app/engine.py", "app/playground.py", "app/explain.py", "app/basis.py", "app/load.py", "app/texts.py",
               "app/packet_html.py"]
ANALYSIS_SQL = ["10_prepare.sql", "11_case_ref.sql", "20_trace_seed.sql", "21_trace_step.sql", "22_trace_swap.sql",
                "30_trail.sql", "31_taint_step.sql", "32_sizing.sql", "40_requests.sql", "50_review.sql",
                "60_additional.sql", "70_evidence.sql", "80_summary.sql"]


def test_calculation_path_does_not_import_ai():
    for rel in CALCULATION:
        src = (BACKEND / rel).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from app\.ai|import app\.ai|from app import ai)", src, re.M), rel


def test_analysis_sql_never_reads_ground_truth():
    for name in ANALYSIS_SQL:
        src = (ROOT / "database" / name).read_text(encoding="utf-8")
        assert "{GT}" not in src and "TRACEHOLD_GT" not in src.upper() and "TRACEHOLD_AUDIT" not in src.upper(), name


def test_engine_never_reads_ground_truth():
    src = (BACKEND / "app/engine.py").read_text(encoding="utf-8")
    # the answer-key schema appears only in the guard that refuses changes to it
    assert not re.search(r"(FROM|JOIN)\s+\{?db\.GT_SCHEMA", src)
    guard = src[src.index("def check_statement"):src.index("class Engine")]
    assert src.count("GT_SCHEMA") == guard.count("GT_SCHEMA")


@pytest.mark.db
def test_ai_off_gives_identical_figures(worked):
    from app.playground import run

    def strip(r):
        r = json.loads(json.dumps(r, default=str))
        r.pop("engine", None)
        return r
    before = os.environ.get("TRACEHOLD_AI")
    try:
        os.environ["TRACEHOLD_AI"] = "off"
        off = strip(run(worked))
        os.environ.pop("TRACEHOLD_AI", None)
        on = strip(run(worked))
    finally:
        if before is not None:
            os.environ["TRACEHOLD_AI"] = before
    assert off == on


@pytest.mark.db
def test_question_user_is_read_only():
    if not os.environ.get("TRACEHOLD_ASK_PASSWORD"):
        pytest.skip("run python -m app.ai_setup first")
    from app.ai_setup import prove_read_only
    lines = prove_read_only(os.environ["TRACEHOLD_ASK_PASSWORD"])
    assert any("can read TH_RESULTS.CASES" in ln for ln in lines)
    assert sum("as intended" in ln for ln in lines) >= 4
