"""Evaluation of the AI features on held-out synthetic data.

    python -m app.ai_eval            # from the backend folder; writes results/ai_evaluation.json

CF9  every held-out letter is read; each field is compared with the generator's
     answer key (TRACEHOLD_GT.LETTER_TRUTH, never read by the extraction).
AF7  a fixed question set; the rows returned must equal those of hand-written SQL,
     and out-of-scope questions must be refused.
AF8  account-holder letters are reworded; we count how often every fact survived.
AI-off  the live-analysis calculation is run with AI switched off and on, and the
     results must be identical (the calculation path never calls a model).

Groq's free tier allows about 8,000 tokens a minute, so a full run takes roughly
20-30 minutes; progress is printed.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime

from app import db
from app.textnum import norm_text, parse_amount

FIELDS = ["officer", "designation", "agency", "contact", "case_reference", "legal_provision", "quoted_txn",
          "stated_amount", "action_type", "targets"]


# ---------------------------------------------------------------- CF9
def _same(field: str, got, truth: str) -> bool:
    if field == "stated_amount":
        t = parse_amount(truth)
        return got is not None and t is not None and abs(float(got) - t) < 0.005
    if field == "targets":
        return sorted(str(x).upper() for x in (got or [])) == sorted(x for x in truth.split(";") if x)
    if field in ("action_type", "quoted_txn", "case_reference"):
        return str(got).strip().upper() == truth.strip().upper()
    return norm_text(str(got)) == norm_text(truth)


def eval_cf9(limit: int | None, log) -> dict:
    from app.ai.extract import extract
    conn = db.connect(admin=True)  # reads the answer key
    docs = conn.execute(f"SELECT doc_id, case_id, body FROM {db.SCHEMA}.REQUEST_DOCUMENTS WHERE split = 'HELDOUT' ORDER BY doc_id").fetchall()
    truth = {}
    for r in conn.execute(f"SELECT doc_id, field_name, true_value FROM {db.GT_SCHEMA}.LETTER_TRUTH").fetchall():
        truth.setdefault(int(r["DOC_ID"]), {})[r["FIELD_NAME"]] = r["TRUE_VALUE"] or ""
    conn.close()
    docs = docs[:limit] if limit else docs
    stats = {f: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for f in FIELDS}
    exact, no_quote, wrong_fields, total_fields, planted, flagged, failures = 0, 0, 0, 0, 0, 0, 0
    for k, d in enumerate(docs, 1):
        doc_id = int(d["DOC_ID"])
        try:
            ex = extract(d["BODY"], {"case_id": int(d["CASE_ID"])}, doc_id=doc_id, store=True)
        except Exception as e:  # noqa: BLE001
            failures += 1
            log(f"  [cf9] letter {doc_id}: failed ({e})")
            continue
        by = {f["field"]: f for f in ex["fields"]}
        all_ok = True
        for f in FIELDS:
            t = truth[doc_id].get(f, "")
            fr = by[f]
            used = fr["status"] in ("VERIFIED", "PARTLY") and fr["value"] not in (None, [], "")
            if used and any(i["start"] < 0 for i in fr["items"] if i["verified"]):
                no_quote += 1
            s = stats[f]
            total_fields += 1
            if t == "CONFLICT":
                planted += 1
                if fr["status"] == "CONFLICT":
                    flagged += 1
                    s["tp"] += 1
                    continue
                ok = False
                s["fn"] += 1
                if used:
                    s["fp"] += 1
            elif not t:
                ok = not used
                s["tn" if ok else "fp"] += 1
            elif used and _same(f, fr["value"], t):
                ok = True
                s["tp"] += 1
            else:
                ok = False
                s["fn"] += 1
                if used:
                    s["fp"] += 1
            if not ok:
                wrong_fields += 1
                all_ok = False
        exact += all_ok
        log(f"  [cf9] {k}/{len(docs)} letter {doc_id}: {'all fields right' if all_ok else 'some fields need a person'}")
    tp = sum(s["tp"] for s in stats.values())
    fp = sum(s["fp"] for s in stats.values())
    fn = sum(s["fn"] for s in stats.values())
    n = len(docs) - failures
    rnd = lambda x: None if x is None else round(x, 4)  # noqa: E731
    return {
        "split": "HELDOUT", "letters": n, "failed_calls": failures,
        "fields": [{"field": f, **s, "precision": rnd(s["tp"] / (s["tp"] + s["fp"]) if s["tp"] + s["fp"] else None),
                    "recall": rnd(s["tp"] / (s["tp"] + s["fn"]) if s["tp"] + s["fn"] else None)} for f, s in stats.items()],
        "overall": {"precision": rnd(tp / (tp + fp) if tp + fp else 0), "recall": rnd(tp / (tp + fn) if tp + fn else 0),
                    "exact_match_letters": rnd(exact / n if n else 0), "values_without_quote": no_quote,
                    "needs_correction_share": rnd(wrong_fields / total_fields if total_fields else 0)},
        "conflicts": {"planted": planted, "flagged": flagged},
        "definition": "A field is right when the value that would be used (status checked) equals the answer key, when a "
                      "planted conflict is flagged, or when nothing is used for a field the letter does not state. Values "
                      "that failed the checks are not used and count as missed.",
    }


# ---------------------------------------------------------------- AF7
QUESTIONS = [
    ("Which active holds older than 90 days exceed their supported amount?",
     "SELECT restraint_id FROM TH_RESULTS.RESTRAINTS WHERE active = 1 AND days_held > 90 AND over_hold = 1", "restraint_id"),
    ("How many police requests are complete, incomplete or conflicting?",
     "SELECT request_status, COUNT(*) FROM TH_RESULTS.REQUESTS GROUP BY request_status", None),
    ("Which holds are still active although the case is closed or a clean chit was given?",
     "SELECT restraint_id FROM TH_RESULTS.RESTRAINTS WHERE closed_still_held = 1", "restraint_id"),
    ("How many account figures are undeterminable?",
     "SELECT COUNT(*) FROM TH_RESULTS.ACCOUNT_SIZING WHERE status = 'UNDETERMINABLE'", None),
    ("Which 5 cases lock the most money that the records do not support?",
     "SELECT case_ref FROM TH_RESULTS.CASES ORDER BY unsupported_amount DESC LIMIT 5", "case_ref"),
    ("How many cases failed the conservation check?",
     "SELECT COUNT(*) FROM TH_RESULTS.CASES WHERE conservation_ok = FALSE", None),
    ("What is the total held amount in active holds under Rs 50,000?",
     "SELECT SUM(held_amount) FROM TH_RESULTS.RESTRAINTS WHERE active = 1 AND band = 'UNDER_50K'", None),
    ("In which cases does account AC0126798 appear?",
     "SELECT case_ref FROM TH_RESULTS.ACCOUNT_SIZING WHERE account_id = 'AC0126798'", "case_ref"),
    ("How many requested holds exceed the evidence?",
     "SELECT COUNT(*) FROM TH_RESULTS.REVIEW_FLAGS WHERE classification = 'EXCEEDS_EVIDENCE'", None),
    ("Which active holds have had no update from the police for 15 days or more?",
     "SELECT restraint_id FROM TH_RESULTS.RESTRAINTS WHERE escalate = 1", "restraint_id"),
]
REFUSE = ["List every transaction made by account AC0126507 last month.",
          "Which account holders are guilty of fraud?"]


def _norm_cell(v):
    try:
        f = float(str(v))
        return f"{f:.2f}"
    except (TypeError, ValueError):
        return str(v).strip().upper()


def eval_af7(log) -> dict:
    from app.ai.ask import AskRejected, ask
    conn = db.connect(admin=True, fetch_dict=False)
    items, correct, fid_fail = [], 0, 0
    for q, sql, key in QUESTIONS:
        exp = conn.execute(sql).fetchall()
        try:
            r = ask(q)
        except (AskRejected, RuntimeError) as e:
            items.append({"question": q, "ok": False, "note": f"error: {e}"})
            continue
        fid_fail += 0 if r["fidelity"]["ok"] else 1
        if key:  # compare the key column as a set
            want = {_norm_cell(x[0]) for x in exp}
            cols = [c.lower() for c in r["columns"]]
            got = {_norm_cell(row[cols.index(key)]) for row in r["rows"]} if key in cols else set()
            ok = want == got or (len(want) > 200 and got <= want and len(got) == 200)
        else:  # aggregate: every expected value must appear in the returned rows
            want = {_norm_cell(v) for row in exp for v in row if v is not None}
            got = {_norm_cell(v) for row in r["rows"] for v in row if v is not None}
            ok = want <= got
        correct += ok
        items.append({"question": q, "ok": ok, "note": f"{r['mode'].lower()}, {r['row_count']} rows"
                      + ("" if r["fidelity"]["ok"] else ", wording rejected")})
        log(f"  [af7] {'ok ' if ok else 'BAD'} {q}")
    for q in REFUSE:
        try:
            r = ask(q)
            ok = r["mode"] == "REFUSED"
        except AskRejected:
            ok = True
        correct += ok
        items.append({"question": q, "ok": ok, "note": "should be refused" + ("" if ok else " (was answered)")})
        log(f"  [af7] {'ok ' if ok else 'BAD'} (refuse) {q}")
    conn.close()
    n = len(QUESTIONS) + len(REFUSE)
    return {"questions": n, "correct": correct, "share_correct": round(correct / n, 4), "fidelity_failures": fid_fail,
            "items": items}


# ---------------------------------------------------------------- AF8
def eval_af8(n: int, log) -> dict:
    from app import main
    from app.ai.reword import reword
    conn = db.connect(admin=True)
    rows = conn.execute(f"""SELECT v.case_id, v.account_id FROM {db.SCHEMA}.REVIEW v
                            JOIN {db.SCHEMA}.SIZING z ON z.case_id = v.case_id AND z.account_id = v.account_id
                            WHERE z.status IN ('RANGE', 'DETERMINED', 'UNDETERMINABLE')
                            ORDER BY MOD(v.case_id * 7919, 1009) LIMIT {int(n)}""").fetchall()
    conn.close()
    used, problems = 0, []
    for k, r in enumerate(rows, 1):
        t = main.explanation(int(r["CASE_ID"]), r["ACCOUNT_ID"])["text"]
        try:
            res = reword(t, f"eval {r['CASE_ID']} {r['ACCOUNT_ID']}")
        except Exception as e:  # noqa: BLE001
            problems.append(f"call failed: {e}")
            continue
        used += res["used"] == "AI"
        if res["used"] != "AI":
            problems += res["check"]["problems"]
        log(f"  [af8] {k}/{len(rows)}: {'reworded text used' if res['used'] == 'AI' else 'template kept'}")
    m = len(rows)
    return {"letters": m, "used_ai": used, "fell_back": m - used, "fidelity_share": round(used / m, 4) if m else 0,
            "fallback_share": round((m - used) / m, 4) if m else 0, "fallback_reasons": problems[:20]}


# ---------------------------------------------------------------- AI-off
def eval_ai_off(log) -> dict:
    from app.playground import SCENARIOS, run

    def strip(r):
        r = json.loads(json.dumps(r, default=str))
        r.pop("engine", None)
        return r
    body = {k: SCENARIOS[0][k] for k in ("accounts", "transfers", "request")}
    before = os.environ.get("TRACEHOLD_AI")
    try:
        os.environ["TRACEHOLD_AI"] = "off"
        off = strip(run(body))
        os.environ.pop("TRACEHOLD_AI", None)
        on = strip(run(body))
    finally:
        if before is None:
            os.environ.pop("TRACEHOLD_AI", None)
        else:
            os.environ["TRACEHOLD_AI"] = before
    same = off == on
    log(f"  [ai-off] worked example identical with AI off and on: {same}")
    return {"passed": same, "detail": "The worked example gives identical results (every figure, status and check) with AI "
                                      "switched off and on; the calculation path does not import the AI package."}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--letters", type=int, default=None, help="limit the number of held-out letters")
    ap.add_argument("--rewordings", type=int, default=8)
    ap.add_argument("--only", choices=["cf9", "af7", "af8", "off"], default=None)
    a = ap.parse_args()
    from app.ai.llm import model, status
    if not status()["enabled"]:
        raise SystemExit(f"AI is off: {status()['reason']}")
    out_path = db.RESULTS / "ai_evaluation.json"
    out = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() and a.only else {}
    t0 = time.time()
    log = lambda m: print(m, flush=True)  # noqa: E731
    if a.only in (None, "off"):
        out["ai_off"] = eval_ai_off(log)
    if a.only in (None, "cf9"):
        out["cf9"] = eval_cf9(a.letters, log)
    if a.only in (None, "af7"):
        out["af7"] = eval_af7(log)
    if a.only in (None, "af8"):
        out["af8"] = eval_af8(a.rewordings, log)
    out.update({"generated_at": datetime.now().isoformat(timespec="seconds"), "model": model(),
                "note": "Synthetic letters and fixed question sets only. Prompts were tuned on the development letters; "
                        "results are reported on held-out letters. Not a claim about real-world accuracy."})
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"written {out_path} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
