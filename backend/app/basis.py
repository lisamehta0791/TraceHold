"""What a result is based on: the rules applied, the SQL scripts that ran in
Exasol (with their real text), and the per-step log of the analysis run."""
from __future__ import annotations

from app import db
from app.engine import Config, step_file

# What each script does, in one line.
SCRIPTS = {
    "10_prepare.sql": "Cleans every posting (duplicates, reversals, clock skew) and rebuilds each account's running balance.",
    "11_case_ref.sql": "Picks the cases to analyse and fixes each case's reference time.",
    "20_trace_seed.sql": "Starts each trail at the victim's disputed transfer(s).",
    "21_trace_step.sql": "Follows the money one hop further, for all cases at once, under pro-rata, FIFO and LIFO. Repeated until nothing changes.",
    "22_trace_swap.sql": "Makes the latest pass the current state before the next pass.",
    "30_trail.sql": "Writes the trail: every transfer that carried disputed money and how much.",
    "31_taint_step.sql": "Marks accounts whose figures depend on missing or ambiguous records. Repeated until nothing changes.",
    "32_sizing.sql": "Sizes each account (retained disputed money, supported range, share, status) and checks conservation.",
    "40_requests.sql": "Checks each police request for missing items and for conflicts with the records.",
    "50_review.sql": "Compares each requested hold with the supported range and computes layer dilution.",
    "60_additional.sql": "Ranks existing holds for review and measures how fast money moved.",
    "70_evidence.sql": "Links every figure to the transactions it rests on (evidence packet).",
    "80_summary.sql": "Summarises each case.",
}


TITLES = {
    "10_prepare.sql": "Clean postings and rebuild balances", "11_case_ref.sql": "Choose cases and reference times",
    "20_trace_seed.sql": "Start at the victim's transfer", "21_trace_step.sql": "Follow the money one hop further",
    "30_trail.sql": "Write the money trail", "31_taint_step.sql": "Flag figures that rest on missing records",
    "32_sizing.sql": "Size every account and check conservation", "40_requests.sql": "Check the police request",
    "50_review.sql": "Compare each requested hold with the evidence", "60_additional.sql": "Rank existing holds, measure speed",
    "70_evidence.sql": "Link every figure to its transactions", "80_summary.sql": "Summarise each case",
}


def rules(cfg: dict | None = None) -> list[dict]:
    c = {**Config().__dict__, **(cfg or {})}
    ref = {"REQUEST": "when the police request was received", "ANALYSIS": "the latest transaction in the data",
           "FIXED": "a fixed time"}.get(c["ref_rule"], c["ref_rule"])
    return [
        {"rule": "Counting methods", "value": "Pro-rata and FIFO (LIFO as a bounding case)",
         "why": "Mixed money carries no label, so two disclosed methods give a range instead of one guessed number."},
        {"rule": "Reference time", "value": ref, "why": "Balances and holdings are measured at this moment."},
        {"rule": "Smallest amount followed", "value": f"₹{c['dust']:g}", "why": "Fractions below this are recorded as untraced instead of being followed further."},
        {"rule": "Duplicate posting window", "value": f"{c['dup_window_s'] // 60} minutes", "why": "The same transfer posted twice within this window is counted once."},
        {"rule": "Clock-skew tolerance", "value": f"{c['skew_tol_s'] // 60} minutes", "why": "A credit stamped slightly before its debit (bank clocks differ) is put back in order."},
        {"rule": "Stop condition", "value": f"repeat until nothing changes (at most {c['max_iter']} passes)", "why": "Each pass follows the money one hop further."},
        {"rule": "Conservation", "value": "retained + left + untraced + absorbed = loss", "why": "Checked for every case and method; a result that does not balance is flagged."},
    ]


def script_text(name: str, schema: str) -> str:
    if name not in SCRIPTS:
        raise KeyError(name)
    params = Config().sql_params(schema)
    params["MISSING_SQL"] = "/* one SELECT per required item in CHECKLIST_ITEMS, joined with UNION ALL */ SELECT 1 FROM DUAL WHERE 1 = 0"
    return db.render((db.SQL_DIR / name).read_text(encoding="utf-8"), **params)


def group_steps(steps: list[dict]) -> list[dict]:
    """Collapse repeated passes ('layer pass 1..n') into one entry with the per-pass rows."""
    out: list[dict] = []
    for s in steps:
        label = s["step"].split(" (longest")[0]
        file = s.get("file") or step_file(label)
        base = label.rsplit(" pass ", 1)[0] if " pass " in label else None
        if base and out and out[-1].get("base") == base:
            g = out[-1]
            g["passes"] += 1
            g["ms"] += s["ms"]
            g["pass_rows"].append(s.get("rows"))
            continue
        out.append({"step": TITLES.get(file or "", base or label), "base": base, "file": file, "ms": s["ms"], "rows": s.get("rows"),
                    "passes": 1 if base else None, "pass_rows": [s.get("rows")] if base else None,
                    "purpose": SCRIPTS.get(file or "", "")})
    for g in out:
        g.pop("base", None)
        g["ms"] = round(g["ms"], 1)
    return out
