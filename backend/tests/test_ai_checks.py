"""The deterministic checks that run after every AI call (no model is called here)."""
import random

import pytest

from app.textnum import amounts_in, english_words, hindi_words, inr_digits, parse_amount


# ---------------------------------------------------------------- amounts in letters
@pytest.mark.parametrize("seed", range(5))
def test_amount_round_trip(seed):
    rng = random.Random(seed)
    for _ in range(400):
        x = round(rng.uniform(1, 5e7), 2)
        for text in (english_words(x), f"Rs. {inr_digits(x)}/-", f"₹{inr_digits(x)}", f"INR {x:.2f}"):
            assert parse_amount(text) == round(x, 2), text


def test_hindi_amounts():
    assert parse_amount("ek lakh bees hazaar rupaye") == 120000
    assert parse_amount("एक लाख बीस हज़ार रुपये") == 120000
    assert parse_amount(hindi_words(250000, "roman")) == 250000
    assert hindi_words(104269.06) is None  # not expressible: the generator falls back to digits


def test_conflicting_amounts_are_separated():
    assert sorted(amounts_in("Rs 1,00,000/- (Rupees Ninety Thousand only)")) == [90000, 100000]
    assert amounts_in("Rs 2,00,000/- (do lakh rupaye)") == [200000, 200000]


# ---------------------------------------------------------------- CF9 rule checks
def test_quote_must_appear_whole_word():
    from app.ai.extract import _find_span
    text = "Sewa mein, Nodal Adhikari ji: A/c A, A/c B"
    start, end = _find_span(text, "A")
    assert text[start - 4:end] == "A/c A"
    assert _find_span(text, "not in the letter") == (-1, -1)


def test_amount_must_follow_from_quote():
    from app.ai.extract import _check_value
    value, checks = _check_value("stated_amount", "2,00,000 (do lakh rupaye)", "Rs 2,00,000/- (do lakh rupaye)", {})
    assert value == 200000 and all(c["ok"] for c in checks)
    _, checks = _check_value("stated_amount", "150000", "Rs 2,00,000/-", {})
    assert not next(c for c in checks if c["check"] == "value follows from the quote")["ok"]


def test_words_next_to_digits_must_agree():
    from app.ai.extract import _check_value, _neighbour_words
    text = "amount of Rs. 80,645.96/- (Rupees Eighty Eight Thousand only) hai"
    end = text.find("80,645.96") + len("80,645.96")
    words = _neighbour_words(text, end)
    _, checks = _check_value("stated_amount", "80645.96", "80,645.96", {"_neighbour": words})
    assert not next(c for c in checks if c["check"] == "one amount in the quote")["ok"]


def test_action_must_follow_from_quote():
    from app.ai.extract import _check_value
    v, checks = _check_value("action_type", "LIEN_AMOUNT", "vivadit raashi ka lien mark karein", {})
    assert v == "LIEN_AMOUNT" and all(c["ok"] for c in checks)
    _, checks = _check_value("action_type", "TOTAL_FREEZE", "debit freeze lagaayen", {})
    assert not all(c["ok"] for c in checks)


def test_conflict_is_never_resolved():
    from app.ai.extract import _field_status
    items = [{"value": 50000.0, "verified": True, "records_ok": True, "start": 1, "end": 5, "checks": []},
             {"value": 40000.0, "verified": True, "records_ok": True, "start": 9, "end": 14, "checks": []}]
    f = _field_status("stated_amount", items)
    assert f["status"] == "CONFLICT" and f["value"] is None


def test_unverified_value_is_not_used():
    from app.ai.extract import _field_status
    items = [{"value": "T123", "verified": False, "records_ok": True, "start": -1, "end": -1,
              "checks": [{"check": "quote appears in the letter", "ok": False, "detail": ""}]}]
    f = _field_status("quoted_txn", items)
    assert f["status"] == "UNVERIFIED" and f["value"] is None


# ---------------------------------------------------------------- AF7 guards
def test_only_results_views_can_be_queried():
    from app.ai.ask import AskRejected, check_sql
    for bad in ["SELECT * FROM TRACEHOLD.TRANSACTIONS", "SELECT * FROM TRACEHOLD_GT.LEDGER",
                "DELETE FROM TH_RESULTS.CASES", "SELECT 1 FROM TH_RESULTS.CASES; DROP TABLE X",
                "SELECT * FROM TH_RESULTS.CASES c JOIN TRACEHOLD.ACCOUNTS a ON 1=1"]:
        with pytest.raises(AskRejected):
            check_sql(bad)
    ok = check_sql("SELECT case_ref FROM TH_RESULTS.CASES ORDER BY unsupported_amount DESC")
    assert ok.endswith("LIMIT 200")


def test_numbers_in_answer_must_be_in_rows():
    from app.ai.ask import number_fidelity
    rows = [["NCRP-1", "15052458.48"], ["NCRP-2", "200"]]
    assert number_fidelity("The largest is ₹15,052,458.48 in NCRP-1.", rows, [])["ok"]
    bad = number_fidelity("About ₹1.5 crore is unsupported across 7 cases.", rows, [])
    assert not bad["ok"] and "7" in bad["unsupported"]
    assert not number_fidelity("The largest is $200.", rows, [])["ok"]


def test_templates_validate_parameters():
    from app.ai.ask import TEMPLATE_BY_ID, AskRejected, fill_template
    sql, used = fill_template(TEMPLATE_BY_ID["old_overheld"], {"days": 120})
    assert "days_held > 120" in sql and used["limit"] == 200
    with pytest.raises(AskRejected):
        fill_template(TEMPLATE_BY_ID["case_accounts"], {"case_ref": "x'; DROP TABLE y; --"})


# ---------------------------------------------------------------- AF8 fact check
def test_reworded_letter_must_keep_every_fact():
    from app.ai.reword import check
    t = "On 07 Aug 2026 a request asked to restrict account AC0135351. Between ₹16,500.90 and ₹16,887.71 can be traced."
    assert check(t, "On 07 Aug 2026 your bank was asked to restrict account AC0135351. Between ₹16,500.90 and ₹16,887.71 can be traced.")["ok"]
    assert not check(t, t.replace("₹16,887.71", "₹16,000"))["ok"]
    assert not check(t, t.replace(" and ₹16,887.71", ""))["ok"]
    assert not check(t, t.replace("a request asked", "money was sent from your account and a request asked"))["ok"]
