"""Live analysis: a small case typed in by the user (or a demo scenario) is
loaded into its own Exasol schema and analysed by exactly the same SQL engine
as the full dataset: request check, trail, sizing, review and conservation."""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import pyexasol

from app import db, texts
from app.engine import Config, Engine
from app.basis import group_steps, rules
from app.explain import explain_account, timeline_sql

SCHEMA = "TH_PLAYGROUND"
BASE = datetime(2026, 8, 14, 14, 0)
BASE_EPOCH = int((BASE - datetime(2026, 1, 1)).total_seconds())
BANK, OTHER_BANK = "BK01", "BK09"
RESERVED = {"VICTIM", "CASH", "OTHER_BANK"}

CHECKLIST = [
    ("OFFICER", "issuing_officer", "Issuing officer's name", True, 1),
    ("DESIGNATION", "designation", "Officer's designation", True, 2),
    ("CONTACT", "agency_contact", "Agency contact details", True, 3),
    ("CASE_REF", "case_reference", "FIR / crime / NCRP / CFCFRMS reference", True, 4),
    ("LEGAL_PROVISION", "legal_provision", "Legal provision invoked", True, 5),
    ("TXN", "quoted_txn_id", "Disputed transaction details", True, 6),
    ("AMOUNT", "stated_amount", "Disputed amount", True, 7),
    ("ACTION", "action_type", "Type of action sought", True, 8),
]


def _req(**kw):
    base = {"officer": "R. Sharma", "designation": "Inspector of Police", "agency": "Cyber Crime Police Station, Jaipur",
            "contact": "cyber.jaipur@police.example.in", "reference": "NCRP-31234567890",
            "legal_provision": "Section 106 BNSS 2023; Section 318(4) BNS", "action_type": "TOTAL_FREEZE",
            "stated_amount": None, "targets": []}
    base.update(kw)
    return base


SCENARIOS = [
    {
        "id": "worked", "title": "The worked example",
        "summary": "₹1,00,000 stolen. A forwards ₹90,000 to B, which already holds ₹5,00,000. B pays ₹4,00,000 to C. "
                   "The police ask to freeze all three accounts.",
        "teaches": "Why freezing whole balances locks far more than the stolen money, and why the methods disagree.",
        "accounts": [{"name": "A", "opening": 20000}, {"name": "B", "opening": 500000}, {"name": "C", "opening": 50000}],
        "transfers": [{"from": "VICTIM", "to": "A", "amount": 100000, "minute": 2},
                      {"from": "A", "to": "B", "amount": 90000, "minute": 10},
                      {"from": "B", "to": "C", "amount": 400000, "minute": 60}],
        "request": _req(stated_amount=100000, targets=[{"account": "A", "scope": "WHOLE_BALANCE"},
                                                       {"account": "B", "scope": "WHOLE_BALANCE"},
                                                       {"account": "C", "scope": "WHOLE_BALANCE"}]),
    },
    {
        "id": "split", "title": "Split, merge and cash-out",
        "summary": "₹2,00,000 is split across three mule accounts within minutes, two of them merge into E, and E "
                   "withdraws cash. The request asks for a ₹2,00,000 lien on every account and forgets the legal provision.",
        "teaches": "Tracing through splits and merges, money lost to cash, and an incomplete, over-broad request.",
        "accounts": [{"name": "A", "opening": 1500}, {"name": "B", "opening": 2000}, {"name": "C", "opening": 500},
                     {"name": "D", "opening": 3000}, {"name": "E", "opening": 1000}],
        "transfers": [{"from": "VICTIM", "to": "A", "amount": 200000, "minute": 0},
                      {"from": "A", "to": "B", "amount": 80000, "minute": 6},
                      {"from": "A", "to": "C", "amount": 70000, "minute": 7},
                      {"from": "A", "to": "D", "amount": 45000, "minute": 8},
                      {"from": "B", "to": "E", "amount": 78000, "minute": 20},
                      {"from": "C", "to": "E", "amount": 69000, "minute": 22},
                      {"from": "E", "to": "CASH", "amount": 100000, "minute": 35}],
        "request": _req(legal_provision="", action_type="LIEN_AMOUNT", stated_amount=200000,
                        targets=[{"account": a, "scope": "AMOUNT", "amount": 200000} for a in "ABCDE"]),
    },
    {
        "id": "shop", "title": "An innocent shopkeeper",
        "summary": "A mule pays a shopkeeper ₹12,000 for goods, then forwards the rest and withdraws cash. The shop's "
                   "₹3,20,000 balance is frozen along with the mule accounts.",
        "teaches": "How a one-off recipient's own money is separated from the disputed money.",
        "accounts": [{"name": "A", "opening": 2000}, {"name": "B", "opening": 1000}, {"name": "SHOP", "opening": 320000}],
        "transfers": [{"from": "VICTIM", "to": "A", "amount": 150000, "minute": 0},
                      {"from": "A", "to": "SHOP", "amount": 12000, "minute": 5},
                      {"from": "A", "to": "B", "amount": 130000, "minute": 9},
                      {"from": "B", "to": "CASH", "amount": 100000, "minute": 15}],
        "request": _req(stated_amount=150000, targets=[{"account": "A", "scope": "WHOLE_BALANCE"},
                                                       {"account": "B", "scope": "WHOLE_BALANCE"},
                                                       {"account": "SHOP", "scope": "WHOLE_BALANCE"}]),
    },
    {
        "id": "otherbank", "title": "Money moves to another bank",
        "summary": "₹80,000 passes through two accounts and ₹60,000 leaves for a bank whose records we do not have. "
                   "The request quotes the amount in paise by mistake.",
        "teaches": "What happens when money leaves the records (a forwarded request is drafted) and how a unit slip is caught.",
        "accounts": [{"name": "A", "opening": 0}, {"name": "B", "opening": 500}],
        "transfers": [{"from": "VICTIM", "to": "A", "amount": 80000, "minute": 0},
                      {"from": "A", "to": "B", "amount": 78000, "minute": 4},
                      {"from": "B", "to": "OTHER_BANK", "amount": 60000, "minute": 12}],
        "request": _req(action_type="LIEN_AMOUNT", stated_amount=8000000,
                        targets=[{"account": "A", "scope": "AMOUNT", "amount": 80000},
                                 {"account": "B", "scope": "AMOUNT", "amount": 78000}]),
    },
    {
        "id": "business", "title": "Mixed into a busy business",
        "summary": "₹55,000 of stolen money lands in a business account holding ₹8,00,000, which then pays two suppliers.",
        "teaches": "Dilution: once money is mixed with a large balance, the traceable share becomes small and uncertain.",
        "accounts": [{"name": "A", "opening": 1000}, {"name": "BIZ", "opening": 800000},
                     {"name": "P", "opening": 100000}, {"name": "Q", "opening": 50000}],
        "transfers": [{"from": "VICTIM", "to": "A", "amount": 60000, "minute": 0},
                      {"from": "A", "to": "BIZ", "amount": 55000, "minute": 3},
                      {"from": "BIZ", "to": "P", "amount": 300000, "minute": 30},
                      {"from": "BIZ", "to": "Q", "amount": 200000, "minute": 50}],
        "request": _req(stated_amount=60000, targets=[{"account": "A", "scope": "WHOLE_BALANCE"},
                                                      {"account": "BIZ", "scope": "WHOLE_BALANCE"},
                                                      {"account": "P", "scope": "WHOLE_BALANCE"}]),
    },
]


class PlaygroundError(ValueError):
    pass


def _validate(body: dict):
    accounts = body.get("accounts") or []
    transfers = body.get("transfers") or []
    if not (1 <= len(accounts) <= 12):
        raise PlaygroundError("Add between 1 and 12 accounts.")
    if not (1 <= len(transfers) <= 40):
        raise PlaygroundError("Add between 1 and 40 transfers.")
    names = []
    for a in accounts:
        n = str(a.get("name", "")).strip().upper()
        if not n or len(n) > 12 or not n.replace("_", "").isalnum() or n in RESERVED:
            raise PlaygroundError(f"Account name '{a.get('name')}' is not allowed (letters and digits, up to 12).")
        if n in names:
            raise PlaygroundError(f"Account name {n} is used twice.")
        try:
            if float(a.get("opening") or 0) < 0:
                raise PlaygroundError(f"The starting balance of {n} cannot be negative.")
        except (TypeError, ValueError):
            raise PlaygroundError(f"The starting balance of {n} is not a number.")
        names.append(n)
    ok_from, ok_to = set(names) | {"VICTIM"}, set(names) | {"CASH", "OTHER_BANK"}
    if not any(str(t.get("from", "")).upper() == "VICTIM" for t in transfers):
        raise PlaygroundError("At least one transfer must come from the victim (that is the reported fraud).")
    for t in transfers:
        fr, to = str(t.get("from", "")).upper(), str(t.get("to", "")).upper()
        if fr not in ok_from or to not in ok_to or fr == to:
            raise PlaygroundError(f"Transfer {fr or '?'} → {to or '?'} is not valid.")
        try:
            if float(t.get("amount") or 0) <= 0:
                raise PlaygroundError(f"Transfer {fr} → {to} needs a positive amount.")
            if not (0 <= int(t.get("minute", 0)) <= 10080):
                raise PlaygroundError("Times must be between 0 and 10,080 minutes.")
        except (TypeError, ValueError):
            raise PlaygroundError(f"Transfer {fr} → {to} has an invalid amount or time.")
    return names


def run(body: dict) -> dict:
    names = _validate(body)
    req = {**_req(), **(body.get("request") or {})}
    openings = {a["name"].strip().upper(): round(float(a.get("opening") or 0), 2) for a in body["accounts"]}
    transfers = sorted(enumerate(body["transfers"]), key=lambda x: (int(x[1]["minute"]), x[0]))
    t0 = time.perf_counter()
    conn = db.connect(autocommit=False, fetch_mapper=pyexasol.exasol_mapper)
    S = SCHEMA
    try:
        for stmt in db.load_sql("00_schema.sql", S=S):
            if stmt.lstrip().upper().startswith("CREATE SCHEMA") and db.engine_ready():
                continue  # the scratch schema is created (and owned by the analysis user) by app.secure
            conn.execute(stmt)
        conn.commit()
        victim_out = sum(float(t["amount"]) for _, t in transfers if t["from"].upper() == "VICTIM")
        last_minute = max(int(t["minute"]) for _, t in transfers)
        ref_minute = int(body.get("ref_minute") or last_minute)
        ref_epoch = BASE_EPOCH + ref_minute * 60
        conn.import_from_iterable([(BANK, "Your bank", "BANK", True), (OTHER_BANK, "Another bank (no records)", "BANK", False)],
                                  (S, "INSTITUTIONS"))
        accs = [("VICTIM", BANK, "Victim", "INDIVIDUAL", None, victim_out + 1000, None, BASE_EPOCH - 86400, None, None)]
        accs += [(n, BANK, f"Account {n}", "INDIVIDUAL", None, openings[n], None, BASE_EPOCH - 86400, None, None) for n in names]
        accs += [("OTHER_BANK", OTHER_BANK, "Account at another bank", "INDIVIDUAL", None, None, None, None, None, None)]
        conn.import_from_iterable(accs, (S, "ACCOUNTS"))
        txns, disputed, first_in = [], [], {}
        for seq, (_, t) in enumerate(transfers, 1):
            fr, to = t["from"].upper(), t["to"].upper()
            tid = f"T{seq:03d}"
            txns.append((tid, seq, None, BASE_EPOCH + int(t["minute"]) * 60, fr, None if to == "CASH" else to,
                         round(float(t["amount"]), 2), "CASH_WD" if to == "CASH" else "IMPS", f"UTR{seq:06d}", "COMPLETED", None))
            if fr == "VICTIM":
                disputed.append((1, tid))
            first_in.setdefault(to, tid)
        conn.import_from_iterable(txns, (S, "TRANSACTIONS"))
        net = {n: openings[n] for n in names}
        net["VICTIM"] = victim_out + 1000
        for t in txns:
            if t[4] in net:
                net[t[4]] -= t[6]
            if t[5] in net:
                net[t[5]] += t[6]
        for n, v in net.items():
            conn.execute(f"UPDATE {S}.ACCOUNTS SET closing_balance = {{v}} WHERE account_id = {{a}}", {"v": round(v, 2), "a": n})
        case_ref = (req.get("reference") or "").strip() or "PLAYGROUND-CASE"
        conn.import_from_iterable([(1, case_ref, "VICTIM", round(victim_out, 2), None, BASE_EPOCH)], (S, "CASES"))
        conn.import_from_iterable(disputed, (S, "CASE_DISPUTED_TXNS"))
        conn.import_from_iterable(CHECKLIST, (S, "CHECKLIST_ITEMS"))

        def blank(v):
            return None if v is None or str(v).strip() == "" else str(v).strip()

        stated = req.get("stated_amount")
        stated = None if stated in (None, "") else round(float(stated), 2)
        conn.import_from_iterable([(1, 1, None, ref_epoch, blank(req.get("officer")), blank(req.get("designation")),
                                    blank(req.get("agency")), blank(req.get("contact")), blank(req.get("reference")),
                                    blank(req.get("legal_provision")), blank(req.get("action_type")), stated,
                                    disputed[0][1])], (S, "REQUESTS"))
        targets = []
        for tg in req.get("targets") or []:
            a = str(tg.get("account", "")).strip().upper()
            if a not in names:
                continue
            scope = "AMOUNT" if tg.get("scope") == "AMOUNT" else "WHOLE_BALANCE"
            amt = round(float(tg.get("amount") or 0), 2) if scope == "AMOUNT" else None
            targets.append((1, a, scope, amt, first_in.get(a)))
        if targets:
            conn.import_from_iterable(targets, (S, "REQUEST_TARGETS"))
        load_ms = (time.perf_counter() - t0) * 1000

        steps = []
        conn.commit()
        eng = Engine(conn, S, Config(), log=lambda m: None, on_step=lambda i, s: steps.append(s))
        # One transaction for the analysis itself: commits are the expensive part on
        # a laptop Docker disk, and nothing else reads this schema.
        t1 = time.perf_counter()
        layers = eng.core()
        eng.request_checks()
        eng.run_file("50_review.sql", "CF5 scope review, CF4 dilution")
        engine_ms = (time.perf_counter() - t1) * 1000

        def rows(sql, params=None):
            return [{k.lower(): v for k, v in r.items()} for r in conn.execute(sql, params).fetchall()]

        sizing = rows(f"SELECT * FROM {S}.SIZING WHERE case_id = 1 ORDER BY layer, account_id")
        edges = rows(f"SELECT * FROM {S}.TRAIL_EDGES WHERE case_id = 1 AND GREATEST(carried_pr, carried_fifo, carried_lifo) > 0 ORDER BY ts_epoch, txn_id")
        cons = rows(f"SELECT * FROM {S}.CONSERVATION WHERE case_id = 1")
        findings = rows(f"SELECT * FROM {S}.REQ_FINDINGS ORDER BY kind DESC, item_code")
        status = rows(f"SELECT status FROM {S}.REQ_STATUS")
        review = rows(f"SELECT r.*, s.reason_codes FROM {S}.REVIEW r LEFT JOIN {S}.SIZING s ON s.case_id = r.case_id "
                      f"AND s.account_id = r.account_id ORDER BY r.layer, r.account_id")
        holder_ids = [s["account_id"] for s in sizing]
        timeline = []
        if holder_ids:
            sql, params = timeline_sql(S, 1, holder_ids)
            timeline = rows(sql, params)
        conn.commit()
    finally:
        conn.close()
    total_ms = (time.perf_counter() - t0) * 1000
    out = _shape(body, names, openings, req, sizing, edges, cons, findings, status, review, timeline, steps,
                 layers, round(victim_out, 2), ref_minute, load_ms, engine_ms, total_ms)
    _remember(body, out)
    return out


def _remember(body: dict, out: dict) -> None:
    """Every live analysis is kept in the append-only history (inputs and the key results)."""
    import json
    if not db.engine_ready():
        return
    try:
        summary = {"loss": out["loss"], "totals": out["totals"], "request_status": out["request_check"]["status"],
                   "conservation_ok": all(c["passed"] for c in out["conservation"]),
                   "accounts": [{k: a[k] for k in ("account_id", "lower", "upper", "status")} for a in out["accounts"]],
                   "review": [{k: v[k] for k in ("account_id", "requested", "upper", "classification")} for v in out["review"]]}
        title = (body.get("request") or {}).get("reference") or "Live analysis"
        c = db.connect()
        try:
            c.execute(f"INSERT INTO {db.AUDIT_SCHEMA}.LIVE_ANALYSES VALUES ({{i}}, CURRENT_TIMESTAMP, {{t}}, {{inp}}, {{sm}}, {{ms}})",
                      {"i": int(time.time() * 1_000_000), "t": str(title)[:200], "inp": json.dumps(body)[:200000],
                       "sm": json.dumps(summary)[:20000], "ms": out["engine"]["engine_ms"]})
        finally:
            c.close()
    except Exception:  # the history must never break an analysis
        pass


def _fl(v):
    return None if v is None else round(float(v), 2)


def _minute(epoch) -> int:
    return (int(epoch) - BASE_EPOCH) // 60


def _clock(epoch) -> str:
    return (BASE + timedelta(minutes=_minute(epoch))).strftime("%H:%M")


def _label(a):
    return {"VICTIM": "the victim", "OTHER_BANK": "an account at another bank"}.get(a, f"account {a}")


def _shape(body, names, openings, req, sizing, edges, cons, findings, status, review, timeline, steps, layers,
           loss, ref_minute, load_ms, engine_ms, total_ms):
    by_acc = {}
    for r in timeline:
        by_acc.setdefault(r["account_id"], []).append(r)
    size_by = {s["account_id"]: s for s in sizing}
    accounts = []
    for n in names:
        s = size_by.get(n)
        exp = explain_account(by_acc.get(n, []), n, s, label=_label, minute=_clock)
        accounts.append({
            "account_id": n, "opening": openings[n],
            "received": bool(s and s["received"]),
            "balance": _fl(s["balance_ref"]) if s else None,
            "retained_pr": _fl(s["retained_pr"]) if s else 0.0, "retained_fifo": _fl(s["retained_fifo"]) if s else 0.0,
            "retained_lifo": _fl(s["retained_lifo"]) if s else 0.0,
            "lower": _fl(s["lower_amt"]) if s else None, "upper": _fl(s["upper_amt"]) if s else None,
            "share_lo": None if not s or s["share_lo"] is None else float(s["share_lo"]),
            "share_hi": None if not s or s["share_hi"] is None else float(s["share_hi"]),
            "status": s["status"] if s else "NOT_REACHED", "layer": s["layer"] if s else None,
            "reasons": texts.reasons_list(s["reason_codes"]) if s else ["No disputed money reached this account."],
            "steps": exp["steps"],
            "summary": exp["summary"] or "No disputed money reached this account before the reference time.",
        })
    checklist_flagged = {f["item_code"] for f in findings if f["kind"] == "MISSING"}
    items = [{"code": f["item_code"], "label": f["label"], "kind": f["kind"], "detail": f["detail"]} for f in findings]
    items += [{"code": c[0], "label": c[2], "kind": "OK", "detail": "Stated"} for c in CHECKLIST if c[0] not in checklist_flagged]
    req_row = {"request_id": 1, "issuing_officer": req.get("officer"), "designation": req.get("designation"),
               "agency": req.get("agency")}
    reviews = []
    for r in review:
        rr = dict(r)
        for k in ("requested_amount", "lower_amt", "upper_amt", "ratio_to_upper", "excess_over_upper"):
            rr[k] = None if rr.get(k) is None else float(rr[k])
        reviews.append({
            "account_id": r["account_id"], "scope": r["requested_scope"], "requested": rr["requested_amount"],
            "lower": rr["lower_amt"], "upper": rr["upper_amt"], "classification": r["classification"],
            "ratio_to_upper": rr["ratio_to_upper"], "reasons": texts.review_reasons(rr),
        })
    edge_out = [{"txn_id": e["txn_id"], "from": e["from_acct"], "to": e["to_acct"] or "CASH",
                 "minute": _minute(e["ts_epoch"]), "time": _clock(e["ts_epoch"]), "amount": _fl(e["amount"]),
                 "layer": e["layer"], "carried_pr": _fl(e["carried_pr"]), "carried_fifo": _fl(e["carried_fifo"]),
                 "carried_lifo": _fl(e["carried_lifo"]), "terminal_state": e["terminal_state"]} for e in edges]
    forwarded = []
    for e in edges:
        if e["terminal_state"] == "OUT_OF_SCOPE":
            missing = [lbl for key, lbl in (("officer", "issuing officer"), ("designation", "designation"),
                                            ("contact", "agency contact"), ("legal_provision", "legal provision"))
                       if not (req.get(key) or "").strip()]
            forwarded.append(texts.forwarded_draft(
                {"case_ref": req.get("reference") or "PLAYGROUND-CASE", "loss": loss},
                {"issuing_officer": req.get("officer"), "designation": req.get("designation"), "agency": req.get("agency"),
                 "agency_contact": req.get("contact"), "legal_provision": req.get("legal_provision")},
                {**e, "to_acct": "OTHER_BANK"}, "the other bank", missing))
    conservation = [{"convention": c["convention"], "loss": _fl(c["loss"]), "retained": _fl(c["retained"]),
                     "exited": _fl(c["exited"]), "dust": _fl(c["dust"]), "absorbed": _fl(c["absorbed"]),
                     "difference": round(float(c["difference"]), 6), "passed": bool(c["passed"])} for c in cons]
    conservation.sort(key=lambda c: ["PR", "FIFO", "LIFO"].index(c["convention"]))
    whole = sum(max(a["balance"] or 0, 0) for a in accounts if a["balance"] is not None)
    return {
        "loss": loss, "ref_minute": ref_minute, "ref_time": (BASE + timedelta(minutes=ref_minute)).strftime("%H:%M"),
        "request_check": {"status": status[0]["status"] if status else None, "items": items,
                          "draft": texts.clarification_draft(req_row, findings, req.get("reference") or "")},
        "accounts": accounts, "edges": edge_out, "review": reviews, "forwarded": forwarded,
        "conservation": conservation,
        "totals": {"whole_balance": round(whole, 2),
                   # Totals per method: adding per-account upper bounds would mix the methods.
                   "traced_pr": round(sum(a["retained_pr"] or 0 for a in accounts), 2),
                   "traced_fifo": round(sum(a["retained_fifo"] or 0 for a in accounts), 2),
                   "requested": round(sum(v["requested"] or 0 for v in reviews), 2)},
        "engine": {"layer_passes": layers, "sql_steps": steps, "steps": group_steps(steps), "rules": rules(), "load_ms": round(load_ms), "engine_ms": round(engine_ms),
                   "total_ms": round(total_ms), "schema": SCHEMA},
    }
