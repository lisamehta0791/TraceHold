"""Amounts and identifiers in free text: writing them (letter generator) and
reading them back (deterministic checks after AI extraction, CF9).

Handles Indian digit grouping (1,04,269.06), currency marks (Rs., INR, ₹, /-),
lakh/crore with digits (1.5 lakh), English number words, and a small fixed
vocabulary of romanised Hindi and Devanagari number words.
"""
from __future__ import annotations

import re
import unicodedata

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
        "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

SMALL: dict[str, int] = {w: i for i, w in enumerate(ONES)}
SMALL.update({w: i * 10 for i, w in enumerate(TENS) if w})
SMALL.update({"fourty": 40})
# romanised Hindi (fixed vocabulary used by the generator)
SMALL.update({"ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhah": 6, "chhe": 6,
              "saat": 7, "aath": 8, "nau": 9, "das": 10, "bees": 20, "tees": 30, "chaalis": 40, "pachaas": 50,
              "pachas": 50})
# Devanagari
SMALL.update({"एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6, "सात": 7, "आठ": 8, "नौ": 9,
              "दस": 10, "बीस": 20, "तीस": 30, "चालीस": 40, "पचास": 50})
HUNDRED = {"hundred", "sau", "सौ"}
MULT = {"thousand": 1_000, "hazaar": 1_000, "hazar": 1_000, "hajar": 1_000, "हज़ार": 1_000, "हजार": 1_000,
        "lakh": 100_000, "lac": 100_000, "lakhs": 100_000, "lacs": 100_000, "लाख": 100_000,
        "crore": 10_000_000, "crores": 10_000_000, "karod": 10_000_000, "करोड़": 10_000_000, "करोड": 10_000_000}
PAISE = {"paise", "paisa", "पैसे"}
FILLER = {"and", "rupees", "rupee", "rs", "inr", "only", "aur", "rupaye", "rupaiye", "रुपये", "रुपए", "और", "of", "the"}


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "")).strip()


# ---------------------------------------------------------------- writing
def inr_digits(x: float, paise: bool = True) -> str:
    """1,04,269.06 (Indian grouping)."""
    neg = x < 0
    x = abs(round(x, 2))
    whole, frac = int(x), round((x - int(x)) * 100)
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = f"{head},{tail}"
    out = s + (f".{frac:02d}" if paise and frac else "")
    return ("-" if neg else "") + out


def _words_below_1000(n: int) -> str:
    parts = []
    if n >= 100:
        parts.append(f"{ONES[n // 100]} hundred")
        n %= 100
    if n >= 20:
        parts.append(TENS[n // 10] + (f" {ONES[n % 10]}" if n % 10 else ""))
    elif n:
        parts.append(ONES[n])
    return " ".join(parts)


def english_words(x: float) -> str:
    """Rupees One Lakh Four Thousand Two Hundred Sixty Nine and Six Paise only."""
    whole, paise = int(round(x, 2)), round((round(x, 2) - int(round(x, 2))) * 100)
    parts = []
    for unit, size in (("crore", 10_000_000), ("lakh", 100_000), ("thousand", 1_000)):
        if whole >= size:
            parts.append(f"{_words_below_1000(whole // size)} {unit}")
            whole %= size
    if whole:
        parts.append(_words_below_1000(whole))
    text = "Rupees " + " ".join(parts).title()
    if paise:
        text += f" and {_words_below_1000(paise).title()} Paise"
    return text + " only"


HI_ROMAN = {1: "ek", 2: "do", 3: "teen", 4: "chaar", 5: "paanch", 10: "das", 20: "bees", 50: "pachaas"}
HI_DEVA = {1: "एक", 2: "दो", 3: "तीन", 4: "चार", 5: "पाँच", 10: "दस", 20: "बीस", 50: "पचास"}


def hindi_words(x: float, script: str = "roman") -> str | None:
    """Only for amounts the fixed vocabulary can express exactly (L lakh + T thousand)."""
    if x != int(x):
        return None
    x = int(x)
    lakh, rest = divmod(x, 100_000)
    thou, rest = divmod(rest, 1_000)
    if rest or (lakh and lakh not in HI_ROMAN) or (thou and thou not in HI_ROMAN) or not (lakh or thou):
        return None
    vocab = HI_ROMAN if script == "roman" else HI_DEVA
    words = []
    if lakh:
        words += [vocab[lakh], "lakh" if script == "roman" else "लाख"]
    if thou:
        words += [vocab[thou], "hazaar" if script == "roman" else "हज़ार"]
    return " ".join(words) + (" rupaye" if script == "roman" else " रुपये")


# ---------------------------------------------------------------- reading
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _tokens(text: str) -> list[str]:
    t = norm_ws(text).lower()
    t = t.replace("₹", " ").replace("/-", " ").replace("rs.", " rs ").replace("-", " ")
    out = []
    for tok in re.findall(r"\d[\d,]*(?:\.\d+)?|[^\s\d,.;:()\[\]/'\"!?]+", t):
        out.append(tok.strip("'\"-"))
    return [t for t in out if t]


def parse_amount(text: str) -> float | None:
    """Read one amount written in digits and/or words. None if nothing numeric is found."""
    if not text:
        return None
    toks = _tokens(text)
    total, current, paise_part, seen = 0.0, 0.0, None, False
    for i, tok in enumerate(toks):
        if tok in FILLER:
            # "... sixty nine and six paise": what came before "and" is rupees
            if tok in ("and", "aur", "और") and any(t in PAISE for t in toks[i + 1:]):
                total += current
                current = 0.0
            continue
        if tok in PAISE:
            paise_part = current  # the number just read was the paise part
            current = 0.0
            continue
        if _NUM.fullmatch(tok):
            current += float(tok.replace(",", ""))
            seen = True
        elif tok in SMALL:
            current += SMALL[tok]
            seen = True
        elif tok in HUNDRED:
            current = (current or 1) * 100
            seen = True
        elif tok in MULT:
            total += (current or 1) * MULT[tok]
            current = 0.0
            seen = True
        else:
            continue
    if not seen:
        return None
    value = total + current
    if paise_part is not None:
        value += paise_part / 100
    return round(value, 2)


def amounts_in(text: str) -> list[float]:
    """Every separately written amount (used to spot conflicting figures in one span)."""
    out = []
    for chunk in re.split(r"[()\[\]]|\bi\.e\.?|\bie\b", text or ""):
        v = parse_amount(chunk)
        if v is not None and v > 0:
            out.append(v)
    return out


def norm_text(s: str | None) -> str:
    """Loose comparison form: lower case, punctuation folded, common abbreviations expanded."""
    t = norm_ws(s or "").lower()
    t = re.sub(r"\bp\.?\s?s\.?\b", "police station", t)
    t = re.sub(r"\binsp\.?\b", "inspector", t)
    t = re.sub(r"\bsec\.?\b|\bs\.\b|\bu/s\b", "section", t)
    t = re.sub(r"[^\w@.+/ ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


ACCOUNT_RE = re.compile(r"\bAC\d{7}\b")
TXN_RE = re.compile(r"\bT\d{10}\b")
REF_RE = re.compile(r"\b(?:NCRP|FIR|CR|CFCFRMS)[-/ ]?[\w/-]{4,}\b", re.I)
