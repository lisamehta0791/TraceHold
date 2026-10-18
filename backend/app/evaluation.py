"""Evaluation harness and policy simulation.

This is the only code that reads the ground-truth schema. It compares the
derived tables written by the analysis with the generator's answer key.

    python -m app.evaluation            # prints a summary, writes backend/results/evaluation.json
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

from app import db

S, GT = db.SCHEMA, db.GT_SCHEMA

REQUEST_DEFECTS = {
    "MISSING_OFFICER": "OFFICER", "MISSING_DESIGNATION": "DESIGNATION", "MISSING_CONTACT": "CONTACT",
    "MISSING_CASE_REF": "CASE_REF", "MISSING_LEGAL_PROVISION": "LEGAL_PROVISION", "MISSING_AMOUNT": "AMOUNT",
    "MISSING_TXN": "TXN", "AMOUNT_MISMATCH": "AMOUNT_MISMATCH", "AMOUNT_UNIT": "AMOUNT_UNIT",
    "TXN_NOT_FOUND": "TXN_NOT_FOUND", "TARGET_MISMATCH": "TARGET_MISMATCH", "REUSED_REFERENCE": "REUSED_REFERENCE",
    "REQUESTED_EXCEEDS": "REQUESTED_EXCEEDS", "DUPLICATE_REQUEST": "DUPLICATE_REQUEST",
}
TARGET_LEVEL = {"TARGET_MISMATCH", "REQUESTED_EXCEEDS"}


def _f(x):
    return None if x is None else float(x)


def _prf(tp, fp, fn):
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(tp / (tp + fp), 4) if tp + fp else None,
            "recall": round(tp / (tp + fn), 4) if tp + fn else None}


def evaluate(q) -> dict:
    out = {"generated_at": datetime.now().isoformat(timespec="seconds"),
           "note": "All results are on synthetic data and are not evidence of real-world performance."}

    # ---------------------------------------------------------- request defects (CF1)
    planted = q(f"SELECT defect_type, request_id, account_id, detail FROM {GT}.PLANTED_DEFECTS "
                f"WHERE request_id IS NOT NULL")
    code_to_defect = {v: k for k, v in REQUEST_DEFECTS.items()}
    by_req = defaultdict(set)
    for p in planted:
        key = (p["account_id"] if p["defect_type"] in TARGET_LEVEL else None)
        by_req[p["request_id"]].add((p["defect_type"], key))
    # A duplicate request inherits the defects of the request it copies.
    for p in planted:
        if p["defect_type"] == "DUPLICATE_REQUEST" and (p["detail"] or "").startswith("duplicate of "):
            src = int(p["detail"].split()[-1])
            by_req[p["request_id"]] |= {d for d in by_req.get(src, set()) if d[0] != "DUPLICATE_REQUEST"}
    planted_set = {(r, d, k) for r, ds in by_req.items() for d, k in ds}
    found = q(f"SELECT request_id, account_id, item_code FROM {S}.REQ_FINDINGS")
    found_set = set()
    for x in found:
        d = code_to_defect.get(x["item_code"], x["item_code"])
        found_set.add((x["request_id"], d, x["account_id"] if d in TARGET_LEVEL else None))
    rows = []
    for d in sorted(set(REQUEST_DEFECTS) | {x[1] for x in found_set}):
        pl = {x for x in planted_set if x[1] == d}
        fd = {x for x in found_set if x[1] == d}
        m = _prf(len(pl & fd), len(fd - pl), len(pl - fd))
        rows.append({"defect": d, "planted": len(pl), "detected": len(fd), **m})
    out["request_defects"] = rows
    conflict_kinds = {"AMOUNT_MISMATCH", "AMOUNT_UNIT", "TXN_NOT_FOUND", "TARGET_MISMATCH", "REUSED_REFERENCE",
                      "REQUESTED_EXCEEDS", "DUPLICATE_REQUEST"}
    conflicted = {r for r, d, k in planted_set if d in conflict_kinds}
    complete = {x["request_id"] for x in q(f"SELECT request_id FROM {S}.REQ_STATUS WHERE status = 'COMPLETE'")}
    out["request_defects_summary"] = {
        **_prf(len(planted_set & found_set), len(found_set - planted_set), len(planted_set - found_set)),
        "planted_conflict_requests": len(conflicted),
        "planted_conflict_reported_complete": len(conflicted & complete)}

    # ---------------------------------------------------------- path reconstruction (CF2)
    path = q(f"""
        WITH gt AS (
            SELECT c.case_id, c.txn_id, g.scenario
            FROM {GT}.CHAIN_TXNS c
            JOIN {GT}.CASE_SCENARIO g ON g.case_id = c.case_id
            JOIN {S}.CASE_REF r ON r.case_id = c.case_id
            JOIN {S}.TRANSACTIONS t ON t.txn_id = c.txn_id
            WHERE t.ts_epoch <= r.ref_epoch
        ),
        an AS (
            SELECT e.case_id, e.txn_id, g.scenario,
                   CASE WHEN GREATEST(e.carried_pr, e.carried_fifo, e.carried_lifo) >= 0.5 * e.amount THEN 1 ELSE 0 END AS major
            FROM {S}.TRAIL_EDGES e JOIN {GT}.CASE_SCENARIO g ON g.case_id = e.case_id
            WHERE GREATEST(e.carried_pr, e.carried_fifo, e.carried_lifo) > 0
        )
        SELECT COALESCE(gt.scenario, an.scenario) AS scenario,
               SUM(CASE WHEN gt.txn_id IS NOT NULL AND an.txn_id IS NOT NULL THEN 1 ELSE 0 END) AS tp,
               SUM(CASE WHEN gt.txn_id IS NULL AND an.txn_id IS NOT NULL THEN 1 ELSE 0 END) AS fp,
               SUM(CASE WHEN gt.txn_id IS NOT NULL AND an.txn_id IS NULL THEN 1 ELSE 0 END) AS fn,
               SUM(CASE WHEN gt.txn_id IS NOT NULL AND an.major = 1 THEN 1 ELSE 0 END) AS tp_major,
               SUM(CASE WHEN gt.txn_id IS NULL AND an.major = 1 THEN 1 ELSE 0 END) AS fp_major,
               SUM(CASE WHEN gt.txn_id IS NOT NULL AND COALESCE(an.major, 0) = 0 THEN 1 ELSE 0 END) AS fn_major
        FROM gt FULL OUTER JOIN an ON an.case_id = gt.case_id AND an.txn_id = gt.txn_id
        GROUP BY COALESCE(gt.scenario, an.scenario) ORDER BY 1""")
    out["path"] = [{"scenario": r["scenario"], **_prf(r["tp"], r["fp"], r["fn"]),
                    "major": _prf(r["tp_major"], r["fp_major"], r["fn_major"])} for r in path]
    tot = {k: sum(r[k] for r in path) for k in ("tp", "fp", "fn", "tp_major", "fp_major", "fn_major")}
    out["path_summary"] = {"any_disputed": _prf(tot["tp"], tot["fp"], tot["fn"]),
                           "major_share": _prf(tot["tp_major"], tot["fp_major"], tot["fn_major"]),
                           "definition": "An edge is reconstructed if it carries disputed funds (>= the dust threshold) "
                                         "under any convention; 'major' requires at least 50% of the transfer to be "
                                         "disputed. Pro-rata legitimately spreads small disputed fractions to ordinary "
                                         "payments of commingled accounts, which count as false positives here."}

    # ---------------------------------------------------------- amounts (CF3)
    amt = q(f"""
        WITH taint AS (SELECT case_id, account_id FROM {GT}.PLANTED_DEFECTS WHERE defect_type = 'UNDETERMINABLE'),
        an AS (
            SELECT case_id, account_id, 'PR' AS conv, CAST(retained_pr AS DOUBLE) AS v FROM {S}.SIZING WHERE received = 1 AND status <> 'UNDETERMINABLE'
            UNION ALL SELECT case_id, account_id, 'FIFO', CAST(retained_fifo AS DOUBLE) FROM {S}.SIZING WHERE received = 1 AND status <> 'UNDETERMINABLE'
            UNION ALL SELECT case_id, account_id, 'LIFO', CAST(retained_lifo AS DOUBLE) FROM {S}.SIZING WHERE received = 1 AND status <> 'UNDETERMINABLE'
        ),
        g AS (SELECT l.case_id, l.account_id, l.convention AS conv, l.retained AS v FROM {GT}.LEDGER l
              WHERE NOT EXISTS (SELECT 1 FROM taint t WHERE t.case_id = l.case_id AND t.account_id = l.account_id)),
        j AS (SELECT COALESCE(an.conv, g.conv) AS conv, COALESCE(an.v, 0) AS av, COALESCE(g.v, 0) AS gv
              FROM an FULL OUTER JOIN g ON g.case_id = an.case_id AND g.account_id = an.account_id AND g.conv = an.conv)
        SELECT conv, COUNT(*) AS n, AVG(ABS(av - gv)) AS mae, MAX(ABS(av - gv)) AS max_abs_err,
               AVG(CASE WHEN ABS(av - gv) <= 1 THEN 1.0 ELSE 0.0 END) AS within_1_rupee,
               AVG(CASE WHEN ABS(av - gv) <= 0.01 THEN 1.0 ELSE 0.0 END) AS within_1_paisa,
               SUM(ABS(av - gv)) / NULLIF(SUM(ABS(gv)), 0) AS relative_err
        FROM j GROUP BY conv ORDER BY conv DESC""")
    cov = q(f"""
        WITH g AS (SELECT case_id, account_id,
                          MAX(CASE WHEN convention = 'PR' THEN retained END) AS gpr,
                          MAX(CASE WHEN convention = 'FIFO' THEN retained END) AS gfifo
                   FROM {GT}.LEDGER GROUP BY case_id, account_id)
        SELECT COUNT(*) AS n,
               AVG(CASE WHEN g.gpr BETWEEN CAST(s.lower_amt AS DOUBLE) - 0.01 AND CAST(s.upper_amt AS DOUBLE) + 0.01
                         AND g.gfifo BETWEEN CAST(s.lower_amt AS DOUBLE) - 0.01 AND CAST(s.upper_amt AS DOUBLE) + 0.01
                        THEN 1.0 ELSE 0.0 END) AS coverage
        FROM {S}.SIZING s JOIN g ON g.case_id = s.case_id AND g.account_id = s.account_id
        WHERE s.received = 1 AND s.status <> 'UNDETERMINABLE'""")[0]
    out["amount"] = [{"convention": r["conv"], "n": r["n"], "mae": _f(r["mae"]), "max_abs_err": _f(r["max_abs_err"]),
                      "within_1_rupee": _f(r["within_1_rupee"]), "within_1_paisa": _f(r["within_1_paisa"]),
                      "relative_err": _f(r["relative_err"]), "range_coverage": _f(cov["coverage"])} for r in amt]

    # ---------------------------------------------------------- conservation
    c = q(f"SELECT COUNT(*) AS checks, SUM(passed) AS passed, MAX(ABS(difference)) AS max_diff FROM {S}.CONSERVATION")[0]
    out["conservation"] = {"checks": c["checks"], "passed": c["passed"], "max_abs_difference": _f(c["max_diff"])}

    # ---------------------------------------------------------- abstention (CF6)
    ab = q(f"""
        WITH p AS (SELECT DISTINCT case_id, account_id FROM {GT}.PLANTED_DEFECTS WHERE defect_type = 'UNDETERMINABLE')
        SELECT SUM(CASE WHEN p.case_id IS NOT NULL THEN 1 ELSE 0 END) AS planted,
               SUM(CASE WHEN p.case_id IS NOT NULL AND s.status = 'UNDETERMINABLE' THEN 1 ELSE 0 END) AS correct,
               SUM(CASE WHEN p.case_id IS NULL THEN 1 ELSE 0 END) AS determinable,
               SUM(CASE WHEN p.case_id IS NULL AND s.status = 'UNDETERMINABLE' THEN 1 ELSE 0 END) AS wrong
        FROM {S}.SIZING s LEFT JOIN p ON p.case_id = s.case_id AND p.account_id = s.account_id
        WHERE s.received = 1""")[0]
    out["abstention"] = {"planted": ab["planted"], "correctly_undeterminable": ab["correct"],
                         "determinable": ab["determinable"], "wrongly_undeterminable": ab["wrong"],
                         "share_correct": round(ab["correct"] / ab["planted"], 4) if ab["planted"] else None,
                         "share_wrong": round(ab["wrong"] / ab["determinable"], 6) if ab["determinable"] else None}

    # ---------------------------------------------------------- over-broad requests (CF5)
    ob = q(f"""
        WITH dup AS (SELECT DISTINCT request_id FROM {S}.REQ_FINDINGS WHERE item_code = 'DUPLICATE_REQUEST'),
        taint AS (SELECT DISTINCT case_id, account_id FROM {GT}.PLANTED_DEFECTS WHERE defect_type = 'UNDETERMINABLE'),
        g AS (SELECT case_id, account_id, MAX(CASE WHEN convention IN ('PR', 'FIFO') THEN retained END) AS gup
              FROM {GT}.LEDGER GROUP BY case_id, account_id),
        v AS (SELECT r.*, COALESCE(g.gup, 0) AS gup,
                     CASE WHEN CAST(r.requested_amount AS DOUBLE) > COALESCE(g.gup, 0) + 1 THEN 1 ELSE 0 END AS planted
              FROM {S}.REVIEW r LEFT JOIN g ON g.case_id = r.case_id AND g.account_id = r.account_id
              WHERE r.request_id NOT IN (SELECT request_id FROM dup)
                AND NOT EXISTS (SELECT 1 FROM taint t WHERE t.case_id = r.case_id AND t.account_id = r.account_id))
        SELECT SUM(planted) AS planted,
               SUM(CASE WHEN planted = 1 AND classification = 'EXCEEDS_EVIDENCE' THEN 1 ELSE 0 END) AS tp,
               SUM(CASE WHEN planted = 0 AND classification = 'EXCEEDS_EVIDENCE' THEN 1 ELSE 0 END) AS fp,
               SUM(CASE WHEN planted = 1 AND classification <> 'EXCEEDS_EVIDENCE' THEN 1 ELSE 0 END) AS fn,
               COUNT(*) AS targets
        FROM v""")[0]
    out["overbroad"] = {"planted": ob["planted"], "flagged": ob["tp"], "targets": ob["targets"],
                        **_prf(ob["tp"], ob["fp"], ob["fn"]),
                        "definition": "A request target is over-broad when the requested amount exceeds the ground-truth "
                                      "upper bound (larger of the pro-rata and FIFO ledgers) by more than one rupee."}

    # ---------------------------------------------------------- determinism (AF6)
    runs = q(f"SELECT run_id, checksum, snapshot_id FROM {db.AUDIT_SCHEMA}.RUNS WHERE run_status = 'DONE' ORDER BY run_id DESC LIMIT 2")
    if len(runs) == 2:
        out["determinism"] = {"runs_compared": [runs[1]["run_id"], runs[0]["run_id"]],
                              "same_snapshot": runs[0]["snapshot_id"] == runs[1]["snapshot_id"],
                              "identical_results": runs[0]["checksum"] == runs[1]["checksum"]}
    return out


POLICIES = [
    ("WHOLE_BALANCE", "Whole balance", "Hold the whole balance of every targeted account"),
    ("REQUESTED", "As requested", "Hold what was requested"),
    ("LOWER", "Lower bound", "Hold the lower end of the supported range"),
    ("UPPER", "Upper bound", "Hold the upper end of the supported range"),
]


def policy_simulation(q) -> dict:
    """AF3: compare hold policies against the ground-truth pro-rata and FIFO ledgers
    at each case's reference time. Undeterminable accounts keep the requested hold
    under the LOWER and UPPER policies (a person must decide them)."""
    rows = q(f"""
        WITH dup AS (SELECT DISTINCT request_id FROM {S}.REQ_FINDINGS WHERE item_code = 'DUPLICATE_REQUEST'),
        g AS (SELECT case_id, account_id,
                     MAX(CASE WHEN convention = 'PR' THEN retained END) AS gpr,
                     MAX(CASE WHEN convention = 'FIFO' THEN retained END) AS gfifo
              FROM {GT}.LEDGER GROUP BY case_id, account_id),
        t AS (
            SELECT r.case_id, r.account_id, sc.scenario,
                   GREATEST(CAST(r.balance_ref AS DOUBLE), 0) AS whole,
                   LEAST(CAST(r.requested_amount AS DOUBLE), GREATEST(CAST(r.balance_ref AS DOUBLE), 0)) AS requested,
                   CASE WHEN r.status = 'UNDETERMINABLE' OR r.status IS NULL
                        THEN LEAST(CAST(r.requested_amount AS DOUBLE), GREATEST(CAST(r.balance_ref AS DOUBLE), 0))
                        ELSE CAST(r.lower_amt AS DOUBLE) END AS lower_h,
                   CASE WHEN r.status = 'UNDETERMINABLE' OR r.status IS NULL
                        THEN LEAST(CAST(r.requested_amount AS DOUBLE), GREATEST(CAST(r.balance_ref AS DOUBLE), 0))
                        ELSE CAST(r.upper_amt AS DOUBLE) END AS upper_h,
                   COALESCE(g.gpr, 0) AS gpr, COALESCE(g.gfifo, 0) AS gfifo
            FROM {S}.REVIEW r
            JOIN {GT}.CASE_SCENARIO sc ON sc.case_id = r.case_id
            LEFT JOIN g ON g.case_id = r.case_id AND g.account_id = r.account_id
            WHERE r.request_id NOT IN (SELECT request_id FROM dup) AND r.balance_ref IS NOT NULL
        )
        SELECT scenario,
               SUM(LEAST(whole, gpr)) AS w_held, SUM(GREATEST(whole - gpr, 0)) AS w_locked, SUM(CASE WHEN whole > 0 THEN 1 ELSE 0 END) AS w_n,
               SUM(LEAST(requested, gpr)) AS r_held, SUM(GREATEST(requested - gpr, 0)) AS r_locked, SUM(CASE WHEN requested > 0 THEN 1 ELSE 0 END) AS r_n,
               SUM(LEAST(lower_h, gpr)) AS l_held, SUM(GREATEST(lower_h - gpr, 0)) AS l_locked, SUM(CASE WHEN lower_h > 0 THEN 1 ELSE 0 END) AS l_n,
               SUM(LEAST(upper_h, gpr)) AS u_held, SUM(GREATEST(upper_h - gpr, 0)) AS u_locked, SUM(CASE WHEN upper_h > 0 THEN 1 ELSE 0 END) AS u_n,
               SUM(LEAST(whole, gfifo)) AS w_held_f, SUM(LEAST(requested, gfifo)) AS r_held_f,
               SUM(LEAST(lower_h, gfifo)) AS l_held_f, SUM(LEAST(upper_h, gfifo)) AS u_held_f,
               SUM(gpr) AS truth_pr, SUM(gfifo) AS truth_fifo
        FROM t GROUP BY scenario ORDER BY scenario""")
    keys = {"WHOLE_BALANCE": "w", "REQUESTED": "r", "LOWER": "l", "UPPER": "u"}
    policies = []
    for pol, label, description in POLICIES:
        k = keys[pol]
        by = [{"scenario": r["scenario"], "disputed_held": _f(r[f"{k}_held"]),
               "non_disputed_locked": _f(r[f"{k}_locked"]), "accounts_restricted": r[f"{k}_n"]} for r in rows]
        policies.append({
            "policy": pol, "label": label, "description": description,
            "disputed_held": sum(b["disputed_held"] or 0 for b in by),
            "non_disputed_locked": sum(b["non_disputed_locked"] or 0 for b in by),
            "accounts_restricted": sum(b["accounts_restricted"] or 0 for b in by),
            "disputed_held_fifo_truth": sum(_f(r[f"{k}_held_f"]) or 0 for r in rows),
            "by_scenario": by,
        })
    return {"hold_time": "each case's reference time (when the request was received)",
            "truth": {"pro_rata": sum(_f(r["truth_pr"]) or 0 for r in rows),
                      "fifo": sum(_f(r["truth_fifo"]) or 0 for r in rows)},
            "note": "Synthetic data only. 'Disputed held' is measured against the generator's pro-rata ledger "
                    "(the FIFO-ledger figure is also given). These are not real-world recovery or harm figures.",
            "policies": policies}


def main():
    import pyexasol
    conn = db.connect(admin=True, fetch_mapper=pyexasol.exasol_mapper)  # reads the answer key

    def q(sql, params=None):
        from decimal import Decimal
        rows = conn.execute(sql, params).fetchall()
        return [{k.lower(): (float(v) if isinstance(v, Decimal) else v) for k, v in r.items()} for r in rows]

    res = evaluate(q)
    res["policy_simulation"] = policy_simulation(q)
    path = db.RESULTS / "evaluation.json"
    path.write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps({k: v for k, v in res.items() if k not in ("path", "request_defects", "policy_simulation")},
                     indent=2, default=str))
    print(f"\nwritten {path}")


if __name__ == "__main__":
    main()
