"""Property and determinism tests on the real SQL engine (live-analysis schema).

- Conservation: for randomly generated cases, retained + left + untraced +
  absorbed equals the loss under every convention.
- Determinism: the same case run twice gives exactly the same results.
"""
import json
import random

import pytest

pytestmark = pytest.mark.db


def random_case(seed: int) -> dict:
    rng = random.Random(seed)
    names = [chr(65 + i) for i in range(rng.randint(2, 5))]
    accounts = [{"name": n, "opening": rng.choice([0, 500, 2000, 15000, 120000])} for n in names]
    loss = rng.choice([25000, 60000, 100000, 240000])
    transfers = [{"from": "VICTIM", "to": names[0], "amount": loss, "minute": 0}]
    minute = 2
    for _ in range(rng.randint(2, 6)):
        frm = rng.choice(names)
        to = rng.choice([n for n in names if n != frm] + ["CASH", "OTHER_BANK"])
        transfers.append({"from": frm, "to": to, "amount": rng.choice([1000, 5000, 12000, 30000]), "minute": minute})
        minute += rng.randint(1, 15)
    request = {"officer": "Test", "designation": "Inspector", "agency": "PS", "contact": "x@y.in", "reference": "NCRP-1",
               "legal_provision": "Section 106 BNSS", "action_type": "TOTAL_FREEZE", "stated_amount": loss,
               "targets": [{"account": n, "scope": "WHOLE_BALANCE"} for n in names]}
    return {"accounts": accounts, "transfers": transfers, "request": request}


@pytest.mark.parametrize("seed", [11, 23, 37, 41, 59])
def test_conservation_on_random_cases(seed):
    from app.playground import PlaygroundError, run
    body = random_case(seed)
    try:
        r = run(body)
    except PlaygroundError:  # a generated account paid more than it held: rejected up front, nothing to check
        pytest.skip("generated case rejected by validation")
    for c in r["conservation"]:
        assert c["passed"], (seed, c)
        assert abs(c["difference"]) < 0.01


def _stable(r: dict) -> str:
    r = dict(r)
    r.pop("engine", None)
    return json.dumps(r, sort_keys=True, default=str)


def test_same_case_twice_is_identical(worked):
    from app.playground import run
    assert _stable(run(worked)) == _stable(run(worked))


def test_stored_case_packet_is_reproducible():
    from app import main
    a = main._packet(2244)
    b = main._packet(2244)
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
