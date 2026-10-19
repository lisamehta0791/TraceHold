"""Benchmark: the same TraceHold SQL workloads on Exasol Personal and on a
PostgreSQL baseline, on the same machine, at several data sizes.

    python -m benchmark.run                 # tiers S M L (data/S, data/M, data/L)
    python -m benchmark.run --tiers S       # quick check

Workloads
  W1  trace and size one case on a prepared ledger (five different cases)
  W2  full core: clean postings, build the ledger, trace and size every case
  W3  lien review queue and oversight aggregations over all restraints

Only what is measured here is claimed. Both engines run identical SQL (the
portable scripts in sql/), each analysis step in its own transaction;
PostgreSQL additionally gets the indexes listed in Engine.PG_INDEXES and the
memory settings in PG_SETTINGS, applied up front.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from app import db
from app.engine import Config, Engine

ROOT = db.ROOT
DOCKER = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "DockerDesktop", "resources", "bin", "docker.exe")
if not os.path.exists(DOCKER):
    DOCKER = "docker"
EXASOL_CONTAINER = os.environ.get("TRACEHOLD_CONTAINER", "tracehold-exasol")
PG_CONTAINER, PG_PORT, PG_PW = "tracehold-pg-baseline", 5440, "tracehold"
PG_SETTINGS = ["shared_buffers=1GB", "work_mem=256MB", "maintenance_work_mem=512MB", "effective_cache_size=3GB",
               "max_parallel_workers_per_gather=4", "random_page_cost=1.1", "synchronous_commit=off"]
TABLES = ["institutions", "accounts", "transactions", "cases", "case_disputed_txns", "requests",
          "request_targets", "restraints", "checklist_items"]

OVERSIGHT_SQL = [
    "SELECT CASE WHEN over_hold_ratio IS NULL THEN 'n/a' WHEN over_hold_ratio <= 1 THEN '<=1x' "
    "WHEN over_hold_ratio <= 2 THEN '1-2x' WHEN over_hold_ratio <= 10 THEN '2-10x' ELSE '>10x' END AS b, "
    "COUNT(*) AS n FROM {S}.LIEN_REVIEW WHERE active = 1 GROUP BY 1",
    "SELECT CASE WHEN days_held <= 30 THEN 'a' WHEN days_held <= 90 THEN 'b' ELSE 'c' END AS b, COUNT(*) AS n "
    "FROM {S}.LIEN_REVIEW WHERE active = 1 GROUP BY 1",
    "SELECT issuing_authority, COUNT(*) AS n, SUM(held_amount) AS held, "
    "SUM(GREATEST(held_amount - COALESCE(upper_amt, 0), 0)) AS over_held FROM {S}.LIEN_REVIEW "
    "WHERE active = 1 GROUP BY issuing_authority ORDER BY over_held DESC LIMIT 10",
    "SELECT closure_status, COUNT(*) AS n, AVG(over_hold_ratio) AS r FROM {S}.LIEN_REVIEW WHERE active = 1 "
    "GROUP BY closure_status",
]


# ---------------------------------------------------------------- engines
class ExasolSide:
    name = "Exasol"

    def __init__(self):
        self.conn = db.connect(fetch_dict=False, autocommit=False)

    def version(self):
        return self.conn.execute("SELECT param_value FROM EXA_METADATA WHERE param_name = "
                                 "'databaseProductVersion'").fetchval()

    def load(self, tier, data_dir):
        if tier == "L":
            # The large tier is the application dataset, already loaded in TRACEHOLD;
            # loading a second copy would not fit the 4 GB Docker VM.
            self.reused = True
            self.conn.commit()
            return db.SCHEMA
        from app.load import load
        load(data_dir, f"LL_BENCH_{tier}", f"LL_BENCH_{tier}_GT", drop_runs=True, log=lambda m: None)
        self.conn.commit()   # start a new snapshot that sees the freshly loaded schema
        return f"LL_BENCH_{tier}"

    def engine(self, schema):
        e = Engine(self.conn, schema, Config(), log=lambda m: None, dialect="exasol")
        e.step_commit = True
        return e

    def query(self, sql):
        self.conn.execute(sql).fetchall()


class PostgresSide:
    name = "PostgreSQL"

    def __init__(self):
        import psycopg
        self._ensure_container()
        for _ in range(60):
            try:
                self.conn = psycopg.connect(host="127.0.0.1", port=PG_PORT, user="postgres", password=PG_PW,
                                            dbname="postgres", autocommit=False)
                break
            except Exception:
                time.sleep(2)

    def _ensure_container(self):
        out = subprocess.run([DOCKER, "ps", "-a", "--filter", f"name={PG_CONTAINER}", "--format", "{{.Status}}"],
                             capture_output=True, text=True).stdout.strip()
        if out.startswith("Up"):
            return
        if out:
            subprocess.run([DOCKER, "start", PG_CONTAINER], check=True, capture_output=True)
            return
        cmd = [DOCKER, "run", "-d", "--name", PG_CONTAINER, "-m", "4g", "--shm-size=1g",
               "-p", f"127.0.0.1:{PG_PORT}:5432", "-e", f"POSTGRES_PASSWORD={PG_PW}", "postgres:16.4"]
        for s in PG_SETTINGS:
            cmd += ["-c", s]
        subprocess.run(cmd, check=True, capture_output=True)

    def version(self):
        return self.conn.execute("SHOW server_version").fetchone()[0]

    def load(self, tier, data_dir):
        schema = f"ll_bench_{tier.lower()}"
        ddl = (db.SQL_DIR / "00_schema.sql").read_text(encoding="utf-8")
        ddl = ddl.split("-- ---------------------------------------------------------------- ground truth")[0]
        ddl = re.sub(r"--[^\n]*", "", ddl)
        ddl = re.sub(r",\s*CONSTRAINT [^\n]*DISABLE", "", ddl)
        ddl = re.sub(r"CREATE OR REPLACE TABLE ([^\s(]+)", r"DROP TABLE IF EXISTS \1; CREATE TABLE \1", ddl)
        ddl = ddl.replace("DOUBLE,", "DOUBLE PRECISION,").replace("DOUBLE\n", "DOUBLE PRECISION\n")
        self.conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        for stmt in db.split_sql(db.render(ddl, S=schema, GT=schema + "_gt")):
            for part in stmt.split("; "):
                self.conn.execute(part)
        for t in TABLES:
            path = data_dir / f"{t}.csv"
            header = path.open(encoding="utf-8").readline().strip()
            with self.conn.cursor() as cur:
                with cur.copy(f"COPY {schema}.{t} ({header}) FROM STDIN WITH (FORMAT csv, HEADER true)") as cp:
                    with open(path, "rb") as fh:
                        while chunk := fh.read(1 << 20):
                            cp.write(chunk)
        self.conn.commit()
        self.conn.execute("ANALYZE")
        self.conn.commit()
        return schema

    def engine(self, schema):
        e = Engine(self.conn, schema, Config(), log=lambda m: None, dialect="postgres")
        e.step_commit = True
        return e

    def query(self, sql):
        self.conn.execute(sql).fetchall()


# ---------------------------------------------------------------- workloads
def timed(fn):
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


def pick_cases(side, schema, n=5):
    """The cases with the most trail rows (deterministic), taken after a full run."""
    sql = (f"SELECT case_id FROM {schema}.TRAIL_EDGES GROUP BY case_id ORDER BY COUNT(*) DESC, case_id LIMIT {n}")
    if side.name == "Exasol":
        return [int(r[0]) for r in side.conn.execute(sql).fetchall()]
    return [int(r[0]) for r in side.conn.execute(sql).fetchall()]


TIER_SPEC = {"S": (0.1, 7), "M": (0.4, 11), "L": (1.0, 2026)}   # scale, seed


def ensure_data(tier, data_dir):
    """Generate a tier's dataset if it is not on disk yet."""
    if (data_dir / "manifest.json").exists():
        return
    scale, seed = TIER_SPEC[tier]
    print(f"[bench] generating tier {tier} (scale {scale}) ...", flush=True)
    subprocess.run([sys.executable, str(db.BACKEND / "generator" / "generate.py"), "--scale", str(scale),
                    "--seed", str(seed), "--out", str(data_dir)], check=True)


def run_tier(side, tier, data_dir, reps_w2, reps_w1, reps_w3, cases=None, log=print):
    ensure_data(tier, data_dir)
    rows = []
    side.reused = False
    t_load = timed(lambda: setattr(side, "_schema", side.load(tier, data_dir)))
    schema = side._schema
    n_tx = int(side.conn.execute(f"SELECT COUNT(*) FROM {schema}.TRANSACTIONS").fetchone()[0])
    log(f"  [{side.name} {tier}] {n_tx:,} transactions ready in {t_load:.1f}s")
    if not side.reused:
        rows.append(dict(engine=side.name, tier=tier, workload="LOAD", rows=n_tx, times=[t_load]))

    # W2 first (it also provides the case list and the tables W1 and W3 read).
    w2 = []
    for i in range(reps_w2):
        w2.append(timed(lambda: side.engine(schema).core()))
        log(f"  [{side.name} {tier}] W2 run {i + 1}: {w2[-1]:.2f}s")
    rows.append(dict(engine=side.name, tier=tier, workload="W2", rows=n_tx, times=w2))
    cases = cases or pick_cases(side, schema)

    # W3 on the full results.
    w3 = []
    for i in range(reps_w3):
        def w3_fn():
            e = side.engine(schema)
            e.run_file("60_additional.sql", "AF1/AF4")
            for qsql in OVERSIGHT_SQL:
                side.query(qsql.format(S=schema))
            side.conn.commit()
        w3.append(timed(w3_fn))
    log(f"  [{side.name} {tier}] W3 median {statistics.median(w3):.2f}s")
    rows.append(dict(engine=side.name, tier=tier, workload="W3", rows=n_tx, times=w3))

    # W1: one case at a time on the prepared ledger.
    w1 = []
    for i in range(reps_w1):
        cid = cases[i % len(cases)]
        w1.append(timed(lambda: side.engine(schema).size_cases(f"case_id = {cid}")))
    log(f"  [{side.name} {tier}] W1 median {statistics.median(w1):.2f}s over cases {cases}")
    rows.append(dict(engine=side.name, tier=tier, workload="W1", rows=n_tx, times=w1, cases=cases))
    return rows, cases


def summarise(r):
    t = r["times"]
    warm = t[1:] if len(t) > 2 else t
    return {**{k: v for k, v in r.items() if k != "times"}, "runs": len(t), "times_s": [round(x, 3) for x in t],
            "cold_s": round(t[0], 3), "median_s": round(statistics.median(warm), 3),
            "min_s": round(min(warm), 3), "max_s": round(max(warm), 3)}


def hardware():
    info = {"platform": platform.platform(), "machine": platform.machine(), "cpu_count": os.cpu_count(),
            "python": platform.python_version()}
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-CimInstance Win32_Processor).Name; "
                              "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1)"],
                             capture_output=True, text=True, timeout=30).stdout.split("\n")
        info["cpu"] = out[0].strip()
        info["ram_gb"] = float(out[1].strip())
    except Exception:
        pass
    info["containers"] = "Both databases run in Docker Desktop (WSL2) on this machine with a 4 GB memory limit each."
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tiers", nargs="+", default=["S", "M", "L"])
    ap.add_argument("--engines", nargs="+", default=["Exasol", "PostgreSQL"])
    ap.add_argument("--reps", type=int, default=3)
    a = ap.parse_args()
    sides = {"Exasol": ExasolSide, "PostgreSQL": PostgresSide}
    results, versions = [], {}
    prev = db.RESULTS / "benchmark.json"
    if prev.exists():   # keep results of engines not re-run this time
        old = json.loads(prev.read_text())
        results = [r for r in old.get("results", []) if r["engine"] not in a.engines]
        versions = {k: v for k, v in old.get("versions", {}).items() if k not in a.engines}
    try:
        _run_engines(a, sides, results, versions)
    finally:
        # Whatever happened, PostgreSQL is stopped and Exasol is running again afterwards.
        if "PostgreSQL" in a.engines:
            _docker("stop", "-t", "120", PG_CONTAINER)
            _docker("start", EXASOL_CONTAINER)
            _wait_exasol()


def _run_engines(a, sides, results, versions):
    for name in a.engines:
        # Only one database runs at a time: both share a 4 GB Docker VM.
        if name == "Exasol":
            _docker("stop", "-t", "120", PG_CONTAINER)
            _docker("start", EXASOL_CONTAINER)
            _wait_exasol()
        else:
            # A graceful shutdown: killing Exasol mid-write can corrupt its storage.
            _docker("stop", "-t", "180", EXASOL_CONTAINER)
        side = sides[name]()
        versions[name] = side.version()
        cases_by_tier = {}
        for tier in a.tiers:
            print(f"[bench] {name} tier {tier}", flush=True)
            rows, cases = run_tier(side, tier, ROOT / "data" / tier, reps_w2=a.reps, reps_w1=5, reps_w3=5,
                                   cases=cases_by_tier.get(tier))
            cases_by_tier[tier] = cases
            results += [summarise(r) for r in rows]
            _write(results, versions)
        if name == "Exasol" and "L" in a.tiers:
            # W1 left TRACEHOLD sized for a single case; restore the full results.
            from app.engine import run_full
            run_full(db.SCHEMA, Config(), log=lambda m: None)
    _write(results, versions)


def _docker(*args):
    subprocess.run([DOCKER, *args], capture_output=True)


def _wait_exasol():
    for _ in range(100):
        try:
            db.connect().close()
            return
        except Exception:
            time.sleep(3)


def _write(results, versions):
    out = {"generated_at": datetime.now().isoformat(timespec="seconds"), "hardware": hardware(),
           "versions": versions, "settings": {"postgresql": PG_SETTINGS + ["indexes: see Engine.PG_INDEXES"],
                                              "exasol": "defaults (indexes are automatic)"},
           "method": "Identical SQL on both engines, one transaction per analysis step. The first run of each workload is reported as cold; "
                     "median/min/max are over the remaining (warm) runs. Synthetic data only. "
                     "Only these workloads were measured; no general claim is made.",
           "results": results}
    (db.RESULTS / "benchmark.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
