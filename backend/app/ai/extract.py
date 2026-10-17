"""CF9: AI-assisted request extraction with deterministic checks after the model.

The model returns, for each checklist field, the value(s) it found and the exact
text each came from. Rule checks then decide what can be used:

1. the quoted text must appear in the letter, character for character;
2. the value must follow from the quoted text (amounts are re-read from the
   quote, e.g. "ek lakh bees hazaar" = 120000);
3. the value must have a valid format;
4. the value is cross-checked against the transaction records.

A field that fails any check is UNVERIFIED and is never used. Two different
values for one field is a CONFLICT and is never resolved silently. A person
confirms every field before the request goes into the analysis.
"""
from __future__ import annotations

import re

from app import db
from app.ai.llm import chat_json, new_id
from app.textnum import ACCOUNT_RE, TXN_RE, amounts_in, norm_text, norm_ws, parse_amount

PROMPT_VERSION = "cf9-v4"

FIELDS = [
    ("officer", "Issuing officer's name (a person's name only)"),
    ("designation", "Officer's designation or rank, e.g. Inspector of Police"),
    ("agency", "Police station or agency name, e.g. Cyber Crime Police Station, Jaipur"),
    ("contact", "Agency contact details: email and/or phone, exactly as written"),
    ("case_reference", "FIR / crime / NCRP / CFCFRMS complaint reference number"),
    ("legal_provision", "All legal provisions invoked, as ONE finding whose span covers the whole list, e.g. Section 106 BNSS 2023; Section 318 BNS"),
    ("quoted_txn", "Transaction ID of the disputed transfer (e.g. T0001578390), if one is quoted"),
    ("stated_amount", "The disputed amount (NOT a total loss across all modes); value as a plain number like 104269.06"),
    ("action_type", "Action asked for: TOTAL_FREEZE (freeze account fully), DEBIT_FREEZE (stop debits) or LIEN_AMOUNT (mark a lien / hold an amount)"),
    ("targets", "Every account the action applies to; value is the account identifier only (e.g. AC0126507 or A)"),
]
FIELD_NAMES = [f for f, _ in FIELDS]

SYSTEM = """You extract fields from police requests to banks about cyber fraud. Letters may mix English, romanised Hindi and Devanagari, use abbreviations, and contain typing errors.
Rules:
- For each field return a list of findings. Each finding has "value" and "span".
- "span" must be copied EXACTLY, character for character, from the letter: the shortest piece of text that states the value.
- Never infer, guess or complete a value that is not written. If a field is not stated, return an empty list.
- If the letter states one field with two different values (for example an amount in digits and a different amount in words), return both findings, each with its own span.
- For stated_amount, include the words in the span if they are written next to the digits.
- For targets return one finding per account.
Return only JSON: {"fields": {"<field>": [{"value": "...", "span": "..."}]}}"""


def _prompt(text: str) -> list[dict]:
    spec = "\n".join(f"- {f}: {d}" for f, d in FIELDS)
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Fields:\n{spec}\n\nLetter:\n<<<\n{text}\n>>>"}]


ACTION_WORDS = {
    "LIEN_AMOUNT": ("lien", "hold the amount", "hold an amount"),
    "DEBIT_FREEZE": ("debit",),
    "TOTAL_FREEZE": ("freeze", "freez", "band kar", "फ्रीज़", "फ्रीज"),
}
LAW_WORDS = ("section", "u/s", "bnss", "bns", "it act", "धारा", "ipc")


def _find_span(text: str, span: str) -> tuple[int, int]:
    if not span:
        return -1, -1
    # prefer a whole-word match, so account "A" is not found inside "Adhikari"
    m = re.search(rf"(?<![\w/]){re.escape(span)}(?![\w/])", text)
    if m:
        return m.start(), m.end()
    i = text.find(span)
    if i >= 0:
        return i, i + len(span)
    # tolerate whitespace differences only (line breaks inside the quote)
    pat = r"\s+".join(re.escape(p) for p in span.split())
    m = re.search(pat, text) if pat else None
    return (m.start(), m.end()) if m else (-1, -1)


def _neighbour_words(text: str, end: int) -> str:
    """An amount written in words right after the quoted digits, e.g. "Rs 50,000/- (Rupees Forty Thousand only)"."""
    if end < 0:
        return ""
    m = re.match(r"\s*(?:/-)?\s*\(([^)]{3,160})\)", text[end:end + 190])
    return m.group(1) if m else ""


def _check_value(field: str, value: str, span: str, ctx: dict) -> tuple[object, list[dict]]:
    """Returns (normalised value or None, list of checks)."""
    checks = []
    v = norm_ws(str(value or ""))
    sp = norm_ws(span or "")

    def add(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    if field == "stated_amount":
        figures = sorted(set(amounts_in(sp)))
        # digits and words for the same amount ("Rs 2,00,000/- (do lakh rupaye)") are one figure
        from_span = figures[0] if len(figures) == 1 else (parse_amount(sp) if not figures else None)
        own = amounts_in(v)
        num = own[0] if own else parse_amount(v)
        add("value follows from the quote", from_span is not None and num is not None and abs(from_span - num) < 0.005
            or (len(figures) > 1 and num in figures),
            f"quote reads as {from_span:,.2f}" if from_span is not None
            else ("the quote holds more than one amount" if len(figures) > 1 else "no amount in the quote"))
        if len(figures) > 1:
            add("one amount in the quote", False, f"the quote states {len(figures)} different amounts: "
                + ", ".join(f"{x:,.2f}" for x in figures))
        add("format", num is not None and num > 0, "a positive amount")
        words = ctx.get("_neighbour")
        if words and parse_amount(words) is not None and num is not None and len(figures) <= 1:
            w = parse_amount(words)
            add("one amount in the quote", abs(w - num) < 0.005,
                f"the words next to it read {w:,.2f}" if abs(w - num) >= 0.005 else "")
        if ctx.get("txn_amount") is not None and num is not None:
            add("matches the records", abs(ctx["txn_amount"] - num) < 0.005,
                f"the quoted transaction is for {ctx['txn_amount']:,.2f}")
        if ctx.get("victim_amounts") and num is not None:
            add("matches the records", any(abs(a - num) < 0.005 for a in ctx["victim_amounts"]),
                "the victim's transfers total " + ", ".join(f"{a:,.2f}" for a in ctx["victim_amounts"]))
        return num, checks
    if field == "action_type":
        enum = v.upper().replace(" ", "_")
        low = sp.lower()
        ok_fmt = enum in ACTION_WORDS
        add("format", ok_fmt, "one of TOTAL_FREEZE, DEBIT_FREEZE, LIEN_AMOUNT")
        if ok_fmt:
            # the most specific action word in the quote decides
            found = next((a for a in ("LIEN_AMOUNT", "DEBIT_FREEZE", "TOTAL_FREEZE")
                          if any(w in low for w in ACTION_WORDS[a])), None)
            add("value follows from the quote", found == enum, f"the quote says {found or 'no action word'}")
        return (enum if ok_fmt else None), checks
    if field == "targets":
        acc = v.upper().replace("A/C", "").strip(" .:")
        acc = acc.split()[-1] if acc else acc
        in_span = acc and acc.lower() in sp.lower()
        add("value follows from the quote", in_span, "")
        known = ctx.get("accounts")
        fmt = bool(ACCOUNT_RE.fullmatch(acc)) or (known is not None and acc in known)
        add("format", fmt, "an account number like AC0126507" + (" or an account of this case" if known else ""))
        if ctx.get("existing_accounts") is not None:
            add("matches the records", acc in ctx["existing_accounts"], "account exists in the records")
        return (acc if acc else None), checks
    # text fields
    add("value follows from the quote", bool(v) and norm_text(v) in norm_text(sp), "")
    if field == "quoted_txn":
        add("format", bool(TXN_RE.fullmatch(v)), "a transaction ID like T0001578390")
        if "txn_exists" in ctx:
            add("matches the records", ctx["txn_exists"], "transaction found in the records")
    elif field == "case_reference":
        add("format", bool(re.search(r"\d{4,}", v)), "contains a reference number")
    elif field == "contact":
        add("format", bool(re.search(r"@|\+?\d[\d -]{7,}", v)), "an email address or phone number")
    elif field == "legal_provision":
        add("format", any(w in v.lower() for w in LAW_WORDS), "names a section or act")
    elif field == "officer":
        add("format", bool(re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,60}", v)), "a person's name")
    else:
        add("format", 1 < len(v) < 200, "")
    return v, checks


def _context(conn, ctx_in: dict | None, quoted_txn: str | None) -> dict:
    ctx: dict = {}
    if not ctx_in:
        return ctx
    if ctx_in.get("accounts") is not None:  # live analysis: the case typed in by the user
        ctx["accounts"] = [a.upper() for a in ctx_in["accounts"]]
        ctx["existing_accounts"] = ctx["accounts"]
        va = [float(t["amount"]) for t in ctx_in.get("transfers", []) if t.get("from") == "VICTIM"]
        if va:
            ctx["victim_amounts"] = sorted({sum(va), *va})
    if ctx_in.get("case_id") and conn is not None:  # stored case: check against the transaction records
        S = db.SCHEMA
        if quoted_txn:
            row = conn.execute(f"SELECT amount FROM {S}.TRANSACTIONS WHERE txn_id = {{t}} LIMIT 1", {"t": quoted_txn}).fetchone()
            ctx["txn_exists"] = row is not None
            if row:
                ctx["txn_amount"] = float(list(row.values())[0] if isinstance(row, dict) else row[0])
        ctx["existing_accounts"] = None  # filled lazily per target below
    return ctx


def extract(text: str, context: dict | None = None, doc_id: int | None = None, store: bool = True) -> dict:
    text = (text or "").strip()
    if len(text) < 20:
        raise ValueError("The letter is too short to read.")
    if len(text) > 12000:
        raise ValueError("The letter is too long (more than 12,000 characters).")
    res = chat_json("CF9", PROMPT_VERSION, _prompt(text), input_ref=f"doc:{doc_id}" if doc_id else "pasted letter",
                    max_tokens=2500)
    raw = res["data"].get("fields", {}) if isinstance(res["data"], dict) else {}

    conn = db.connect() if (store or (context or {}).get("case_id")) else None
    try:
        first_txn = next((norm_ws(str(f.get("value", ""))) for f in raw.get("quoted_txn", []) or [] if isinstance(f, dict)), None)
        ctx = _context(conn, context, first_txn)
        out_fields = []
        for name in FIELD_NAMES:
            findings = [f for f in (raw.get(name) or []) if isinstance(f, dict)]
            items = []
            for f in findings:
                value, span = f.get("value", ""), str(f.get("span", "") or "")
                start, end = _find_span(text, span)
                fctx = dict(ctx)
                if name == "targets" and (context or {}).get("case_id") and conn is not None:
                    acc = norm_ws(str(value)).upper()
                    fctx["existing_accounts"] = [acc] if conn.execute(
                        f"SELECT 1 FROM {db.SCHEMA}.ACCOUNTS WHERE account_id = {{a}}", {"a": acc}).fetchone() else []
                if name == "stated_amount":
                    fctx["_neighbour"] = _neighbour_words(text, end)
                norm, checks = _check_value(name, value, span, fctx)
                checks.insert(0, {"check": "quote appears in the letter", "ok": start >= 0,
                                  "detail": "" if start >= 0 else "the quoted text is not in the letter"})
                ok = all(c["ok"] for c in checks if c["check"] != "matches the records")
                items.append({"value": norm, "raw_value": str(value), "span": span, "start": start, "end": end,
                              "checks": checks, "verified": ok,
                              "records_ok": all(c["ok"] for c in checks if c["check"] == "matches the records")})
            out_fields.append(_field_status(name, items))
        extraction_id = new_id()
        if store and conn is not None:
            _store(conn, extraction_id, doc_id, out_fields, res["model"])
        return {"extraction_id": extraction_id, "model": res["model"], "prompt_version": PROMPT_VERSION,
                "ms": res["ms"], "fields": out_fields, "text": text}
    finally:
        if conn is not None:
            conn.close()


def _field_status(name: str, items: list[dict]) -> dict:
    label = dict(FIELDS)[name]
    if not items:
        return {"field": name, "label": label, "status": "NOT_STATED", "value": None, "items": [],
                "reasons": ["Not stated in the letter."]}
    verified = [i for i in items if i["verified"]]
    reasons = []
    if name == "targets":
        accs = sorted({i["value"] for i in verified if i["value"]})
        bad = [i for i in items if not i["verified"]]
        status = "VERIFIED" if verified and not bad else ("UNVERIFIED" if not verified else "PARTLY")
        if bad:
            reasons.append(f"{len(bad)} account(s) failed the checks and are not used.")
        return {"field": name, "label": label, "status": status, "value": accs, "items": items, "reasons": reasons}
    if name == "legal_provision" and len(items) > 1 and all(i["verified"] for i in items):
        parts = sorted(items, key=lambda i: i["start"])
        joined = "; ".join(dict.fromkeys(str(i["value"]) for i in parts))
        return {"field": name, "label": label, "status": "VERIFIED", "value": joined, "items": items,
                "reasons": ["Several provisions; joined in the order written."]}
    distinct = {round(i["value"], 2) if isinstance(i["value"], float) else norm_text(str(i["value"])) for i in items if i["value"] is not None}
    multi_in_span = any(any(c["check"] == "one amount in the quote" and not c["ok"] for c in i["checks"]) for i in items)
    if len(distinct) > 1 or multi_in_span:
        return {"field": name, "label": label, "status": "CONFLICT", "value": None, "items": items,
                "reasons": ["The letter states different values for this field. It is flagged and not resolved."]}
    if not verified:
        failed = sorted({c["check"] for i in items for c in i["checks"] if not c["ok"] and c["check"] != "matches the records"})
        return {"field": name, "label": label, "status": "UNVERIFIED", "value": None, "items": items,
                "reasons": [f"Failed: {', '.join(failed)}. Not used."]}
    it = verified[0]
    if not it["records_ok"]:
        reasons.append("Read correctly, but it does not match the transaction records: the request check will flag it.")
    return {"field": name, "label": label, "status": "VERIFIED", "value": it["value"], "items": items, "reasons": reasons}


def _store(conn, extraction_id, doc_id, fields, mdl):
    rows = []
    for f in fields:
        if not f["items"]:
            rows.append((extraction_id, doc_id, f["field"], None, None, None, None, f["status"], "; ".join(f["reasons"])[:2000], mdl, PROMPT_VERSION))
        for i in f["items"]:
            rows.append((extraction_id, doc_id, f["field"], str(i["value"])[:2000] if i["value"] is not None else None,
                         i["span"][:2000], i["start"], i["end"], f["status"] if f["field"] != "targets" else ("VERIFIED" if i["verified"] else "UNVERIFIED"),
                         "; ".join(c["check"] for c in i["checks"] if not c["ok"])[:2000], mdl, PROMPT_VERSION))
    for r in rows:
        conn.execute(f"""INSERT INTO {db.AUDIT_SCHEMA}.EXTRACTION_RESULTS VALUES ({{a}}, {{b}}, {{c}}, {{d}}, {{e}}, {{f}}, {{g}},
                         {{h}}, {{i}}, {{j}}, {{k}}, CURRENT_TIMESTAMP)""",
                     dict(zip("abcdefghijk", r)))
    conn.commit()


def confirm(extraction_id: int, fields: dict, confirmed_by: str) -> dict:
    """Stores the person's confirmation (and corrections) of every field."""
    conn = db.connect()
    try:
        stored = {}
        for r in conn.execute(f"SELECT field_name, value_text, status FROM {db.AUDIT_SCHEMA}.EXTRACTION_RESULTS "
                              f"WHERE extraction_id = {{e}}", {"e": extraction_id}).fetchall():
            r = {k.lower(): v for k, v in r.items()}
            stored.setdefault(r["field_name"], []).append(r)
        if not stored:
            raise ValueError("Unknown extraction")
        n_corr = 0
        for name, value in fields.items():
            if name not in FIELD_NAMES:
                continue
            vals = [s["value_text"] for s in stored.get(name, []) if s["status"] == "VERIFIED" and s["value_text"]]
            given = ";".join(sorted(value)) if isinstance(value, list) else ("" if value is None else str(value))
            before = ";".join(sorted(vals)) if name == "targets" else (vals[0] if vals else "")
            corrected = norm_text(given) != norm_text(before) and not (
                name == "stated_amount" and parse_amount(given) is not None and before and parse_amount(before) == parse_amount(given))
            n_corr += corrected
            conn.execute(f"""INSERT INTO {db.AUDIT_SCHEMA}.EXTRACTION_CONFIRMATIONS VALUES ({{e}}, {{f}}, {{v}}, {{c}}, {{b}},
                             CURRENT_TIMESTAMP)""", {"e": extraction_id, "f": name, "v": given[:2000] or None,
                                                     "c": corrected, "b": (confirmed_by or "reviewer")[:100]})
        conn.commit()
        return {"extraction_id": extraction_id, "confirmed": len(fields), "corrected": n_corr}
    finally:
        conn.close()
