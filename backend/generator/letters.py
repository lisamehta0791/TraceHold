"""Synthetic free-text police letters for CF9 (AI-assisted request extraction).

Each letter is rendered from a structured request (stored dataset or a live-
analysis demo) with controlled noise: four writing styles (formal English,
romanised Hinglish, English with Devanagari lines, terse message), typing
errors in filler words, abbreviations, amounts in words, a distracting second
amount, and sometimes digits and words that disagree (a planted conflict).

The true field values go to a separate answer-key file that the extraction
never reads.

    python backend/generator/letters.py data/L --dev 24 --heldout 60
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.textnum import english_words, hindi_words, inr_digits  # noqa: E402

FIELDS = ["officer", "designation", "agency", "contact", "case_reference", "legal_provision",
          "quoted_txn", "stated_amount", "action_type", "targets"]
STYLES = ["FORMAL_EN", "HINGLISH", "DEVA_MIX", "CRYPTIC"]

TYPO_WORDS = {"request": "reqeust", "account": "acount", "immediately": "immediatly", "received": "recieved",
              "transaction": "transcation", "necessary": "neccessary", "freeze": "freez", "please": "pls"}

ACTION_TEXT = {
    "FORMAL_EN": {"TOTAL_FREEZE": "You are requested to freeze the following account(s) completely",
                  "DEBIT_FREEZE": "You are requested to impose a debit freeze (stop all debits) on the following account(s)",
                  "LIEN_AMOUNT": "You are requested to mark a lien for the disputed amount on the following account(s)"},
    "HINGLISH": {"TOTAL_FREEZE": "Kripya neeche diye gaye account ko poori tarah freeze karein",
                 "DEBIT_FREEZE": "Kripya neeche diye gaye account par debit freeze lagaayen, koi debit na ho",
                 "LIEN_AMOUNT": "Kripya neeche diye gaye account par vivadit raashi ka lien mark karein"},
    "DEVA_MIX": {"TOTAL_FREEZE": "कृपया निम्न खाते को पूर्ण रूप से freeze करें",
                 "DEBIT_FREEZE": "कृपया निम्न खाते पर debit freeze लगाएँ",
                 "LIEN_AMOUNT": "कृपया निम्न खाते पर विवादित राशि का lien mark करें"},
    "CRYPTIC": {"TOTAL_FREEZE": "pls FREEZE", "DEBIT_FREEZE": "pls DEBIT FREEZE", "LIEN_AMOUNT": "pls mark LIEN on"},
}


def _amount_text(amount: float, style: str, rng: random.Random, conflict: bool) -> str:
    digits = inr_digits(amount)
    if conflict:
        # digits and words disagree: a planted conflict that must never be resolved silently
        other = round(amount * rng.choice([0.9, 1.1, 0.5, 2.0]), 2)
        return f"Rs. {digits}/- ({english_words(other)})"
    roll = rng.random()
    if style == "HINGLISH" and (hw := hindi_words(amount, "roman")) and roll < 0.7:
        return f"Rs {digits}/- ({hw})"
    if style == "DEVA_MIX" and (hw := hindi_words(amount, "deva")) and roll < 0.7:
        return f"₹{digits} ({hw})"
    if style == "CRYPTIC":
        return rng.choice([f"Rs{digits}", f"INR {amount:.2f}", f"₹{digits}"])
    if roll < 0.45:
        return f"Rs. {digits}/- ({english_words(amount)})"
    return rng.choice([f"Rs. {digits}/-", f"₹{digits}", f"INR {amount:.2f}"])


def _typos(text: str, rng: random.Random, rate: float) -> str:
    for w, t in TYPO_WORDS.items():
        if rng.random() < rate:
            text = text.replace(f" {w} ", f" {t} ", 1)
    return text


def _abbrev(s: str, rng: random.Random) -> str:
    if rng.random() < 0.5:
        s = s.replace("Police Station", "PS")
    return s


def render(req: dict, targets: list[dict], rng: random.Random, style: str | None = None,
           account_label=lambda a: a) -> tuple[str, dict, dict]:
    """Returns (letter text, true field values, noise settings)."""
    style = style or rng.choice(STYLES)
    conflict = req.get("stated_amount") not in (None, "") and rng.random() < 0.08
    distractor = rng.random() < 0.25
    noise = {"style": style, "conflict": conflict, "distractor": distractor, "typo_rate": 0.0}

    officer, desig = req.get("officer") or "", req.get("designation") or ""
    agency, contact = req.get("agency") or "", req.get("contact") or ""
    ref, law = req.get("case_reference") or "", req.get("legal_provision") or ""
    txn, action = req.get("quoted_txn") or "", req.get("action_type") or ""
    amt = req.get("stated_amount")
    amt = float(amt) if amt not in (None, "") else None
    accs = [account_label(t["account"]) for t in targets]

    lines: list[str] = []
    if style == "FORMAL_EN":
        lines += ["To,", "The Nodal Officer,", "Concerned Bank", ""]
        lines.append(f"Subject: Request for action on account(s) in cyber fraud complaint"
                     + (f" {ref}" if ref else ""))
        lines.append("")
        lines.append("Sir/Madam,")
        body = "With reference to the above, it is stated that a complaint of online financial fraud has been received at this office."
        if txn:
            body += f" The victim's money was transferred through transaction ID {txn}"
            body += f" for an amount of {_amount_text(amt, style, rng, conflict)}." if amt else "."
        elif amt:
            body += f" The disputed amount is {_amount_text(amt, style, rng, conflict)}."
        if distractor and amt:
            body += f" The total loss reported by the complainant across all modes is Rs. {inr_digits(round(amt * rng.choice([1.5, 2, 3]), 2))}/-."
        lines.append(body)
        if law:
            lines.append(f"This request is made under {law}.")
        if action:
            lines.append(f"{ACTION_TEXT[style][action]}: {', '.join(accs)}.")
        else:
            lines.append(f"The following account(s) are involved: {', '.join(accs)}.")
        lines += ["", "Yours faithfully,"]
        if officer:
            lines.append(officer)
        if desig:
            lines.append(desig)
        if agency:
            lines.append(_abbrev(agency, rng))
        if contact:
            lines.append(f"Contact: {contact}")
        noise["typo_rate"] = 0.15
    elif style == "HINGLISH":
        lines.append("Sewa mein, Nodal Adhikari ji,")
        lines.append("")
        parts = ["Online fraud ki shikayat prapt hui hai"]
        if ref:
            parts.append(f"(shikayat sankhya {ref})")
        lines.append(" ".join(parts) + ".")
        if amt:
            lines.append(f"Vivadit raashi {_amount_text(amt, style, rng, conflict)} hai"
                         + (f", txn id {txn}" if txn else "") + ".")
        elif txn:
            lines.append(f"Txn id {txn} hai.")
        if distractor and amt:
            lines.append(f"Peedit ka kul nuksaan lagbhag Rs {inr_digits(round(amt * rng.choice([1.5, 2]), 2))} bataya gaya hai.")
        if law:
            lines.append(f"Yeh anurodh {law} ke antargat hai.")
        if action:
            lines.append(f"{ACTION_TEXT[style][action]}: {', '.join(accs)}.")
        else:
            lines.append(f"Sambandhit khate: {', '.join(accs)}.")
        lines.append("")
        sign = [x for x in (officer, desig, _abbrev(agency, rng)) if x]
        if sign:
            lines.append("Bhavdiya, " + ", ".join(sign))
        if contact:
            lines.append(f"Sampark: {contact}")
        noise["typo_rate"] = 0.1
    elif style == "DEVA_MIX":
        lines.append("सेवा में, नोडल अधिकारी,")
        lines.append("")
        lines.append("विषय: साइबर धोखाधड़ी शिकायत के संबंध में" + (f" (Ref: {ref})" if ref else ""))
        if amt:
            lines.append(f"विवादित राशि {_amount_text(amt, style, rng, conflict)} है।" + (f" Transaction ID: {txn}." if txn else ""))
        elif txn:
            lines.append(f"Transaction ID: {txn}.")
        if distractor and amt:
            lines.append(f"शिकायतकर्ता की कुल हानि ₹{inr_digits(round(amt * 2, 2))} बताई गई है।")
        if law:
            lines.append(f"यह अनुरोध {law} के अंतर्गत है।")
        if action:
            lines.append(f"{ACTION_TEXT[style][action]}: {', '.join(accs)}।")
        else:
            lines.append(f"संबंधित खाते: {', '.join(accs)}।")
        lines.append("")
        for x in (officer, desig, _abbrev(agency, rng)):
            if x:
                lines.append(x)
        if contact:
            lines.append(f"संपर्क: {contact}")
    else:  # CRYPTIC
        bits = []
        if ref:
            bits.append(f"Ref {ref}")
        if txn:
            bits.append(f"txn {txn}")
        if amt:
            bits.append(f"amt {_amount_text(amt, style, rng, conflict)}")
        if distractor and amt:
            bits.append(f"tot loss {inr_digits(round(amt * 2, 2))}")
        if law:
            bits.append(f"u/s {law}")
        head = "URGENT. " + " | ".join(bits) + "."
        lines.append(head)
        if action:
            lines.append(f"{ACTION_TEXT[style][action]} {' & '.join(accs)} immediately.")
        else:
            lines.append(f"a/c {' & '.join(accs)}.")
        sign = [x for x in (officer, desig, _abbrev(agency, rng)) if x]
        if sign:
            lines.append("- " + ", ".join(sign))
        if contact:
            lines.append(contact)

    text = "\n".join(lines)
    if noise["typo_rate"]:
        text = _typos(text, rng, noise["typo_rate"])
    truth = {
        "officer": officer, "designation": desig, "agency": agency, "contact": contact,
        "case_reference": ref, "legal_provision": law, "quoted_txn": txn,
        "stated_amount": "CONFLICT" if conflict else ("" if amt is None else f"{amt:.2f}"),
        "action_type": action, "targets": ";".join(sorted(t["account"] for t in targets)),
    }
    return text, truth, noise


# ---------------------------------------------------------------- stored dataset
def build(data_dir: Path, dev: int, heldout: int, seed: int = 2026):
    reqs = list(csv.DictReader(open(data_dir / "requests.csv", encoding="utf-8")))
    tgts: dict[str, list[dict]] = {}
    for t in csv.DictReader(open(data_dir / "request_targets.csv", encoding="utf-8")):
        tgts.setdefault(t["request_id"], []).append({"account": t["account_id"]})
    rng = random.Random(seed)
    picked = rng.sample([r for r in reqs if tgts.get(r["request_id"])], dev + heldout)
    docs, truth_rows = [], []
    for i, r in enumerate(picked, 1):
        req = {"officer": r["issuing_officer"], "designation": r["designation"], "agency": r["agency"],
               "contact": r["agency_contact"], "case_reference": r["case_reference"],
               "legal_provision": r["legal_provision"], "quoted_txn": r["quoted_txn_id"],
               "stated_amount": r["stated_amount"], "action_type": r["action_type"]}
        drng = random.Random(seed * 1000 + int(r["request_id"]))
        text, truth, noise = render(req, tgts[r["request_id"]], drng, style=STYLES[i % len(STYLES)])
        split = "DEV" if i <= dev else "HELDOUT"
        docs.append([i, r["request_id"], r["case_id"], split, noise["style"], int(noise["conflict"]),
                     int(noise["distractor"]), text])
        truth_rows += [[i, f, truth[f]] for f in FIELDS]
    out = data_dir
    with open(out / "request_documents.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["doc_id", "request_id", "case_id", "split", "style", "planted_conflict", "distractor", "body"])
        w.writerows(docs)
    (out / "gt").mkdir(exist_ok=True)
    with open(out / "gt" / "letter_truth.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["doc_id", "field", "true_value"])
        w.writerows(truth_rows)
    return len(docs)


# ---------------------------------------------------------------- live-analysis demos
def scenario_letters(scenario: dict) -> list[dict]:
    """Two letters for a demo scenario: a tidy one and a noisy one with a missing detail."""
    req = scenario["request"]
    base = {"officer": req.get("officer"), "designation": req.get("designation"), "agency": req.get("agency"),
            "contact": req.get("contact"), "case_reference": req.get("reference"),
            "legal_provision": req.get("legal_provision"), "quoted_txn": "",
            "stated_amount": req.get("stated_amount"), "action_type": req.get("action_type")}
    label = lambda a: f"A/c {a}"  # noqa: E731
    out = []
    for k, (style, drop) in enumerate((("FORMAL_EN", None), ("HINGLISH", "contact"), ("CRYPTIC", "designation"),
                                       ("DEVA_MIX", None))):
        r = dict(base)
        if drop:
            r[drop] = ""
        rng = random.Random(zlib.crc32(f"{scenario['id']}-{k}".encode()))
        text, truth, noise = render(r, req.get("targets", []), rng, style=style, account_label=label)
        out.append({"id": f"{scenario['id']}-{k + 1}", "title": {"FORMAL_EN": "Formal letter", "HINGLISH": "Hinglish message",
                    "CRYPTIC": "Terse message", "DEVA_MIX": "Hindi and English"}[style] + (f", {drop} missing" if drop else ""),
                    "style": style, "text": text})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--dev", type=int, default=24)
    ap.add_argument("--heldout", type=int, default=60)
    a = ap.parse_args()
    n = build(Path(a.data_dir), a.dev, a.heldout)
    print(f"[letters] {n} synthetic letters -> {a.data_dir}/request_documents.csv (answer key in gt/letter_truth.csv)")
