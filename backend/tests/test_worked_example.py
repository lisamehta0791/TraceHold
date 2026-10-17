"""The worked example from the project document (section 4.7), checked to the paisa,
plus the last-in-first-out bounds from AF2 and the over-broad ratios from CF5."""
import pytest

pytestmark = pytest.mark.db

EXPECTED = {  # account: (balance, pro-rata, FIFO, LIFO)
    "A": (30000.00, 25000.00, 30000.00, 10000.00),
    "B": (190000.00, 24152.54, 70000.00, 0.00),
    "C": (450000.00, 50847.46, 0.00, 90000.00),
}


@pytest.fixture(scope="module")
def result(worked):
    from app.playground import run
    return run(worked)


def test_retained_amounts_to_the_paisa(result):
    got = {a["account_id"]: a for a in result["accounts"]}
    for acc, (bal, pr, fifo, lifo) in EXPECTED.items():
        a = got[acc]
        assert a["balance"] == pytest.approx(bal, abs=0.005)
        assert a["retained_pr"] == pytest.approx(pr, abs=0.005)
        assert a["retained_fifo"] == pytest.approx(fifo, abs=0.005)
        assert a["retained_lifo"] == pytest.approx(lifo, abs=0.005)
        assert a["status"] == "RANGE"


def test_traceable_share(result):
    got = {a["account_id"]: a for a in result["accounts"]}
    assert got["A"]["share_lo"] == pytest.approx(0.833, abs=0.001)
    assert got["B"]["share_lo"] == pytest.approx(0.127, abs=0.001)
    assert got["B"]["share_hi"] == pytest.approx(0.368, abs=0.001)
    assert got["C"]["share_hi"] == pytest.approx(0.113, abs=0.001)


def test_conservation_every_convention(result):
    assert len(result["conservation"]) == 3
    for c in result["conservation"]:
        assert c["passed"], c
        assert c["retained"] + c["exited"] + c["dust"] + c["absorbed"] == pytest.approx(100000.0, abs=0.01)


def test_whole_balance_over_upper_bound(result):
    ratio = {v["account_id"]: v["ratio_to_upper"] for v in result["review"]}
    assert ratio["A"] == pytest.approx(1.00, abs=0.01)
    assert ratio["B"] == pytest.approx(2.71, abs=0.01)
    assert ratio["C"] == pytest.approx(8.85, abs=0.01)
    cls = {v["account_id"]: v["classification"] for v in result["review"]}
    assert cls == {"A": "WITHIN_RANGE", "B": "EXCEEDS_EVIDENCE", "C": "EXCEEDS_EVIDENCE"}


def test_request_is_complete(result):
    assert result["request_check"]["status"] == "COMPLETE"
