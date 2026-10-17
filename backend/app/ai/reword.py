"""AF8: checked rewording of the account-holder explanation.

The template explanation (CF7) is always produced first and is complete on its
own. A model may reword it for readability. An automatic check then confirms
that every amount, date, time, account number and reference in the reworded text
appears in the template, and that none of the template's facts were dropped. On
any mismatch the template is used.
"""
from __future__ import annotations

import re

from app.ai.llm import chat_json

PROMPT_VERSION = "af8-v3"

_FACT_PATTERNS = [
    re.compile(r"₹\s?[\d,]+(?:\.\d+)?"),                       # amounts
    re.compile(r"\b\d{1,2}\s+[A-Z][a-z]{2,8}\s+\d{4}\b"),       # dates like 14 Aug 2026
    re.compile(r"\b\d{1,2}:\d{2}\b"),                           # times
    re.compile(r"\bAC\d{7}\b|\bT\d{10}\b"),                     # accounts, transactions
    re.compile(r"\b(?:NCRP|FIR|CR)-[\w-]+\b"),                  # references
    re.compile(r"\b\d+(?:\.\d+)?\s?%"),                         # percentages
]
_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def facts(text: str) -> set[str]:
    out = set()
    for p in _FACT_PATTERNS:
        for m in p.findall(text or ""):
            out.add(re.sub(r"\s+", "", m).replace("₹", "₹"))
    return out


def _numbers(text: str) -> set[str]:
    stripped = re.sub(r"(?m)^\s*\d{1,2}[.)]\s", " ", text)  # list markers are not facts
    for p in _FACT_PATTERNS:
        stripped = p.sub(" ", stripped)
    return {n.replace(",", "") for n in _NUMBER.findall(stripped)}


# Claims about the account holder that the template never makes; a rewording must not add them.
_CLAIMS = [r"from your account", r"you (?:sent|transferred|moved|withdrew|paid)", r"by you",
           r"your (?:involvement|role|participation)", r"you (?:are|were) (?:involved|responsible)",
           r"frozen", r"seized", r"confiscat"]


def check(template: str, reworded: str) -> dict:
    t_facts, r_facts = facts(template), facts(reworded)
    added = sorted(r_facts - t_facts)
    dropped = sorted(t_facts - r_facts)
    stray = sorted(_numbers(reworded) - _numbers(template))
    problems = []
    if added:
        problems.append("figures or references not in the original: " + ", ".join(added))
    if dropped:
        problems.append("facts left out: " + ", ".join(dropped))
    if stray:
        problems.append("numbers not in the original: " + ", ".join(stray))
    if re.search(r"\b(guilty|criminal|fraudster|mule|suspect|culprit|offender)\b", reworded, re.I) and not \
            re.search(r"\b(guilty|criminal|fraudster|mule|suspect|culprit|offender)\b", template, re.I):
        problems.append("accusatory wording")
    for pat in _CLAIMS:
        m = re.search(pat, reworded, re.I)
        if m and not re.search(pat, template, re.I):
            problems.append(f"adds a claim the original does not make: \"{m.group(0)}\"")
    if len(reworded) < 0.5 * len(template):
        problems.append("too short to carry the same information")
    return {"ok": not problems, "problems": problems, "facts_checked": len(t_facts)}


def reword(template: str, ref: str = "") -> dict:
    sys = ("You rewrite a letter to a bank account holder so it is easier to read. Keep it neutral and polite; make no "
           "accusation and give no legal advice. Keep every amount, date, time, account number and reference exactly as "
           "written, keep every fact, and add no new facts or figures. Do not say who sent money or from which account; "
           "keep the meaning of every sentence. Use paragraphs, not numbered lists. Return JSON {\"text\": \"...\"}.")
    res = chat_json("AF8", PROMPT_VERSION, [{"role": "system", "content": sys}, {"role": "user", "content": template}],
                    input_ref=ref, max_tokens=1800)
    reworded = str(res["data"].get("text", "")).strip()
    result = check(template, reworded)
    return {"template": template, "reworded": reworded, "check": result,
            "used": "AI" if result["ok"] else "TEMPLATE", "text": reworded if result["ok"] else template,
            "model": res["model"], "prompt_version": PROMPT_VERSION}
