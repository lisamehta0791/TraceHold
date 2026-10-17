"""Load a generated dataset into Exasol Personal.

    python -m app.load data/L                      # into TRACEHOLD_SRC / TRACEHOLD_GT
    python -m app.load data/S --schema LL_S --gt-schema LL_S_GT   (benchmark tiers: plain schemas)

Source data is written by the administrator into TRACEHOLD_SRC, which the
analysis may only read. --fresh replaces the source data; the run history in
TRACEHOLD_AUDIT is never touched.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from app import db

TABLES = [
    ("institutions.csv", "INSTITUTIONS"),
    ("accounts.csv", "ACCOUNTS"),
    ("transactions.csv", "TRANSACTIONS"),
    ("cases.csv", "CASES"),
    ("case_disputed_txns.csv", "CASE_DISPUTED_TXNS"),
    ("requests.csv", "REQUESTS"),
    ("request_targets.csv", "REQUEST_TARGETS"),
    ("restraints.csv", "RESTRAINTS"),
    ("checklist_items.csv", "CHECKLIST_ITEMS"),
]
GT_TABLES = [
    ("gt/case_scenario.csv", "CASE_SCENARIO"),
    ("gt/chain_txns.csv", "CHAIN_TXNS"),
    ("gt/ledger.csv", "LEDGER"),
    ("gt/planted_defects.csv", "PLANTED_DEFECTS"),
]


def load(data_dir: Path, schema: str, gt_schema: str, drop_runs: bool = False, log=print):
    t0 = time.time()
    protected = schema.upper() in (db.SCHEMA, db.SRC_SCHEMA)
    if protected:
        schema = db.SRC_SCHEMA
    conn = db.connect(admin=True)
    conn.execute("ALTER SESSION SET NLS_TIMESTAMP_FORMAT='YYYY-MM-DD HH24:MI:SS'")
    conn.execute("ALTER SESSION SET NLS_DATE_FORMAT='YYYY-MM-DD'")
    if drop_runs:
        conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    for stmt in db.load_sql("00_schema.sql", S=schema) + db.load_sql("02_ground_truth.sql", GT=gt_schema):
        conn.execute(stmt)
    if not protected:  # benchmark tiers keep their run log next to their data
        for stmt in db.load_sql("01_audit.sql", A=schema):
            conn.execute(stmt)
    for fname, table in TABLES:
        _import(conn, data_dir / fname, schema, table, log)
    for fname, table in GT_TABLES:
        _import(conn, data_dir / fname, gt_schema, table, log)
    manifest = json.loads((data_dir / "manifest.json").read_text())
    info = {
        "snapshot_id": manifest["snapshot_id"],
        "generator_version": manifest["generator_version"],
        "seed": str(manifest["seed"]),
        "scale": str(manifest["scale"]),
        "generated_at": manifest["generated_at"],
        "data_dir": str(data_dir),
    }
    conn.execute(f"TRUNCATE TABLE {schema}.DATASET_INFO")
    conn.import_from_iterable(list(info.items()), (schema, "DATASET_INFO"))
    conn.commit()
    log(f"[load] {schema} loaded in {time.time() - t0:.1f}s")
    if protected:
        from app.secure import ensure_layout
        ensure_layout(conn=None, log=log)
        log(f"[load] protected layout ready: the analysis reads {db.SRC_SCHEMA} through views in {db.SCHEMA}")
    conn.close()


def _import(conn, path: Path, schema: str, table: str, log):
    t = time.time()
    header = path.open(encoding="utf-8").readline().strip().split(",")
    conn.execute(f"TRUNCATE TABLE {schema}.{table}")
    conn.import_from_file(
        str(path), (schema, table),
        import_params={"skip": 1, "columns": header, "column_separator": ",",
                       "column_delimiter": '"', "encoding": "UTF8"},
    )
    n = conn.execute(f"SELECT COUNT(*) AS N FROM {schema}.{table}").fetchval()
    log(f"[load] {schema}.{table:20s} {n:>10,} rows  {time.time() - t:5.1f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--schema", default=db.SCHEMA)
    ap.add_argument("--gt-schema", default=db.GT_SCHEMA)
    ap.add_argument("--fresh", action="store_true", help="replace the source data (the run history is kept)")
    a = ap.parse_args()
    load(Path(a.data_dir), a.schema.upper(), a.gt_schema.upper(), a.fresh)


if __name__ == "__main__":
    main()
