"""TraceHold API (FastAPI). All figures are read from derived tables that the
SQL engine computed inside Exasol; this layer only reads, shapes and exports.

    uvicorn app.main:app --port 8000
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pyexasol
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db, texts
from app.engine import SOFTWARE_VERSION, Config, run_full

S = db.SCHEMA
GT = db.GT_SCHEMA
A = db.AUDIT_SCHEMA
ROOT = db.ROOT

app = FastAPI(title="TraceHold API", version=SOFTWARE_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def _timing(request, call_next):
    t = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t) * 1000
    response.headers["Server-Timing"] = f"app;dur={ms:.0f}"
    if ms > 1500:
        import logging
        logging.getLogger("uvicorn.error").warning("slow request %s %.0f ms", request.url.path, ms)
    return response

# ---------------------------------------------------------------- db access
# A small shared pool: the local Exasol runtime handles a few long-lived
# connections far better than one TLS handshake per request thread.
import queue

POOL_SIZE = 4
_pool: "queue.Queue" = queue.Queue()
_pool_lock = threading.Lock()
_pool_created = 0


def _borrow():
    global _pool_created
    try:
        return _pool.get_nowait()
    except queue.Empty:
        pass
    with _pool_lock:
        if _pool_created < POOL_SIZE:
            _pool_created += 1
            try:
                return db.connect(fetch_mapper=pyexasol.exasol_mapper, socket_timeout=120, connection_timeout=60)
            except Exception:
                _pool_created -= 1
                raise
    return _pool.get(timeout=120)


def _give_back(c, broken=False):
    global _pool_created
    if broken:
        try:
            c.close()
        except Exception:
            pass
        with _pool_lock:
            _pool_created -= 1
    else:
        _pool.put(c)


def _norm(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() and abs(v) < 2**53 and v.as_tuple().exponent >= 0 else float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def q(sql: str, params: dict | None = None) -> list[dict]:
    for attempt in (1, 2):
        c = _borrow()
        try:
            st = c.execute(sql, params)
            rows = [{k.lower(): _norm(v) for k, v in r.items()} for r in st.fetchall()]
            _give_back(c)
            return rows
        except (pyexasol.ExaCommunicationError, pyexasol.ExaConnectionError):
            _give_back(c, broken=True)
            if attempt == 2:
                raise
        except Exception:
            _give_back(c)
            raise


def q1(sql: str, params: dict | None = None) -> dict | None:
    rows = q(sql, params)
    return rows[0] if rows else None


def f(x):
    return None if x is None else float(x)


_known_tables: set = set()


def table_exists(name: str, schema: str = S) -> bool:
    # Positive answers are cached: result tables are replaced, never removed,
    # and querying the system catalogue on every request contends with the
    # playground's schema changes.
    if (schema, name) in _known_tables:
        return True
    found = bool(q1("SELECT 1 AS X FROM EXA_ALL_TABLES WHERE TABLE_SCHEMA = {s} AND TABLE_NAME = {t} "
                    "UNION ALL SELECT 1 FROM EXA_ALL_VIEWS WHERE VIEW_SCHEMA = {s} AND VIEW_NAME = {t}",
                    {"s": schema, "t": name}))
    if found:
        _known_tables.add((schema, name))
    return found


_dead_since: dict = {}  # run_id -> when Exasol was first seen doing nothing for it


def _running_run():
    """A run that is really rebuilding the result tables right now.

    A run whose process was stopped (for example the server restarted mid-run) stays
    'RUNNING' in the log. It counts as alive only while Exasol is executing statements
    (or in its first two minutes); once two checks 15 s apart find Exasol idle, it is
    closed off as interrupted so the pages show the last complete results again."""
    try:
        r = q1(f"SELECT run_id, started, SECONDS_BETWEEN(CURRENT_TIMESTAMP, started) AS age FROM {A}.RUNS "
               f"WHERE run_status = 'RUNNING' AND started > ADD_HOURS(CURRENT_TIMESTAMP, -3) ORDER BY run_id DESC LIMIT 1")
        if not r:
            return None
        busy = q1("SELECT COUNT(*) AS n FROM EXA_DBA_SESSIONS WHERE status <> 'IDLE' AND session_id <> CURRENT_SESSION")
        if float(r["age"] or 0) < 120 or (busy and busy["n"]):
            _dead_since.pop(r["run_id"], None)
            return r
        first = _dead_since.setdefault(r["run_id"], time.time())
        if time.time() - first < 15:
            return r
        with db.connect() as conn:
            conn.execute(f"UPDATE {A}.RUNS SET run_status = 'FAILED', finished = CURRENT_TIMESTAMP, "
                         f"error_text = 'Interrupted: the process running it stopped before it finished' "
                         f"WHERE run_id = {{r}} AND run_status = 'RUNNING'", {"r": r["run_id"]})
            conn.commit()
        _dead_since.pop(r["run_id"], None)
        import logging
        logging.getLogger("uvicorn.error").warning("analysis run #%s was interrupted earlier; marked as failed", r["run_id"])
        return None
    except Exception:
        return None


def require_results():
    running = _running_run()
    if running:
        _known_tables.clear()
        raise HTTPException(503, f"An analysis run (#{running['run_id']}) is rebuilding the results inside Exasol. "
                                 "This page reloads by itself when it finishes (about 3 minutes on a laptop).")
    if not table_exists("CASE_SUMMARY"):
        raise HTTPException(409, "The analysis results are not in Exasol yet. Run it once from the backend folder: "
                                 r"..\.venv\Scripts\python -m app.engine   (2-4 minutes), then reload this page.")


_cache: dict = {}


def cached(key: str, fn, ttl: float = 3600.0):
    run = _latest_run_id()
    k = (key, run)
    hit = _cache.get(k)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[k] = (time.time(), val)
    return val


def _latest_run_id():
    try:
        r = q1(f"SELECT MAX(run_id) AS r FROM {A}.RUNS WHERE run_status = 'DONE'")
        return r["r"] if r else None
    except Exception:
        return None


# ---------------------------------------------------------------- health
_health_last = {"t": 0.0, "v": None}


@app.get("/api/health")
def health():
    # The top bar polls this. Serve a recent answer instead of querying again, and
    # never wait on Exasol while a live analysis is rebuilding its schema.
    last = _health_last["v"]
    if last and (time.time() - _health_last["t"] < 20 or _playground_lock.locked()):
        return last
    try:
        v = q1("SELECT param_value AS v FROM EXA_METADATA WHERE param_name = 'databaseProductVersion'")
        counts = {}
        for t in ("ACCOUNTS", "TRANSACTIONS", "CASES"):
            counts[t.lower()] = q1(f"SELECT COUNT(*) AS n FROM {S}.{t}")["n"]
        out = {"db": "ok", "exasol_version": v["v"], "schema": S, "latest_run_id": _latest_run_id(),
               "row_counts": counts}
        _health_last.update(t=time.time(), v=out)
        return out
    except Exception as e:
        import logging
        logging.getLogger("uvicorn.error").warning("health check failed: %r", e)
        return JSONResponse({"db": "error", "error": str(e)[:300]}, status_code=503)


# ---------------------------------------------------------------- overview
@app.get("/api/overview")
def overview():
    require_results()
    return cached("overview", _overview)


def _overview():
    counts = {}
    for t in ("ACCOUNTS", "TRANSACTIONS", "CASES", "REQUESTS", "REQUEST_TARGETS", "RESTRAINTS", "INSTITUTIONS"):
        counts[t.lower()] = q1(f"SELECT COUNT(*) AS n FROM {S}.{t}")["n"]
    run = q1(f"SELECT run_id, started, finished, run_status AS status, duration_s FROM {A}.RUNS "
             f"WHERE run_status = 'DONE' ORDER BY run_id DESC LIMIT 1")
    t = q1(f"""SELECT SUM(loss) AS reported_loss, SUM(whole_balance) AS whole_balance_locked,
                      SUM(requested_total) AS requested_total, SUM(supported_lower) AS supported_lower,
                      SUM(supported_upper) AS supported_upper, SUM(excess) AS unsupported_locked
               FROM {S}.CASE_SUMMARY""")
    status = q(f"SELECT status, COUNT(*) AS n FROM {S}.SIZING WHERE received = 1 GROUP BY status ORDER BY n DESC")
    cls = q(f"""SELECT classification, COUNT(*) AS n FROM {S}.REVIEW
                WHERE request_id NOT IN (SELECT request_id FROM {S}.REQ_FINDINGS WHERE item_code = 'DUPLICATE_REQUEST')
                GROUP BY classification ORDER BY n DESC""")
    rs = q(f"SELECT status AS request_status, COUNT(*) AS n FROM {S}.REQ_STATUS GROUP BY status ORDER BY n DESC")
    sc = q(f"SELECT scenario, COUNT(*) AS n FROM {GT}.CASE_SCENARIO GROUP BY scenario ORDER BY n DESC") \
        if table_exists("CASE_SCENARIO", GT) else []
    cons = q1(f"SELECT COUNT(*) AS checks, SUM(passed) AS passed FROM {S}.CONSERVATION")
    layers = q(f"""SELECT layer, SUM(n_accounts) AS n_accounts,
                          SUM(share_pr * n_accounts) / SUM(n_accounts) AS avg_share_pr,
                          SUM(share_fifo * n_accounts) / SUM(n_accounts) AS avg_share_fifo
                   FROM {S}.DILUTION WHERE layer <= 8 GROUP BY layer ORDER BY layer""")
    return {"counts": counts, "run": run, "totals": {k: f(v) for k, v in t.items()},
            "status_breakdown": status, "classification_breakdown": cls, "request_status_breakdown": rs,
            "scenario_breakdown": sc, "conservation": cons, "layer_profile": layers}


# ---------------------------------------------------------------- cases
SORTS = {"loss": "s.loss DESC", "fraud_ts": "s.fraud_epoch DESC", "overbroad": "s.excess DESC"}


@app.get("/api/cases")
def cases(search: str = "", scenario: str = "", classification: str = "", request_status: str = "",
          page: int = 1, page_size: int = Query(25, le=200), sort: str = "fraud_ts"):
    require_results()
    where, p = ["1 = 1"], {}
    if search:
        where.append("""(UPPER(s.case_ref) LIKE {s} OR CAST(s.case_id AS VARCHAR(12)) = {raw}
                       OR s.case_id IN (SELECT case_id FROM """ + S + """.SIZING WHERE account_id LIKE {s}))""")
        p["s"] = f"%{search.upper()}%"
        p["raw"] = search.strip()
    if scenario:
        where.append(f"g.scenario = {{sc}}")
        p["sc"] = scenario
    if classification:
        where.append("s.worst_classification = {cl}")
        p["cl"] = classification
    if request_status:
        where.append("s.request_status = {rs}")
        p["rs"] = request_status
    w = " AND ".join(where)
    base = f"FROM {S}.CASE_SUMMARY s LEFT JOIN {GT}.CASE_SCENARIO g ON g.case_id = s.case_id WHERE {w}"
    total = q1(f"SELECT COUNT(*) AS n {base}", p)["n"]
    p.update(lim=page_size, off=(max(page, 1) - 1) * page_size)
    rows = q(f"""SELECT s.*, g.scenario {base} ORDER BY {SORTS.get(sort, SORTS['fraud_ts'])}, s.case_id
                LIMIT {{lim!d}} OFFSET {{off!d}}""", p)
    items = [{
        "case_id": r["case_id"], "case_ref": r["case_ref"], "scenario": r["scenario"],
        "reported_loss": f(r["loss"]), "fraud_ts": texts.ts(r["fraud_epoch"]), "ref_ts": texts.ts(r["ref_epoch"]),
        "request_status": r["request_status"], "n_accounts": r["n_accounts"], "max_layer": r["max_layer"],
        "requested_total": f(r["requested_total"]), "supported_lower": f(r["supported_lower"]),
        "supported_upper": f(r["supported_upper"]), "worst_classification": r["worst_classification"],
        "n_out_of_scope": r["n_out_of_scope"], "n_undeterminable": r["n_undeterminable"],
        "conservation_ok": bool(r["conservation_ok"]),
    } for r in rows]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


def _case_core(case_id: int):
    c = q1(f"""SELECT c.*, sm.request_id, sm.request_status FROM {S}.CASE_REF c
               JOIN {S}.CASE_SUMMARY sm ON sm.case_id = c.case_id WHERE c.case_id = {{id}}""", {"id": case_id})
    if not c:
        raise HTTPException(404, f"Case {case_id} not found")
    sc = q1(f"SELECT scenario FROM {GT}.CASE_SCENARIO WHERE case_id = {{id}}", {"id": case_id}) \
        if table_exists("CASE_SCENARIO", GT) else None
    c["scenario"] = sc["scenario"] if sc else None
    return c


def _request_block(case: dict):
    rid = case["request_id"]
    req = q1(f"SELECT * FROM {S}.REQUESTS WHERE request_id = {{r}}", {"r": rid}) if rid else None
    if not req:
        return None, None
    findings = q(f"SELECT * FROM {S}.REQ_FINDINGS WHERE request_id = {{r}} ORDER BY kind DESC, item_code", {"r": rid})
    checklist = q(f"SELECT item_code, label FROM {S}.CHECKLIST_ITEMS WHERE required = TRUE ORDER BY sort_order")
    flagged = {x["item_code"] for x in findings if x["kind"] == "MISSING"}
    items = [{"code": it["item_code"], "label": it["label"], "kind": "OK", "detail": "Stated"}
             for it in checklist if it["item_code"] not in flagged]
    items = [{"code": x["item_code"], "label": x["label"], "kind": x["kind"],
              "detail": x["detail"] + (f" (account {x['account_id']})" if x.get("account_id") and
                                       x["account_id"] not in (x["detail"] or "") else "")}
             for x in findings] + items
    dups = q(f"""SELECT request_id FROM {S}.REQUESTS WHERE case_id = {{c}} AND request_id <> {{r}}""",
             {"c": case["case_id"], "r": rid})
    block = {
        "request_id": rid, "received_ts": texts.ts(req["received_epoch"]),
        "issuing_officer": req["issuing_officer"], "designation": req["designation"], "agency": req["agency"],
        "agency_contact": req["agency_contact"], "case_reference": req["case_reference"],
        "legal_provision": req["legal_provision"], "action_type": req["action_type"],
        "stated_amount": f(req["stated_amount"]), "quoted_txn_id": req["quoted_txn_id"],
        "other_requests": [d["request_id"] for d in dups],
        "completeness": {
            "status": case["request_status"], "items": items,
            "clarification_draft": texts.clarification_draft(req, findings, case["case_ref"]),
        },
    }
    return block, req


MAX_EDGES = 400


@app.get("/api/cases/{case_id}")
def case_detail(case_id: int):
    require_results()
    return _case_detail(case_id)


def _case_detail(case_id: int):
    case = _case_core(case_id)
    request, req_row = _request_block(case)
    p = {"id": case_id}
    sizing = q(f"""SELECT s.*, a.institution_id, i.inst_name, i.observable, a.acct_type, a.holder_label
                   FROM {S}.SIZING s JOIN {S}.ACCOUNTS a ON a.account_id = s.account_id
                   JOIN {S}.INSTITUTIONS i ON i.institution_id = a.institution_id
                   WHERE s.case_id = {{id}} ORDER BY s.layer, s.account_id""", p)
    review = q(f"""SELECT v.*, s.reason_codes FROM {S}.REVIEW v
                   LEFT JOIN {S}.SIZING s ON s.case_id = v.case_id AND s.account_id = v.account_id
                   WHERE v.case_id = {{id}} AND v.request_id = {{r}} ORDER BY v.layer, v.account_id""",
               {"id": case_id, "r": case["request_id"] or -1})
    rev_by_acc = {r["account_id"]: r for r in review}
    # CF3: an account touched by several cases is sized per case and also reported combined.
    combined = {r["account_id"]: r for r in q(f"""
        SELECT z.account_id, COUNT(DISTINCT z.case_id) AS n_cases, SUM(z.lower_amt) AS lower_sum,
               SUM(z.upper_amt) AS upper_sum, MAX(z.balance_ref) AS balance_max
        FROM {S}.SIZING z
        WHERE z.account_id IN (SELECT account_id FROM {S}.SIZING WHERE case_id = {{id}})
        GROUP BY z.account_id HAVING COUNT(DISTINCT z.case_id) > 1""", p)}
    edges_all = q(f"""SELECT e.*, i.inst_name AS to_inst, i.observable AS to_observable
                      FROM {S}.TRAIL_EDGES e
                      LEFT JOIN {S}.ACCOUNTS a ON a.account_id = e.to_acct
                      LEFT JOIN {S}.INSTITUTIONS i ON i.institution_id = a.institution_id
                      WHERE e.case_id = {{id}} AND GREATEST(e.carried_pr, e.carried_fifo, e.carried_lifo) > 0
                      ORDER BY GREATEST(e.carried_pr, e.carried_fifo, e.carried_lifo) DESC""", p)
    truncated = len(edges_all) > MAX_EDGES
    edges_rows = edges_all[:MAX_EDGES]

    nodes, edges = {}, []
    victim = case["victim_account"]
    nodes[victim] = {"account_id": victim, "institution": None, "observable": True, "account_type": "INDIVIDUAL",
                     "is_victim": True, "layer": 0, "status": None, "kind": "VICTIM", "balance": None}
    for s in sizing:
        rv = rev_by_acc.get(s["account_id"], {})
        nodes[s["account_id"]] = {
            "account_id": s["account_id"], "institution": s["inst_name"], "observable": bool(s["observable"]),
            "account_type": s["acct_type"], "holder_label": s["holder_label"], "is_victim": False,
            "kind": "ACCOUNT", "layer": s["layer"] if s["layer"] is not None else None,
            "received": bool(s["received"]),
            "balance": f(s["balance_ref"]), "retained_pr": f(s["retained_pr"]), "retained_fifo": f(s["retained_fifo"]),
            "retained_lifo": f(s["retained_lifo"]), "lower": f(s["lower_amt"]), "upper": f(s["upper_amt"]),
            "lower_ext": f(s["lower_ext"]), "upper_ext": f(s["upper_ext"]), "share_lo": f(s["share_lo"]),
            "share_hi": f(s["share_hi"]), "sensitivity": f(s["sensitivity"]), "status": s["status"],
            "status_reasons": texts.reasons_list(s["reason_codes"]), "reason_codes": s["reason_codes"],
            "requested_scope": rv.get("requested_scope"), "requested_amount": f(rv.get("requested_amount")),
            "classification": rv.get("classification"), "ratio_to_upper": f(rv.get("ratio_to_upper")),
            "in_transit": {"pr": 0.0, "fifo": 0.0, "lifo": 0.0},
            "combined": ({"cases": int(combined[s["account_id"]]["n_cases"]),
                          "lower": f(combined[s["account_id"]]["lower_sum"]),
                          "upper": f(combined[s["account_id"]]["upper_sum"])}
                         if s["account_id"] in combined else None),
        }
    for e in edges_rows:
        frm = e["from_acct"]
        to = e["to_acct"]
        term = e["terminal_state"]
        if to is None:
            to = "SINK:CHARGES" if term == "CHARGES" else "SINK:CASH"
        if frm not in nodes:
            nodes[frm] = {"account_id": frm, "kind": "ACCOUNT", "observable": True, "is_victim": False,
                          "layer": max((e["layer"] or 1) - 1, 0), "status": None, "institution": None}
        if to not in nodes:
            if to.startswith("SINK:"):
                nodes[to] = {"account_id": to, "kind": "SINK", "observable": False, "is_victim": False,
                             "layer": e["layer"], "status": None,
                             "institution": "Cash / wallet withdrawal" if to == "SINK:CASH" else "Bank charges",
                             "in_transit": {"pr": 0.0, "fifo": 0.0, "lifo": 0.0}}
            else:
                nodes[to] = {"account_id": to, "kind": "EXTERNAL", "observable": False, "is_victim": False,
                             "institution": e["to_inst"], "layer": e["layer"], "status": "OUT_OF_SCOPE",
                             "status_reasons": ["Funds moved to an account outside the available records; "
                                                "a forwarded request is drafted."],
                             "in_transit": {"pr": 0.0, "fifo": 0.0, "lifo": 0.0}}
        n = nodes[to]
        if n.get("kind") in ("SINK", "EXTERNAL"):
            n["in_transit"]["pr"] += f(e["carried_pr"])
            n["in_transit"]["fifo"] += f(e["carried_fifo"])
            n["in_transit"]["lifo"] += f(e["carried_lifo"])
            n["layer"] = min(n["layer"] or 99, e["layer"] or 99)
        flags = []
        if e["skew_adjusted"]:
            flags.append("SKEW_ADJUSTED")
        if e["partly_reversed"]:
            flags.append("PARTLY_REVERSED")
        edges.append({"txn_id": e["txn_id"], "from": frm, "to": to, "ts": texts.ts(e["ts_epoch"]),
                      "amount": f(e["amount"]), "channel": e["channel"], "layer": e["layer"],
                      "carried_pr": round(f(e["carried_pr"]), 2), "carried_fifo": round(f(e["carried_fifo"]), 2),
                      "carried_lifo": round(f(e["carried_lifo"]), 2), "terminal_state": term, "flags": flags,
                      "reference": e["txn_ref"]})
    for n in nodes.values():
        n.setdefault("balance", None)
        if n.get("layer") is None:
            n["layer"] = 1
        for k in ("in_transit",):
            if k in n:
                n[k] = {a: round(b, 2) for a, b in n[k].items()}

    review_out = []
    for r in review:
        review_out.append({
            "account_id": r["account_id"], "layer": r["layer"], "requested_scope": r["requested_scope"],
            "requested_amount": f(r["requested_amount"]), "balance": f(r["balance_ref"]),
            "lower": f(r["lower_amt"]), "upper": f(r["upper_amt"]), "status": r["status"],
            "classification": r["classification"], "ratio_to_upper": f(r["ratio_to_upper"]),
            "excess_over_upper": f(r["excess_over_upper"]),
            "reasons": texts.review_reasons(r),
            "facts": {"cases_through_account": r["cases_through_account"],
                      "share_moved_within_minutes": f(r["share_moved_fast"]), "minutes_window": Config().fast_minutes,
                      "commingling": f(r["commingling"]), "separable": bool(r["separable"])},
        })
    dilution = q(f"SELECT layer, n_accounts, share_pr, share_fifo, below_threshold FROM {S}.DILUTION "
                 f"WHERE case_id = {{id}} ORDER BY layer", p)
    oos = q(f"""SELECT o.*, i.inst_name FROM {S}.OUT_OF_SCOPE o
                LEFT JOIN {S}.ACCOUNTS a ON a.account_id = o.to_acct
                LEFT JOIN {S}.INSTITUTIONS i ON i.institution_id = a.institution_id
                WHERE o.case_id = {{id}} ORDER BY o.ts_epoch""", p)
    missing_fields = [lbl for key, lbl in (("issuing_officer", "issuing officer"), ("designation", "designation"),
                                           ("agency_contact", "agency contact"), ("legal_provision", "legal provision"))
                      if not (req_row or {}).get(key)]
    case_info = {"case_ref": case["case_ref"], "loss": case["loss"]}
    forwarded = [{
        "txn_id": o["txn_id"], "destination_account": o["to_acct"], "destination_institution": o["inst_name"],
        "from_account": o["from_acct"], "amount": f(o["amount"]), "carried_pr": round(f(o["carried_pr"]), 2),
        "carried_fifo": round(f(o["carried_fifo"]), 2), "carried_lifo": round(f(o["carried_lifo"]), 2),
        "ts": texts.ts(o["ts_epoch"]), "reference": o["txn_ref"], "checklist_missing": missing_fields,
        "draft": texts.forwarded_draft(case_info, req_row, o, o["inst_name"] or "receiving institution", missing_fields),
    } for o in oos]
    conservation = [{"convention": c["convention"], "loss": f(c["loss"]), "seeded": f(c["seeded"]),
                     "retained": round(f(c["retained"]), 2), "exited": round(f(c["exited"]), 2),
                     "dust": round(f(c["dust"]), 2), "absorbed": round(f(c["absorbed"]), 2),
                     "difference": round(f(c["difference"]), 6), "passed": bool(c["passed"])}
                    for c in q(f"SELECT * FROM {S}.CONSERVATION WHERE case_id = {{id}} ORDER BY convention DESC", p)]
    cfg = Config()
    assumptions = [
        f"Reference time: the time the request was received ({texts.ts_h(case['ref_epoch'])}). "
        f"Postings after it are not considered.",
        texts.CONVENTION_NOTE,
        f"Transfers carrying less than {texts.inr(cfg.dust)} of this case's disputed funds under a convention are "
        f"not traced further under that convention and are reported as dust.",
        "Failed and pending transfers are excluded; a completed reversal reduces the original transfer.",
        f"Duplicate postings (same parties, amount and reference within {cfg.dup_window_s // 60} minutes) are counted once.",
        f"A debit that overdraws an account and is cured by a credit within {cfg.skew_tol_s} seconds is treated as "
        f"clock skew and ordered after that credit.",
        "Funds that repay an overdraft are treated as absorbed by the bank and leave the trail.",
        "Funds moving to accounts outside the available records are 'Out of observable scope'; a forwarded request "
        "is drafted instead of guessing.",
        "Results describe synthetic data only and are decision support, not a decision.",
    ]
    return {
        "case": {"case_id": case["case_id"], "case_ref": case["case_ref"], "scenario": case["scenario"],
                 "victim_account": victim, "reported_loss": f(case["loss"]),
                 "fraud_ts": texts.ts(case["fraud_epoch"]), "ref_ts": texts.ts(case["ref_epoch"]),
                 "ref_rule": "REQUEST", "fraud_epoch": case["fraud_epoch"], "ref_epoch": case["ref_epoch"]},
        "request": request, "nodes": list(nodes.values()), "edges": edges, "edges_truncated": truncated,
        "edges_total": len(edges_all), "review": review_out, "dilution": dilution, "forwarded": forwarded,
        "conservation": conservation, "assumptions": assumptions,
    }


@app.get("/api/cases/{case_id}/explanation/{account_id}")
def explanation(case_id: int, account_id: str):
    require_results()
    case = _case_core(case_id)
    node = q1(f"SELECT * FROM {S}.SIZING WHERE case_id = {{c}} AND account_id = {{a}}", {"c": case_id, "a": account_id})
    if not node:
        raise HTTPException(404, "Account is not part of this case's trail")
    rv = q1(f"SELECT requested_scope, requested_amount FROM {S}.REVIEW WHERE case_id = {{c}} AND account_id = {{a}} "
            f"AND request_id = {{r}}", {"c": case_id, "a": account_id, "r": case["request_id"] or -1}) or {}
    node.update(rv)
    req = q1(f"SELECT * FROM {S}.REQUESTS WHERE request_id = {{r}}", {"r": case["request_id"] or -1})
    return {"account_id": account_id, "text": texts.holder_explanation(case, node, req)}


# ---------------------------------------------------------------- evidence packet
def _packet(case_id: int) -> dict:
    d = _case_detail(case_id)
    ev = q(f"""SELECT account_id, figure, figure_value, in_txns, out_txns, n_records, assumption
               FROM {S}.EVIDENCE_ITEMS WHERE case_id = {{c}} ORDER BY account_id, figure""", {"c": case_id})
    run = q1(f"SELECT run_id, snapshot_id, software_version, config_json, checksum, finished FROM {A}.RUNS "
             f"WHERE run_status = 'DONE' ORDER BY run_id DESC LIMIT 1") or {}
    evidence = [{"account_id": e["account_id"], "figure": e["figure"], "value": f(e["figure_value"]),
                 "source_txn_ids": [x for x in (e["in_txns"] or "").split(",") if x]
                 + [x for x in (e["out_txns"] or "").split(",") if x],
                 "assumption": e["assumption"]} for e in ev]
    missing = [n for n in d["nodes"] if n.get("status") == "UNDETERMINABLE"]
    body = {
        "title": "TraceHold evidence packet",
        "notice": "Decision support only. Synthetic data. Not a decision and not legal advice.",
        "header": d["case"], "request": d["request"],
        "trail_summary": {"accounts": len([n for n in d["nodes"] if n.get("kind") == "ACCOUNT"]),
                          "transfers": d["edges_total"],
                          "max_layer": max((n.get("layer") or 0) for n in d["nodes"]),
                          "out_of_scope_transfers": len(d["forwarded"])},
        "sizing": [n for n in d["nodes"] if n.get("kind") == "ACCOUNT"],
        "edges": d["edges"],
        "review": d["review"], "conservation": d["conservation"], "assumptions": d["assumptions"],
        "missing_data": [{"account_id": n["account_id"], "reasons": n.get("status_reasons")} for n in missing],
        "unresolved_questions": ([i["detail"] for i in d["request"]["completeness"]["items"] if i["kind"] != "OK"]
                                 if d["request"] else []),
        "forwarded_requests": d["forwarded"], "evidence": evidence,
    }
    canon = json.dumps(body, sort_keys=True, default=str).encode()
    body["reproducibility"] = {
        "run_id": run.get("run_id"), "snapshot_id": run.get("snapshot_id"),
        "software_version": run.get("software_version"),
        "config": json.loads(run["config_json"]) if run.get("config_json") else None,
        "run_finished": run.get("finished"), "run_checksum": run.get("checksum"),
        "packet_checksum": "sha256:" + hashlib.sha256(canon).hexdigest(),
    }
    return body


@app.get("/api/cases/{case_id}/packet")
def packet(case_id: int):
    require_results()
    return _packet(case_id)


@app.get("/api/cases/{case_id}/packet.html", response_class=HTMLResponse)
def packet_html(case_id: int):
    require_results()
    from app.packet_html import render_packet
    return render_packet(_packet(case_id))


# ---------------------------------------------------------------- live analysis (playground)
_playground_lock = threading.Lock()


@app.get("/api/playground/scenarios")
def playground_scenarios():
    from app.playground import SCENARIOS
    return {"scenarios": SCENARIOS}


@app.post("/api/playground/run")
def playground_run(body: dict):
    from app.playground import PlaygroundError, run
    with _playground_lock:
        try:
            return run(body)
        except PlaygroundError as e:
            raise HTTPException(400, str(e))


@app.get("/api/cases/{case_id}/explain/{account_id}")
def case_explain(case_id: int, account_id: str):
    """Step-by-step calculation for one account of a real case (computed in Exasol)."""
    require_results()
    from app.explain import explain_account, timeline_sql
    sql, params = timeline_sql(S, case_id, [account_id])
    rows = q(sql, params)
    sizing = q1(f"SELECT * FROM {S}.SIZING WHERE case_id = {{c}} AND account_id = {{a}}", {"c": case_id, "a": account_id})
    if not sizing:
        raise HTTPException(404, "This account is not part of the case's trail")
    victim = q1(f"SELECT victim_account FROM {S}.CASE_REF WHERE case_id = {{c}}", {"c": case_id})
    vid = victim["victim_account"] if victim else None

    def label(a):
        return "the victim" if a == vid else f"account {a}"
    return explain_account(rows, account_id, sizing, label=label, minute=lambda e: texts.ts(e).replace("T", " ")[:16])


# ---------------------------------------------------------------- Exasol at work (system statistics)
@app.get("/api/exasol")
def exasol_at_work():
    """What Exasol did, read from its own system tables (read-only)."""
    def tables(schema):
        return q(f"""SELECT t.TABLE_NAME AS name, t.TABLE_ROW_COUNT AS row_count, s.RAW_OBJECT_SIZE AS raw, s.MEM_OBJECT_SIZE AS mem
                     FROM EXA_DBA_TABLES t JOIN EXA_DBA_OBJECT_SIZES s
                       ON s.OBJECT_NAME = t.TABLE_NAME AND s.ROOT_NAME = t.TABLE_SCHEMA AND s.OBJECT_TYPE = 'TABLE'
                     WHERE t.TABLE_SCHEMA = {{s}} ORDER BY s.RAW_OBJECT_SIZE DESC""", {"s": schema})
    src = tables(db.SRC_SCHEMA)
    work = tables(db.SCHEMA)
    idx = q(f"""SELECT INDEX_SCHEMA AS sch, INDEX_TABLE AS tbl, INDEX_TYPE AS kind, MEM_OBJECT_SIZE AS mem, REMARKS AS remarks
                FROM EXA_DBA_INDICES WHERE INDEX_SCHEMA IN ({{a}}, {{b}}) ORDER BY MEM_OBJECT_SIZE DESC""",
            {"a": db.SRC_SCHEMA, "b": db.SCHEMA})
    size = q1("SELECT RAW_OBJECT_SIZE AS raw_gib, MEM_OBJECT_SIZE AS mem_gib, RECOMMENDED_DB_RAM_SIZE AS ram_gib, "
              "STORAGE_SIZE AS storage_gib, OBJECT_COUNT AS objects FROM EXA_STATISTICS.EXA_DB_SIZE_LAST_DAY "
              "ORDER BY MEASURE_TIME DESC LIMIT 1")
    run = q1(f"SELECT run_id, started, finished FROM {A}.RUNS WHERE run_status = 'DONE' ORDER BY run_id DESC LIMIT 1")
    stats = None
    if run:
        # the statement log is kept in UTC (SYSTIMESTAMP); the run log in the database's time zone
        window = {"r": run["run_id"]}
        agg = q(f"""WITH w AS (SELECT ADD_SECONDS(started, -SECONDS_BETWEEN(CURRENT_TIMESTAMP, SYSTIMESTAMP)) AS t0,
                                      ADD_SECONDS(finished, -SECONDS_BETWEEN(CURRENT_TIMESTAMP, SYSTIMESTAMP)) AS t1
                               FROM {A}.RUNS WHERE run_id = {{r}})
                    SELECT s.COMMAND_NAME AS command, COUNT(*) AS n, SUM(s.DURATION) AS seconds, SUM(s.ROW_COUNT) AS row_count,
                           MAX(s.TEMP_DB_RAM_PEAK) AS temp_peak_mib
                    FROM EXA_STATISTICS.EXA_SQL_LAST_DAY s, w
                    WHERE s.START_TIME BETWEEN w.t0 AND w.t1
                    GROUP BY s.COMMAND_NAME ORDER BY seconds DESC""", window)
        stats = {"run_id": run["run_id"], "by_command": agg,
                 "statements": int(sum(int(a["n"]) for a in agg)),
                 "seconds": round(sum(float(a["seconds"] or 0) for a in agg), 1),
                 "rows": int(sum(int(a["row_count"] or 0) for a in agg)),
                 "temp_peak_mib": max((float(a["temp_peak_mib"] or 0) for a in agg), default=0)}
    by_schema = {}
    for i in idx:
        by_schema[i["sch"]] = by_schema.get(i["sch"], 0) + 1
    return {"version": q1("SELECT PARAM_VALUE AS v FROM EXA_METADATA WHERE PARAM_NAME = 'databaseProductVersion'")["v"],
            "db_size": size, "source_tables": src, "work_tables": work[:12],
            "indexes": {"total": len(idx), "by_schema": by_schema, "created_by_tracehold": 0, "largest": idx[:12]},
            "last_run": stats}


# ---------------------------------------------------------------- live re-trace on the full ledger
@app.post("/api/cases/{case_id}/retrace")
def case_retrace(case_id: int):
    require_results()
    from app.retrace import retrace
    try:
        return retrace(case_id)
    except RuntimeError as e:
        raise HTTPException(409, str(e))


# ---------------------------------------------------------------- proportionate hold draft
def _hold_response(case_ref, request, items, basis, overrides, ref_time):
    basis = basis if basis in texts.BASIS_LABEL else "UPPER"
    plan = texts.hold_plan(items, basis, overrides)
    sized = [p for p in plan if p["proposed"] is not None]
    return {"basis": basis, "plan": plan,
            "totals": {"requested": round(sum(float(p.get("requested") or 0) for p in sized), 2),
                       "proposed": round(sum(p["proposed"] for p in sized), 2),
                       "released": round(sum(float(p.get("released") or 0) for p in sized), 2),
                       "not_sized": len(plan) - len(sized)},
            "text": texts.hold_draft(case_ref, request, plan, basis, ref_time)}


@app.post("/api/cases/{case_id}/hold-draft")
def case_hold_draft(case_id: int, body: dict):
    """Draft a proportionate hold instruction for the accounts named in the case's request."""
    require_results()
    case = _case_core(case_id)
    rows = q(f"""SELECT v.account_id, v.requested_amount, s.balance_ref, s.lower_amt, s.upper_amt, s.status
                 FROM {S}.REVIEW v JOIN {S}.SIZING s ON s.case_id = v.case_id AND s.account_id = v.account_id
                 WHERE v.case_id = {{c}} AND v.request_id = {{r}} ORDER BY v.layer, v.account_id""",
             {"c": case_id, "r": case["request_id"] or -1})
    items = [{"account_id": r["account_id"], "requested": f(r["requested_amount"]), "balance": f(r["balance_ref"]),
              "lower": f(r["lower_amt"]), "upper": f(r["upper_amt"]), "status": r["status"]} for r in rows]
    req = q1(f"SELECT issuing_officer, agency FROM {S}.REQUESTS WHERE request_id = {{r}}", {"r": case["request_id"] or -1})
    return _hold_response(case["case_ref"], req, items, body.get("basis"), body.get("overrides"),
                          texts.ts_h(case["ref_epoch"]))


@app.post("/api/hold-draft")
def hold_draft(body: dict):
    """Same draft for a live analysis (the figures come from the analysis result shown on the page)."""
    items = [{"account_id": str(i.get("account_id"))[:20], "requested": i.get("requested"), "balance": i.get("balance"),
              "lower": i.get("lower"), "upper": i.get("upper"), "status": i.get("status")} for i in (body.get("items") or [])][:200]
    return _hold_response(str(body.get("case_ref") or "LIVE-ANALYSIS")[:60], body.get("request") or {}, items,
                          body.get("basis"), body.get("overrides"), str(body.get("ref_time") or "the reference time")[:40])


# ---------------------------------------------------------------- AI at the edges (CF9, AF7, AF8)
def _ai_call(fn, *a, **kw):
    """Runs an AI feature and turns its failures into clear HTTP errors."""
    from app.ai.ask import AskRejected
    from app.ai.llm import AIUnavailable
    from app.ai.storage import ensure_ai_tables
    try:
        if ensure_ai_tables():
            _known_tables.clear()
        return fn(*a, **kw)
    except AIUnavailable as e:
        raise HTTPException(503, f"{e}. The rest of TraceHold works without AI; add GROQ_API_KEY to .env to use this.")
    except (AskRejected, ValueError) as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))


def _heal_ai_tables():
    try:
        from app.ai.storage import ensure_ai_tables
        if ensure_ai_tables():
            _known_tables.clear()
    except Exception:  # never block a page on this
        pass


@app.get("/api/ai/status")
def ai_status():
    _heal_ai_tables()
    from app.ai.llm import status
    from app.ai.mcp_client import mcp
    out = {"llm": status(), "mcp": mcp.status(), "reader_ready": bool(os.environ.get("TRACEHOLD_ASK_PASSWORD"))}
    try:
        out["counts"] = q1(f"""SELECT (SELECT COUNT(*) FROM {S}.REQUEST_DOCUMENTS) AS letters,
                                      (SELECT COUNT(DISTINCT extraction_id) FROM {A}.EXTRACTION_RESULTS) AS extractions,
                                      (SELECT COUNT(*) FROM {A}.EXTRACTION_CONFIRMATIONS) AS confirmations,
                                      (SELECT COUNT(*) FROM {A}.AI_LOG) AS ai_calls,
                                      (SELECT COUNT(*) FROM {A}.ASK_LOG) AS questions""")
    except Exception:
        out["counts"] = None
    return out


@app.get("/api/ai/letters")
def ai_scenario_letters(scenario: str = "worked"):
    """Synthetic letters for a live-analysis demo scenario (generated on the fly)."""
    import sys as _sys
    from app.playground import SCENARIOS
    gen = str(db.BACKEND / "generator")
    if gen not in _sys.path:
        _sys.path.insert(0, gen)
    from letters import scenario_letters
    sc = next((s for s in SCENARIOS if s["id"] == scenario), None)
    if not sc:
        raise HTTPException(404, "Unknown scenario")
    return {"letters": scenario_letters(sc)}


@app.get("/api/cases/{case_id}/letter")
def case_letter(case_id: int):
    _heal_ai_tables()
    row = q1(f"SELECT doc_id, request_id, split, body FROM {S}.REQUEST_DOCUMENTS WHERE case_id = {{c}} ORDER BY doc_id LIMIT 1",
             {"c": case_id}) if table_exists("REQUEST_DOCUMENTS") else None
    return {"letter": row}


@app.get("/api/ai/documents")
def ai_documents(limit: int = Query(20, le=100)):
    _heal_ai_tables()
    if not table_exists("REQUEST_DOCUMENTS"):
        return {"documents": []}
    rows = q(f"""SELECT d.doc_id, d.case_id, d.split, c.case_ref, SUBSTR(d.body, 1, 160) AS preview
                 FROM {S}.REQUEST_DOCUMENTS d JOIN {S}.CASES c ON c.case_id = d.case_id
                 ORDER BY d.doc_id LIMIT {{n!d}}""", {"n": limit})
    return {"documents": rows}


@app.post("/api/ai/extract")
def ai_extract(body: dict):
    from app.ai.extract import extract
    return _ai_call(extract, body.get("text", ""), body.get("context"), body.get("doc_id"))


@app.post("/api/ai/extract/{extraction_id}/confirm")
def ai_confirm(extraction_id: int, body: dict):
    from app.ai.extract import confirm
    return _ai_call(confirm, extraction_id, body.get("fields") or {}, body.get("confirmed_by") or "reviewer")


@app.get("/api/ai/ask/templates")
def ai_ask_templates():
    from app.ai.ask import TEMPLATES, VIEWS
    return {"templates": [{"id": t["id"], "question": t["question"]} for t in TEMPLATES],
            "views": [{"name": f"TH_RESULTS.{k}", "about": v} for k, v in VIEWS.items()]}


_ask_lock = threading.Lock()


@app.post("/api/ai/ask")
def ai_ask(body: dict):
    from app.ai.ask import ask
    with _ask_lock:
        return _ai_call(ask, body.get("question", ""))


@app.post("/api/cases/{case_id}/explanation/{account_id}/reword")
def ai_reword(case_id: int, account_id: str):
    from app.ai.reword import reword
    template = explanation(case_id, account_id)["text"]
    return _ai_call(reword, template, f"case {case_id} {account_id}")


@app.get("/api/ai/log")
def ai_log(limit: int = Query(30, le=200)):
    _heal_ai_tables()
    if not table_exists("AI_LOG", A):
        return {"calls": []}
    rows = q(f"""SELECT call_id, feature, model, prompt_version, input_ref, ms, status, created,
                        SUBSTR(output_text, 1, 300) AS output_preview
                 FROM {A}.AI_LOG ORDER BY created DESC LIMIT {{n!d}}""", {"n": limit})
    return {"calls": rows}


@app.get("/api/ai/evaluation")
def ai_evaluation():
    p = db.RESULTS / "ai_evaluation.json"
    if not p.exists():
        return {"available": False, "note": "Run: python -m app.ai_eval (from the backend folder)"}
    return {"available": True, **json.loads(p.read_text(encoding="utf-8"))}


# ---------------------------------------------------------------- what a result is based on
@app.get("/api/basis/sql/{name}")
def basis_sql(name: str, where: str = "cases"):
    """The real text of one SQL script, as rendered for the stored cases or the live analysis."""
    from app import basis
    from app.playground import SCHEMA as PG_SCHEMA
    try:
        text = basis.script_text(name, PG_SCHEMA if where == "playground" else S)
    except KeyError:
        raise HTTPException(404, "Unknown script")
    return {"name": name, "purpose": basis.SCRIPTS[name], "sql": text}


@app.get("/api/cases/{case_id}/basis")
def case_basis(case_id: int):
    require_results()
    from app import basis
    run = q1(f"SELECT run_id, started, duration_s, checksum, config_json FROM {A}.RUNS "
             f"WHERE run_status = 'DONE' ORDER BY run_id DESC LIMIT 1")
    steps = q(f"SELECT step_name AS step, ms, row_count AS \"rows\" FROM {A}.RUN_STEPS WHERE run_id = {{r}} ORDER BY step_no",
              {"r": run["run_id"]}) if run else []
    facts = q1(f"""SELECT (SELECT COUNT(*) FROM {S}.TRAIL_EDGES WHERE case_id = {{c}}) AS transfers,
                          (SELECT COUNT(*) FROM {S}.SIZING WHERE case_id = {{c}}) AS accounts,
                          (SELECT MAX(layer) FROM {S}.SIZING WHERE case_id = {{c}}) AS layers,
                          (SELECT COUNT(*) FROM {S}.EV e JOIN {S}.SIZING z ON z.account_id = e.account_id AND z.case_id = {{c}}
                             JOIN {S}.CASE_REF r ON r.case_id = z.case_id WHERE e.ord_epoch <= r.ref_epoch) AS postings""",
               {"c": case_id})
    total = cached("txn_total", lambda: q1(f"SELECT COUNT(*) AS n FROM {S}.TRANSACTIONS")["n"])
    grouped = basis.group_steps([{k.lower(): v for k, v in s.items()} for s in steps])
    cfg = json.loads(run["config_json"]) if run and run.get("config_json") else None
    return {
        "run": {"run_id": run["run_id"], "started": run["started"], "duration_s": run["duration_s"],
                "checksum": run["checksum"]} if run else None,
        "facts": {**{k: int(v or 0) for k, v in facts.items()}, "transactions_total": int(total)},
        "steps": grouped,
        "rules": basis.rules(cfg),
        "source_check": ({"run_id": run["run_id"], "tables": len(fps), "rows": sum(f["rows_after"] or 0 for f in fps),
                          "unchanged": all(f["unchanged"] for f in fps)} if run and (fps := _fingerprints(run["run_id"])) else None),
        "page_query": (f"SELECT account_id, layer, balance_ref, retained_pr, retained_fifo, lower_amt, upper_amt, status\n"
                       f"FROM {S}.SIZING\nWHERE case_id = {case_id}\nORDER BY layer, account_id;"),
    }


# ---------------------------------------------------------------- lien review & oversight
FLAG_COL = {"OVER_HOLD": "f_over_hold", "CLOSED_STILL_HELD": "f_closed_still_held", "PAST_90": "f_past_90",
            "PAST_REVIEW": "f_past_review", "ESCALATE": "f_escalate", "CANNOT_SIZE": "f_cannot_size"}


@app.get("/api/lien-review")
def lien_review(flag: str = "ALL", page: int = 1, page_size: int = Query(25, le=200)):
    require_results()
    where = "active = 1"
    if flag in FLAG_COL:
        where += f" AND {FLAG_COL[flag]} = 1"
    total = q1(f"SELECT COUNT(*) AS n FROM {S}.LIEN_REVIEW WHERE {where}")["n"]
    summ = q1(f"""SELECT SUM(active) AS active, SUM(f_over_hold) AS over_hold, SUM(f_closed_still_held) AS closed_still_held,
                         SUM(f_past_90) AS past_90, SUM(f_past_review) AS past_review, SUM(f_escalate) AS escalate,
                         SUM(f_cannot_size) AS cannot_size FROM {S}.LIEN_REVIEW WHERE active = 1""")
    rows = q(f"""SELECT l.*, c.case_ref FROM {S}.LIEN_REVIEW l JOIN {S}.CASES c ON c.case_id = l.case_id
                 WHERE {where} ORDER BY l.priority DESC, l.restraint_id
                 LIMIT {{lim!d}} OFFSET {{off!d}}""", {"lim": page_size, "off": (max(page, 1) - 1) * page_size})
    items = []
    for r in rows:
        flags = [k for k, col in FLAG_COL.items() if r[col]]
        items.append({
            "restraint_id": r["restraint_id"], "account_id": r["account_id"], "case_id": r["case_id"],
            "case_ref": r["case_ref"], "restraint_type": r["restraint_type"], "held_amount": f(r["held_amount"]),
            "lower": f(r["lower_amt"]), "upper": f(r["upper_amt"]), "status": r["status"],
            "over_hold_ratio": f(r["over_hold_ratio"]), "days_held": r["days_held"],
            "days_since_update": r["days_since_update"], "closure_status": r["closure_status"], "band": r["band"],
            "days_to_90": r["days_to_90"], "escalation_date": r["escalation_date"], "start_date": r["start_date"],
            "issuing_authority": r["issuing_authority"], "flags": flags, "priority": f(r["priority"]),
        })
    return {"as_of": Config().as_of, "total": total, "summary": summ, "items": items,
            "note": "Ranked for human review. TraceHold performs no release."}


@app.get("/api/oversight")
def oversight():
    require_results()

    def _o():
        hist = q(f"""SELECT bucket, COUNT(*) AS n FROM (
                        SELECT CASE WHEN f_cannot_size = 1 THEN 'cannot size'
                                    WHEN over_hold_ratio IS NULL AND held_amount > 1 THEN 'no support'
                                    WHEN over_hold_ratio IS NULL OR over_hold_ratio <= 1.0001 THEN '<=1x'
                                    WHEN over_hold_ratio <= 2 THEN '1-2x'
                                    WHEN over_hold_ratio <= 5 THEN '2-5x'
                                    WHEN over_hold_ratio <= 10 THEN '5-10x'
                                    WHEN over_hold_ratio <= 100 THEN '10-100x' ELSE '>100x' END AS bucket
                        FROM {S}.LIEN_REVIEW WHERE active = 1) b GROUP BY bucket""")
        order = ["<=1x", "1-2x", "2-5x", "5-10x", "10-100x", ">100x", "no support", "cannot size"]
        hist.sort(key=lambda r: order.index(r["bucket"]) if r["bucket"] in order else 99)
        age = q(f"""SELECT bucket, COUNT(*) AS n FROM (
                      SELECT CASE WHEN days_held <= 30 THEN '0-30d' WHEN days_held <= 60 THEN '31-60d'
                                  WHEN days_held <= 90 THEN '61-90d' WHEN days_held <= 120 THEN '91-120d'
                                  ELSE '>120d' END AS bucket
                      FROM {S}.LIEN_REVIEW WHERE active = 1) b GROUP BY bucket ORDER BY bucket""")
        age.sort(key=lambda r: ["0-30d", "31-60d", "61-90d", "91-120d", ">120d"].index(r["bucket"]))
        miss = q1(f"""SELECT AVG(CASE WHEN rs.n_missing > 0 THEN 1.0 ELSE 0.0 END) AS v
                      FROM {S}.LIEN_REVIEW l JOIN {S}.REQ_STATUS rs ON rs.request_id = l.request_id WHERE l.active = 1""")
        noupd = q1(f"""SELECT AVG(CASE WHEN last_update_date = start_date THEN 1.0 ELSE 0.0 END) AS v
                       FROM {S}.LIEN_REVIEW WHERE active = 1""")
        by_status = q(f"""SELECT closure_status, COUNT(*) AS n, AVG(over_hold_ratio) AS avg_over_hold,
                                 SUM(held_amount) AS held FROM {S}.LIEN_REVIEW WHERE active = 1
                          GROUP BY closure_status ORDER BY n DESC""")
        by_agency = q(f"""SELECT issuing_authority AS agency, COUNT(*) AS n, SUM(held_amount) AS held,
                                 SUM(GREATEST(held_amount - COALESCE(upper_amt, 0), 0)) AS over_held
                          FROM {S}.LIEN_REVIEW WHERE active = 1 AND f_cannot_size = 0
                          GROUP BY issuing_authority ORDER BY over_held DESC LIMIT 10""")
        tot = q1(f"""SELECT SUM(held_amount) AS held, SUM(CASE WHEN f_cannot_size = 0 THEN LEAST(held_amount, COALESCE(upper_amt, 0)) END) AS supported
                     FROM {S}.LIEN_REVIEW WHERE active = 1""")
        return {"over_hold_hist": hist, "age_hist": age, "missing_fields_share": f(miss["v"]),
                "no_update_share": f(noupd["v"]), "by_status": by_status, "by_agency": by_agency,
                "held_total": f(tot["held"]), "held_supported": f(tot["supported"])}
    return cached("oversight", _o)


# ---------------------------------------------------------------- insights
@app.get("/api/policy-sim")
def policy_sim():
    saved = _saved_evaluation()
    if saved and saved.get("policy_simulation"):
        return saved["policy_simulation"]
    require_results()
    from app.evaluation import policy_simulation
    return cached("policy", lambda: policy_simulation(q))


def _saved_evaluation():
    """Evaluation written by `python -m app.evaluation` after each analysis run:
    serving the saved file keeps heavy ground-truth queries off the request path."""
    p = db.RESULTS / "evaluation.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


@app.get("/api/speed")
def speed():
    require_results()

    def _s():
        rows = q(f"""SELECT COALESCE(g.scenario, 'UNLABELLED') AS scenario, s.minutes,
                            AVG(s.inside_pr) AS pr, AVG(s.inside_fifo) AS fifo, COUNT(*) AS n
                     FROM {S}.SPEED s LEFT JOIN {GT}.CASE_SCENARIO g ON g.case_id = s.case_id
                     WHERE COALESCE(g.scenario, '') <> 'WORKED_EXAMPLE'
                     GROUP BY COALESCE(g.scenario, 'UNLABELLED'), s.minutes ORDER BY 1, 2""")
        allr = q(f"""SELECT s.minutes, AVG(s.inside_pr) AS pr, AVG(s.inside_fifo) AS fifo, COUNT(*) AS n
                     FROM {S}.SPEED s GROUP BY s.minutes ORDER BY s.minutes""")
        curves = {"ALL": [{"minutes": r["minutes"], "share_inside": f(r["fifo"]), "share_inside_pr": f(r["pr"]),
                           "n_cases": r["n"]} for r in allr]}
        for r in rows:
            curves.setdefault(r["scenario"], []).append(
                {"minutes": r["minutes"], "share_inside": f(r["fifo"]), "share_inside_pr": f(r["pr"]), "n_cases": r["n"]})
        return {"curves": [{"scenario": k, "points": v} for k, v in curves.items()],
                "note": "Share of disputed funds still inside observable accounts (FIFO; pro-rata also given), "
                        "averaged over cases whose reference time is at least that many minutes after the fraud. "
                        "Synthetic data only."}
    return cached("speed", _s)


@app.get("/api/sensitivity")
def sensitivity():
    require_results()

    def _s():
        hist = q(f"""SELECT bucket, COUNT(*) AS n FROM (
                        SELECT CASE WHEN sensitivity < 0.1 THEN '0-10%' WHEN sensitivity < 0.25 THEN '10-25%'
                                    WHEN sensitivity < 0.5 THEN '25-50%' WHEN sensitivity < 0.75 THEN '50-75%'
                                    WHEN sensitivity < 0.999 THEN '75-99%' ELSE '100%' END AS bucket
                        FROM {S}.SIZING WHERE received = 1 AND sensitivity IS NOT NULL) b GROUP BY bucket""")
        order = ["0-10%", "10-25%", "25-50%", "50-75%", "75-99%", "100%"]
        hist.sort(key=lambda r: order.index(r["bucket"]))
        by_layer = q(f"""SELECT layer, AVG(sensitivity) AS avg_sensitivity, COUNT(*) AS n FROM {S}.SIZING
                         WHERE received = 1 AND sensitivity IS NOT NULL AND layer <= 8 GROUP BY layer ORDER BY layer""")
        top = q(f"""SELECT s.case_id, c.case_ref, s.account_id, s.layer, s.lower_ext, s.upper_ext, s.lower_amt,
                           s.upper_amt, s.sensitivity, s.balance_ref
                    FROM {S}.SIZING s JOIN {S}.CASES c ON c.case_id = s.case_id
                    WHERE s.received = 1 AND s.sensitivity IS NOT NULL
                    ORDER BY s.sensitivity DESC, s.upper_ext DESC LIMIT 25""")
        return {"hist": hist, "by_layer": by_layer,
                "top": [{**t, **{k: f(t[k]) for k in ("lower_ext", "upper_ext", "lower_amt", "upper_amt",
                                                      "sensitivity", "balance_ref")}} for t in top]}
    return cached("sensitivity", _s)


# ---------------------------------------------------------------- runs (AF6)
_run_state = {"running": None}
_run_lock = threading.Lock()


@app.get("/api/runs")
def runs():
    rows = q(f"SELECT * FROM {A}.RUNS ORDER BY run_id DESC LIMIT 50")
    return {"runs": [_run_out(r) for r in rows], "running": _run_state["running"]}


def _run_out(r):
    return {"run_id": r["run_id"], "started": r["started"], "finished": r["finished"], "status": r["run_status"],
            "snapshot_id": r["snapshot_id"], "software_version": r["software_version"], "checksum": r["checksum"],
            "duration_s": f(r["duration_s"]), "error": r.get("error_text"),
            "config": json.loads(r["config_json"]) if r.get("config_json") else None}


@app.post("/api/runs")
def start_run(body: dict | None = None):
    from app.engine import start_run as _start
    mode = "lua" if (body or {}).get("mode") == "lua" else "python"
    cfg = Config(orchestration=mode)
    with _run_lock:
        if _run_state["running"]:
            raise HTTPException(409, f"Run {_run_state['running']} is already in progress")
        conn = db.connect()
        rid = _start(conn, S, cfg)
        conn.close()
        _run_state["running"] = rid

    def work():
        try:
            run_full(S, cfg, log=lambda m: None, run_id=rid, mode=mode)
        except Exception:
            pass
        finally:
            _run_state["running"] = None
            _cache.clear()
            _warm()

    threading.Thread(target=work, daemon=True).start()
    return {"run_id": rid}


@app.get("/api/runs/{run_id}")
def run_detail(run_id: int):
    r = q1(f"SELECT * FROM {A}.RUNS WHERE run_id = {{r}}", {"r": run_id})
    if not r:
        raise HTTPException(404, "No such run")
    steps = [{"step_no": x["step_no"], "step": x["step"], "ms": x["ms"], "rows": x["row_count"]}
             for x in q(f"SELECT step_no, step_name AS step, ms, row_count FROM {A}.RUN_STEPS "
                        f"WHERE run_id = {{r}} ORDER BY step_no", {"r": run_id})]
    prev = q1(f"SELECT run_id, checksum, snapshot_id FROM {A}.RUNS WHERE run_id < {{r}} AND run_status = 'DONE' "
              f"ORDER BY run_id DESC LIMIT 1", {"r": run_id})
    out = _run_out(r)
    out["steps"] = steps
    if prev and r["checksum"]:
        out["compared_with"] = {"run_id": prev["run_id"], "same_snapshot": prev["snapshot_id"] == r["snapshot_id"],
                                "identical_results": prev["checksum"] == r["checksum"]}
    out["fingerprints"] = _fingerprints(run_id)
    out["source_unchanged"] = (all(f["unchanged"] for f in out["fingerprints"]) if out["fingerprints"] else None)
    out["history_rows"] = q1(f"""SELECT (SELECT COUNT(*) FROM {A}.SIZING_HISTORY WHERE run_id = {{r}}) AS sizing,
                                        (SELECT COUNT(*) FROM {A}.REVIEW_HISTORY WHERE run_id = {{r}}) AS review,
                                        (SELECT COUNT(*) FROM {A}.CASE_SUMMARY_HISTORY WHERE run_id = {{r}}) AS cases,
                                        (SELECT COUNT(*) FROM {A}.TRAIL_HISTORY WHERE run_id = {{r}}) AS trail""",
                             {"r": run_id}) if table_exists("SIZING_HISTORY", A) else None
    return out


def _fingerprints(run_id: int) -> list[dict]:
    if not table_exists("SOURCE_FINGERPRINTS", A):
        return []
    rows = q(f"SELECT phase, table_name, row_count, fingerprint FROM {A}.SOURCE_FINGERPRINTS WHERE run_id = {{r}}",
             {"r": run_id})
    by = {}
    for x in rows:
        by.setdefault(x["table_name"], {})[x["phase"]] = x
    out = []
    for t, ph in sorted(by.items()):
        b, a = ph.get("BEFORE"), ph.get("AFTER")
        out.append({"table": t, "rows_before": b and int(b["row_count"]), "rows_after": a and int(a["row_count"]),
                    "fingerprint_before": b and str(b["fingerprint"]), "fingerprint_after": a and str(a["fingerprint"]),
                    "unchanged": bool(b and a and b["row_count"] == a["row_count"] and b["fingerprint"] == a["fingerprint"])})
    return out


# ---------------------------------------------------------------- protection and history
@app.get("/api/protection")
def protection():
    """Tries every forbidden statement as the engine user; Exasol must refuse each one."""
    if not db.engine_ready():
        return {"ready": False, "note": "Run python -m app.secure (from the backend folder) to set up the protected layout."}
    from app.secure import prove_protection
    checks = prove_protection()
    return {
        "ready": True, "engine_user": db.ENGINE_USER, "all_ok": all(c["ok"] for c in checks), "checks": checks,
        "schemas": [
            {"schema": db.SRC_SCHEMA, "holds": "Source data: transactions, accounts, cases, requests, holds, letters", "engine": "read only"},
            {"schema": db.SCHEMA, "holds": "Views of the source data and the calculation tables, rebuilt on every run", "engine": "owner (rebuilds)"},
            {"schema": "TH_PLAYGROUND", "holds": "Scratch area for live analyses", "engine": "owner (rebuilds)"},
            {"schema": db.AUDIT_SCHEMA, "holds": "Run log, results history, source fingerprints, live analyses, AI log", "engine": "add rows only"},
            {"schema": db.GT_SCHEMA, "holds": "The generator's answer key", "engine": "no access (scenario labels only)"},
        ],
    }


@app.get("/api/history/compare")
def history_compare(a: int, b: int):
    """Compares the stored results of two runs, account by account."""
    p = {"a": a, "b": b}
    r = q1(f"""SELECT
        (SELECT COUNT(*) FROM {A}.SIZING_HISTORY WHERE run_id = {{a}}) AS rows_a,
        (SELECT COUNT(*) FROM {A}.SIZING_HISTORY WHERE run_id = {{b}}) AS rows_b,
        (SELECT COUNT(*) FROM {A}.SIZING_HISTORY x JOIN {A}.SIZING_HISTORY y
            ON y.case_id = x.case_id AND y.account_id = x.account_id AND y.run_id = {{b}}
          WHERE x.run_id = {{a}} AND (ABS(COALESCE(x.retained_pr, 0) - COALESCE(y.retained_pr, 0)) > 0.005
                OR ABS(COALESCE(x.retained_fifo, 0) - COALESCE(y.retained_fifo, 0)) > 0.005
                OR COALESCE(x.status, '') <> COALESCE(y.status, ''))) AS changed,
        (SELECT COUNT(*) FROM {A}.REVIEW_HISTORY x JOIN {A}.REVIEW_HISTORY y
            ON y.request_id = x.request_id AND y.account_id = x.account_id AND y.run_id = {{b}}
          WHERE x.run_id = {{a}} AND COALESCE(x.classification, '') <> COALESCE(y.classification, '')) AS reclassified""", p)
    out = {k: int(v or 0) for k, v in r.items()}
    out["identical"] = out["rows_a"] == out["rows_b"] and out["changed"] == 0 and out["reclassified"] == 0 and out["rows_a"] > 0
    return {"a": a, "b": b, **out}


@app.get("/api/live-analyses")
def live_analyses(limit: int = Query(20, le=100)):
    if not table_exists("LIVE_ANALYSES", A):
        return {"analyses": []}
    rows = q(f"SELECT analysis_id, created, case_title, summary_json, engine_ms FROM {A}.LIVE_ANALYSES "
             f"ORDER BY created DESC LIMIT {{n!d}}", {"n": limit})
    for r in rows:
        try:
            r["summary"] = json.loads(r.pop("summary_json") or "{}")
        except ValueError:
            r["summary"] = {}
    return {"analyses": rows}


# ---------------------------------------------------------------- evaluation & benchmark
@app.get("/api/evaluation")
def evaluation():
    saved = _saved_evaluation()
    if saved:
        return {k: v for k, v in saved.items() if k != "policy_simulation"}
    require_results()
    from app.evaluation import evaluate
    return cached("evaluation", lambda: evaluate(q))


@app.get("/api/benchmark")
def benchmark():
    p = db.RESULTS / "benchmark.json"
    if not p.exists():
        return {"hardware": None, "results": [], "note": "Benchmark not run yet: python -m benchmark.run (from the backend folder)"}
    out = json.loads(p.read_text())
    out["full_run"] = _full_run_timing()
    return out


def _full_run_timing():
    """The latest full analysis on the loaded dataset: the largest measured point."""
    try:
        run = q1(f"SELECT run_id, duration_s FROM {A}.RUNS WHERE run_status = 'DONE' ORDER BY run_id DESC LIMIT 1")
        if not run:
            return None
        steps = q(f"SELECT step_name, ms FROM {A}.RUN_STEPS WHERE run_id = {{r}} ORDER BY step_no", {"r": run["run_id"]})
        core, in_core = 0.0, True
        for st in steps:  # the core workload ends with sizing (same as W2 in the benchmark)
            if in_core:
                core += float(st["ms"])
            if st["step_name"].startswith("CF3 sizing"):
                in_core = False
        n = cached("txn_total", lambda: q1(f"SELECT COUNT(*) AS n FROM {S}.TRANSACTIONS")["n"])
        return {"run_id": run["run_id"], "transactions": int(n), "duration_s": float(run["duration_s"] or 0),
                "core_s": round(core / 1000, 3)}
    except Exception:
        return None


# ---------------------------------------------------------------- warm-up
def _warm():
    """Touch the main views once so the first user does not wait while Exasol
    builds indexes on freshly created result tables."""
    try:
        if not table_exists("CASE_SUMMARY"):
            return
        overview()
        cases(page=1, page_size=25, sort="fraud_ts")
        _case_detail(1)
        lien_review(flag="ALL", page=1, page_size=20)
    except Exception as e:  # warm-up is best effort
        import logging
        logging.getLogger("uvicorn.error").warning("warm-up skipped: %r", e)


@app.on_event("startup")
def _startup():
    threading.Thread(target=_warm, daemon=True).start()


# ---------------------------------------------------------------- frontend
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            # An unknown API address is an error, not the website.
            raise HTTPException(404, f"No such API endpoint: /{path}. If the website is newer than the backend, restart the backend.")
        target = DIST / path
        if path and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
