"""AF7: governed questions over the results, through Exasol's MCP server.

1. The model picks a prepared, parameterised query (preferred) or drafts a
   SELECT over the TH_RESULTS views.
2. The SQL is checked: one SELECT, only TH_RESULTS views, a row limit.
3. It runs through Exasol's MCP server as the read-only user TH_ASK.
4. The model words a short answer from the rows; every number in that answer
   must appear in the rows, otherwise the wording is rejected and only the
   rows are shown. The SQL and the rows are always shown.
"""
from __future__ import annotations

import re
import time

from app import db
from app.ai.llm import chat_json, model, new_id
from app.ai.mcp_client import mcp

PROMPT_VERSION = "af7-v4"
R = "TH_RESULTS"
VIEWS = {
    "CASES": "one row per case: reported_loss, request_status, requested_total, supported_lower, supported_upper, whole_balance, unsupported_amount, n_exceeds, worst_classification, conservation_ok",
    "ACCOUNT_SIZING": "one row per case and account: layer, balance, retained_pr, retained_fifo, retained_lifo, supported_lower, supported_upper, share_lo, share_hi, status (DETERMINED, RANGE, UNDETERMINABLE, OUT_OF_SCOPE)",
    "REVIEW_FLAGS": "one row per requested hold: requested_scope, requested_amount, supported_lower, supported_upper, classification (WITHIN_EVIDENCE, WITHIN_RANGE, EXCEEDS_EVIDENCE, CANNOT_DETERMINE), ratio_to_upper, excess_over_upper, cases_through_account",
    "RESTRAINTS": "one row per existing hold: restraint_type, held_amount, start_date, closure_status, active (1/0), band (UNDER_50K/OVER_50K), days_held, days_since_update, supported_upper, over_hold_ratio, over_hold, closed_still_held, past_90_days, past_review_date, escalate (flags 1/0), priority",
    "REQUESTS": "one row per police request: request_status (COMPLETE, INCOMPLETE, CONFLICTING), n_missing, n_conflict",
}

TEMPLATES = [
    {"id": "old_overheld", "question": "Which active holds older than N days exceed their supported amount?",
     "params": {"days": ("int", 90, 0, 3650), "limit": ("int", 200, 1, 200)},
     "sql": "SELECT restraint_id, case_id, account_id, held_amount, supported_upper, over_hold_ratio, days_held\n"
            "FROM TH_RESULTS.RESTRAINTS\nWHERE active = 1 AND days_held > {days} AND over_hold = 1\n"
            "ORDER BY over_hold_ratio DESC LIMIT {limit}"},
    {"id": "closed_still_held", "question": "Which holds are still active although the case is closed or a clean chit was given?",
     "params": {"limit": ("int", 200, 1, 200)},
     "sql": "SELECT restraint_id, case_id, account_id, held_amount, closure_status, days_held\nFROM TH_RESULTS.RESTRAINTS\n"
            "WHERE closed_still_held = 1 ORDER BY held_amount DESC LIMIT {limit}"},
    {"id": "top_unsupported_cases", "question": "Which cases lock the most money the records do not support?",
     "params": {"limit": ("int", 10, 1, 200)},
     "sql": "SELECT case_ref, reported_loss, requested_total, supported_upper, unsupported_amount\nFROM TH_RESULTS.CASES\n"
            "ORDER BY unsupported_amount DESC LIMIT {limit}"},
    {"id": "portfolio_totals", "question": "Across all cases, how much was asked to be held versus supported?",
     "params": {},
     "sql": "SELECT COUNT(*) AS cases, SUM(reported_loss) AS reported_loss, SUM(requested_total) AS requested_total,\n"
            "       SUM(supported_upper) AS supported_upper, SUM(unsupported_amount) AS unsupported_amount\nFROM TH_RESULTS.CASES"},
    {"id": "requests_by_status", "question": "How many police requests are complete, incomplete or conflicting?",
     "params": {},
     "sql": "SELECT request_status, COUNT(*) AS requests\nFROM TH_RESULTS.REQUESTS\nGROUP BY request_status ORDER BY requests DESC"},
    {"id": "overbroad_ratio", "question": "Which requested holds are more than X times their supported upper bound?",
     "params": {"ratio": ("num", 5, 1, 1000), "limit": ("int", 200, 1, 200)},
     "sql": "SELECT case_ref, account_id, requested_amount, supported_upper, ratio_to_upper\nFROM TH_RESULTS.REVIEW_FLAGS\n"
            "WHERE ratio_to_upper > {ratio} ORDER BY ratio_to_upper DESC LIMIT {limit}"},
    {"id": "escalate", "question": "Which active holds have had no update from the police for 15 days or more?",
     "params": {"limit": ("int", 200, 1, 200)},
     "sql": "SELECT restraint_id, case_id, account_id, held_amount, days_since_update\nFROM TH_RESULTS.RESTRAINTS\n"
            "WHERE escalate = 1 ORDER BY days_since_update DESC LIMIT {limit}"},
    {"id": "small_past_90", "question": "Which holds under Rs 50,000 have passed the 90-day mark?",
     "params": {"limit": ("int", 200, 1, 200)},
     "sql": "SELECT restraint_id, case_id, account_id, held_amount, days_held\nFROM TH_RESULTS.RESTRAINTS\n"
            "WHERE past_90_days = 1 ORDER BY days_held DESC LIMIT {limit}"},
    {"id": "case_accounts", "question": "What does the analysis say for each account of case <case reference>?",
     "params": {"case_ref": ("ref", None, None, None)},
     "sql": "SELECT account_id, layer, balance, supported_lower, supported_upper, status\nFROM TH_RESULTS.ACCOUNT_SIZING\n"
            "WHERE case_ref = '{case_ref}' ORDER BY layer, account_id"},
    {"id": "account_cases", "question": "In which cases does account <account number> appear, and what is supported there?",
     "params": {"account_id": ("acct", None, None, None)},
     "sql": "SELECT case_ref, layer, balance, supported_lower, supported_upper, status\nFROM TH_RESULTS.ACCOUNT_SIZING\n"
            "WHERE account_id = '{account_id}' ORDER BY case_ref"},
    {"id": "status_counts", "question": "How many account figures are determined, a range, undeterminable or out of scope?",
     "params": {},
     "sql": "SELECT status, COUNT(*) AS accounts\nFROM TH_RESULTS.ACCOUNT_SIZING\nGROUP BY status ORDER BY accounts DESC"},
    {"id": "held_by_band", "question": "How much is held in active holds, below and above Rs 50,000?",
     "params": {},
     "sql": "SELECT band, COUNT(*) AS holds, SUM(held_amount) AS held_amount, SUM(over_hold) AS over_held\n"
            "FROM TH_RESULTS.RESTRAINTS\nWHERE active = 1 GROUP BY band ORDER BY band"},
]
TEMPLATE_BY_ID = {t["id"]: t for t in TEMPLATES}

FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE|ALTER|GRANT|REVOKE|TRUNCATE|IMPORT|EXPORT|EXECUTE|"
                       r"OPEN|CLOSE|COMMIT|ROLLBACK|KILL|FLUSH|RECOMPRESS|REORGANIZE|IMPERSONATE)\b", re.I)


class AskRejected(ValueError):
    pass


def fill_template(t: dict, params: dict) -> tuple[str, dict]:
    used = {}
    for name, (kind, default, lo, hi) in t["params"].items():
        v = params.get(name, default)
        if v is None:
            raise AskRejected(f"The question needs a value for '{name}'.")
        if kind in ("int", "num"):
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise AskRejected(f"'{name}' must be a number.")
            v = int(v) if kind == "int" else v
            if not (lo <= v <= hi):
                raise AskRejected(f"'{name}' must be between {lo} and {hi}.")
        elif kind == "ref":
            v = str(v).strip().upper()
            if not re.fullmatch(r"NCRP-\d{8,16}", v):
                raise AskRejected("A case reference looks like NCRP-32026081400001.")
        elif kind == "acct":
            v = str(v).strip().upper()
            if not re.fullmatch(r"AC\d{7}", v):
                raise AskRejected("An account number looks like AC0126507.")
        used[name] = v
    return t["sql"].format(**used), used


def check_sql(sql: str) -> str:
    """Only one SELECT over the TH_RESULTS views; adds a row limit."""
    s = sql.strip().rstrip(";").strip()
    if ";" in s:
        raise AskRejected("Only one statement is allowed.")
    if not re.match(r"(?is)^\s*(SELECT|WITH)\b", s):
        raise AskRejected("Only SELECT queries are allowed.")
    if FORBIDDEN.search(s):
        raise AskRejected("The query contains a statement that changes data.")
    refs = re.findall(r"(?i)\b(?:FROM|JOIN)\s+([A-Z_][\w.\"]*)", s)
    for ref in refs:
        name = ref.replace('"', "").upper()
        if name.startswith("("):
            continue
        parts = name.split(".")
        if len(parts) != 2 or parts[0] != R or parts[1] not in VIEWS:
            raise AskRejected(f"Only the results views {R}.{{{', '.join(VIEWS)}}} may be queried, not {name}.")
    if not refs:
        raise AskRejected("The query does not read any results view.")
    if not re.search(r"(?i)\bLIMIT\s+\d+", s):
        s += "\nLIMIT 200"
    return s


def _plan(question: str) -> dict:
    catalog = "\n".join(f"- {t['id']}: {t['question']} params: {', '.join(f'{k} ({v[0]}, default {v[1]})' for k, v in t['params'].items()) or 'none'}"
                        for t in TEMPLATES)
    views = "\n".join(f"- {R}.{k}: {v}" for k, v in VIEWS.items())
    sys = ("You turn questions about cyber-fraud account holds into a database query plan. Prefer a prepared query. "
           "Only if none fits, write one Exasol SELECT over the views listed (always schema-qualified, no other tables). "
           "If the question cannot be answered from these views (for example it asks for raw transactions, personal data, "
           "or a decision about guilt), refuse. Return JSON: {\"template_id\": \"...\", \"params\": {...}} or "
           "{\"sql\": \"...\"} or {\"refuse\": \"reason\"}.")
    msg = f"Prepared queries:\n{catalog}\n\nViews:\n{views}\n\nQuestion: {question}"
    return chat_json("AF7", PROMPT_VERSION, [{"role": "system", "content": sys}, {"role": "user", "content": msg}],
                     input_ref="plan", max_tokens=1200)


def _word(question: str, columns: list, rows: list) -> dict:
    sample = rows[:40]
    sys = ("You answer a question using ONLY the rows given. Write 1 to 3 plain sentences for a police or bank officer: "
           "say how many rows match (use the exact count given), then name the most important one to three items with "
           "their key figures. Money amounts are Indian rupees: write them with ₹ (never $); counts, days, ratios and IDs "
           "get no currency sign. Do not list every row (the officer sees the table). Use only numbers that appear in the "
           "rows or the count given; you may round to two decimals and add thousands separators. Do not calculate new "
           "figures, do not guess, and do not judge anyone's guilt. If there are no rows, say so. "
           "Return JSON {\"answer\": \"...\"}.")
    msg = (f"Question: {question}\nThe query returned exactly {len(rows)} row(s)"
           + (f"; only the first {len(sample)} are shown below" if len(rows) > len(sample) else "")
           + f".\nColumns: {columns}\nRows: {sample}")
    return chat_json("AF7", PROMPT_VERSION + "-answer", [{"role": "system", "content": sys}, {"role": "user", "content": msg}],
                     input_ref="answer", max_tokens=600)


_ID = re.compile(r"\b(?:NCRP-\d+|AC\d{7}|T\d{10}|R\d+)\b")
_NUM = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(\s?%)?")


def number_fidelity(answer: str, rows: list, extra: list[float]) -> dict:
    """Every number and identifier in the wording must come from the rows (or the question)."""
    cells = [str(c) for r in rows for c in r if c is not None]
    nums = set()
    for c in cells:
        try:
            f = float(str(c).replace(",", ""))
            nums |= {round(f, 2), round(f), round(f, 1)}
        except ValueError:
            pass
    nums |= {float(len(rows))} | {float(x) for x in extra}
    unsupported = []
    for ident in _ID.findall(answer):
        if not any(ident == c for c in cells):
            unsupported.append(ident)
    stripped = _ID.sub(" ", answer)
    for m in _NUM.finditer(stripped):
        raw, pct = m.group(1), m.group(2)
        try:
            v = float(raw.replace(",", ""))
        except ValueError:
            continue
        ok = any(abs(v - n) <= 0.011 for n in nums)
        if not ok and pct:
            ok = any(abs(v / 100 - n) <= 0.0011 for n in nums)
        if not ok:
            unsupported.append(raw + (pct or ""))
    if re.search(r"[$€£]|USD|dollars?", answer, re.I):
        unsupported.append("a currency other than rupees")
    return {"ok": not unsupported, "unsupported": unsupported}


def ask(question: str) -> dict:
    question = (question or "").strip()
    if not 3 <= len(question) <= 500:
        raise AskRejected("Ask a question of 3 to 500 characters.")
    t0 = time.perf_counter()
    plan = _plan(question)["data"]
    mode, template_id, params = None, None, {}
    if plan.get("refuse"):
        out = {"question": question, "mode": "REFUSED", "answer": f"Not answered: {plan['refuse']}", "sql": None,
               "columns": [], "rows": [], "row_count": 0, "fidelity": {"ok": True, "unsupported": []}}
        _log(out, t0)
        return out
    if plan.get("template_id") in TEMPLATE_BY_ID:
        mode, template_id = "TEMPLATE", plan["template_id"]
        sql, params = fill_template(TEMPLATE_BY_ID[template_id], plan.get("params") or {})
    elif plan.get("sql"):
        mode, sql = "SQL", plan["sql"]
    else:
        raise AskRejected("The question could not be turned into a query. Try one of the suggested questions.")
    sql = check_sql(sql)
    res = mcp.query(sql, row_limit=200)
    columns, rows = res["columns"], res["rows"]
    extra = [float(v) for v in params.values() if isinstance(v, (int, float))]
    extra += [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", question)]
    worded = _word(question, columns, rows)["data"].get("answer", "")
    fid = number_fidelity(worded, rows, extra)
    answer = worded if fid["ok"] else f"{len(rows)} row(s) returned. The AI's wording was not used because it contained figures that are not in the rows."
    out = {"question": question, "mode": mode, "template_id": template_id, "params": params, "sql": sql,
           "columns": columns, "rows": rows, "row_count": len(rows), "answer": answer, "ai_wording": worded,
           "fidelity": fid, "via": f"Exasol MCP server ({mcp.status()['package']}), tool execute_exasol_query, read-only user {mcp.status()['user']}",
           "model": model()}
    _log(out, t0)
    return out


def _log(out: dict, t0: float):
    out["ms"] = round((time.perf_counter() - t0) * 1000)
    try:
        c = db.connect()
        try:
            c.execute(f"""INSERT INTO {db.SCHEMA}.ASK_LOG VALUES ({{i}}, {{q}}, {{m}}, {{t}}, {{s}}, {{n}}, {{a}}, {{f}},
                          {{mdl}}, {{ms}}, CURRENT_TIMESTAMP)""",
                      {"i": new_id(), "q": out["question"][:2000], "m": out["mode"], "t": out.get("template_id"),
                       "s": (out.get("sql") or "")[:20000] or None, "n": out.get("row_count", 0),
                       "a": out["answer"][:20000], "f": out["fidelity"]["ok"], "mdl": model(), "ms": out["ms"]})
            c.commit()
        finally:
            c.close()
    except Exception:
        pass
