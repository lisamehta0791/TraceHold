"""Step-by-step explanation of how an account's disputed amount was calculated.

The numbers come from Exasol: the per-posting ledger (EV) and the allocation
state the engine left behind (PR_IN, FIFO_SEG, TRAIL_EDGES). This module only
turns them into plain sentences.
"""
from __future__ import annotations

from app.texts import inr


def timeline_sql(schema: str, case_id: int, accounts: list[str]) -> tuple[str, dict]:
    """Per account and posting: balance, disputed money under pro-rata and FIFO."""
    names = ", ".join("{a%d}" % i for i in range(len(accounts)))
    params = {f"a{i}": a for i, a in enumerate(accounts)}
    params["case"] = case_id
    S = schema
    sql = f"""
        WITH ev AS (
            SELECT e.* FROM {S}.EV e
            JOIN {S}.CASE_REF c ON c.case_id = {{case}}
            WHERE e.account_id IN ({names}) AND e.ord_epoch <= c.ref_epoch
        ),
        first_in AS (
            SELECT account_id, MIN(ev_rank) AS r FROM {S}.PR_IN WHERE case_id = {{case}} GROUP BY account_id
        ),
        pr AS (
            SELECT e.account_id, e.ev_rank,
                   SUM(j.d * CASE WHEN e.lcum - j.lcum < -700 THEN 0.0 ELSE EXP(e.lcum - j.lcum) END) AS disp
            FROM ev e JOIN {S}.PR_IN j ON j.case_id = {{case}} AND j.account_id = e.account_id AND j.ev_rank <= e.ev_rank
            GROUP BY e.account_id, e.ev_rank
        ),
        ff AS (
            SELECT e.account_id, e.ev_rank,
                   SUM(GREATEST(0, f.hi - GREATEST(f.lo, e.cout_before + CASE WHEN e.kind = 'D' THEN e.amount ELSE 0 END))) AS disp
            FROM ev e JOIN {S}.FIFO_SEG f ON f.case_id = {{case}} AND f.account_id = e.account_id AND f.arr_rank <= e.ev_rank
            GROUP BY e.account_id, e.ev_rank
        ),
        ed AS (SELECT txn_id, carried_pr, carried_fifo FROM {S}.TRAIL_EDGES WHERE case_id = {{case}})
        SELECT ev.account_id, ev.ev_rank, ev.txn_id, ev.ts_epoch, ev.kind, ev.amount, ev.counterparty, ev.channel,
               ev.bal_before, ev.bal_after,
               COALESCE(pr.disp, 0) AS disp_pr, COALESCE(ff.disp, 0) AS disp_fifo,
               COALESCE(ed.carried_pr, 0) AS carried_pr, COALESCE(ed.carried_fifo, 0) AS carried_fifo
        FROM ev
        LEFT JOIN first_in fi ON fi.account_id = ev.account_id
        LEFT JOIN pr ON pr.account_id = ev.account_id AND pr.ev_rank = ev.ev_rank
        LEFT JOIN ff ON ff.account_id = ev.account_id AND ff.ev_rank = ev.ev_rank
        LEFT JOIN ed ON ed.txn_id = ev.txn_id
        WHERE ev.ev_rank >= COALESCE(fi.r, 999999999) - 1
        ORDER BY ev.account_id, ev.ev_rank
        LIMIT 4000"""
    return sql, params


def _f(x) -> float:
    return float(x or 0)


def explain_account(rows: list[dict], account: str, sizing: dict | None, label=lambda a: a,
                    minute=None) -> dict:
    """Turn ledger rows into steps. `label` names counterparties; `minute(epoch)` formats times."""
    steps = []
    prev_pr = prev_ff = 0.0
    for r in rows:
        amt = _f(r["amount"])
        bal_before, bal_after = _f(r["bal_before"]), _f(r["bal_after"])
        pr_after, ff_after = _f(r["disp_pr"]), _f(r["disp_fifo"])
        cp = label(r["counterparty"]) if r["counterparty"] else ("cash withdrawal" if r["kind"] == "D" else "outside")
        when = minute(r["ts_epoch"]) if minute else None
        if r["kind"] == "C":
            got_pr, got_ff = _f(r["carried_pr"]), _f(r["carried_fifo"])
            if got_pr > 0.005 or got_ff > 0.005:
                text = (f"Received {inr(amt)} from {cp}. The records trace {inr(got_pr)} of it to the fraud under "
                        f"pro-rata and {inr(got_ff)} under FIFO.")
                if abs(got_pr - amt) < 0.01 and abs(got_ff - amt) < 0.01:
                    text = f"Received {inr(amt)} from {cp} — all of it is the reported (disputed) money."
            else:
                text = f"Received {inr(amt)} from {cp}. None of it is traced to the fraud."
            if bal_before < -0.005:
                text += f" The account was overdrawn by {inr(-bal_before)}, so that part only repays the overdraft."
            calc = None
        else:
            share = 1.0 if bal_before <= 0.005 else min(1.0, amt / bal_before)
            out_pr, out_ff = _f(r["carried_pr"]), _f(r["carried_fifo"])
            text = f"Paid {inr(amt)} to {cp}."
            if prev_pr > 0.005 or prev_ff > 0.005:
                calc = {
                    "pro_rata": (f"The payment is {share * 100:.1f}% of the {inr(bal_before)} balance, so {share * 100:.1f}% "
                                 f"of the {inr(prev_pr)} disputed money left with it: {inr(out_pr)}."),
                    "fifo": (f"Oldest money leaves first. Of the {inr(amt)} paid, {inr(out_ff)} was disputed money "
                             f"(the rest was older money already in the account)." if out_ff < amt - 0.005 else
                             f"Oldest money leaves first; by now the disputed money is the oldest, so all {inr(amt)} paid is disputed."),
                }
                if out_ff < 0.005:
                    calc["fifo"] = "Oldest money leaves first. The account's older own money covers this payment, so no disputed money leaves."
            else:
                calc = None
        steps.append({
            "txn_id": r["txn_id"], "when": when, "kind": "IN" if r["kind"] == "C" else "OUT", "amount": round(amt, 2),
            "counterparty": cp, "balance_after": round(bal_after, 2),
            "disputed_pr_after": round(pr_after, 2), "disputed_fifo_after": round(ff_after, 2),
            "text": text, "calc": calc,
        })
        prev_pr, prev_ff = pr_after, ff_after

    summary = None
    if sizing:
        st = sizing.get("status")
        bal = _f(sizing.get("balance_ref"))
        p, f = _f(sizing.get("retained_pr")), _f(sizing.get("retained_fifo"))
        if st == "UNDETERMINABLE":
            summary = ("The records for this account are incomplete (missing opening balance, a gap, or money from such an "
                       "account), so no figure is stated.")
        elif st == "DETERMINED":
            summary = f"At the reference time the balance is {inr(bal)}. Both methods agree: {inr(p)} is traceable to the fraud."
        else:
            summary = (f"At the reference time the balance is {inr(bal)}. Pro-rata says {inr(p)} is disputed money and FIFO says "
                       f"{inr(f)}, so the records support {inr(min(p, f))} to {inr(max(p, f))}. The rest of the balance is the "
                       f"holder's own money under both methods.")
    return {"account_id": account, "steps": steps, "summary": summary}
