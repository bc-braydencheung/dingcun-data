import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import parsers  # noqa: E402
from banks import banks  # noqa: E402
from common import offer, rate, sane, tenor  # noqa: E402
from run import build  # noqa: E402


def fx(name):
    return open(os.path.join(HERE, "..", "fixtures", f"{name}.txt"), encoding="utf-8").read()


def find(offers, cur, months=None, days=None, **cond):
    return [o for o in offers if o["currency"] == cur and o["tenor_months"] == months
            and o["tenor_days"] == days
            and all(o["conditions"][k] == v for k, v in cond.items())]


EXPECT = {
    # bank: (min offers, currency, months, days, expected rate)
    "bochk": (20, "USD", 3, None, 3.30),
    "hangseng": (40, "HKD", 12, None, 0.15),
    "sc": (20, "HKD", 12, None, 3.30),
    "livi": (20, "USD", 12, None, 4.20),
    "publicbank": (60, "USD", 6, None, 4.15),
    "antbank": (15, "USD", 12, None, 3.65),
    "paob": (10, "HKD", 12, None, 3.40),
    "welab": (5, "HKD", 13, None, 3.35),
    "mox": (10, "HKD", 6, None, 3.00),
    "fubon": (50, "CNH", 6, None, 1.10),
    "chbank": (100, "HKD", 12, None, None),
    "za": (2, "CNH", None, 7, 20.0),
    "ccba": (2, "HKD", 3, None, 7.88),
}


@pytest.mark.parametrize("bank", sorted(EXPECT))
def test_parser_fixture(bank):
    n, cur, m, d, r = EXPECT[bank]
    got = parsers.PARSERS[bank](fx(bank))
    assert len(got) >= n
    assert all(sane(o) for o in got)
    hits = find(got, cur, m, d)
    assert hits
    if r is not None:
        assert r in [o["rate_pa"] for o in hits]


def test_condition_flags():
    sc = parsers.sc(fx("sc"))
    assert all(o["conditions"]["new_funds"] for o in sc)
    assert sc[0]["min_amount"] == 10000 and sc[0]["promo_end"]
    za = parsers.za(fx("za"))
    assert all(o["conditions"]["fx_conversion"] for o in za)
    cc = parsers.ccba(fx("ccba"))
    assert all(o["conditions"]["new_customer"] and o["conditions"]["up_to"] for o in cc)
    ant = parsers.antbank(fx("antbank"))
    assert find(ant, "HKD", 3, None, new_funds=False) and find(ant, "HKD", 3, None, new_funds=True)


def test_tiers_hangseng_publicbank():
    hs = find(parsers.hangseng(fx("hangseng")), "HKD", 3)
    assert {o["min_amount"] for o in hs} >= {10000, 100000, 500000}
    pb = find(parsers.publicbank(fx("publicbank")), "HKD", 12)
    assert sorted(o["rate_pa"] for o in pb) == [3.25, 3.30, 3.35]
    assert pb[0]["max_amount"] == 99999


def test_tenor_and_rate_helpers():
    assert tenor("3個月") == (3, None)
    assert tenor("一星期") == (None, 7)
    assert tenor("十二個月") == (12, None)
    assert tenor("2 年") == (24, None)
    assert tenor("7 日") == (None, 7)
    assert tenor("abc") is None
    assert rate("2.40%") == 2.4 and rate("-") is None and rate("0.27") == 0.27


def test_validation_rejects_bad():
    assert not sane(offer("x", "HKD", (3, None), 80.0))
    assert not sane(offer("x", "HKD", (0, None), 3.0))
    assert sane(offer("x", "HKD", (3, None), 3.0))


def test_stale_fallback_and_status():
    bl = [b for b in banks() if b["id"] in ("welab", "mox", "citi", "hsbc")]
    texts = {"welab": fx("welab"), "mox": fx("mox"), "hsbc": fx("hsbc")}
    offers, status = build(bl, texts, None, "2026-10-31T08:30:00+08:00")
    st = {s["bank_id"]: s for s in status}
    assert st["welab"]["status"] == "ok" and st["citi"]["status"] == "unsupported"
    assert st["hsbc"]["status"] == "headline" and st["hsbc"]["headline_max"]
    prev = {"offers": offers, "bank_status": status}
    texts2 = {"welab": RuntimeError("timeout"), "mox": "nothing here"}
    offers2, status2 = build(bl, texts2, prev, "2026-11-01T08:30:00+08:00")
    st2 = {s["bank_id"]: s for s in status2}
    assert st2["welab"]["status"] == "stale" and st2["mox"]["status"] == "stale"
    assert st2["welab"]["last_ok"] == "2026-10-31T08:30:00+08:00"
    assert all(o["status"] == "stale" for o in offers2)
    assert len(offers2) == len(offers)
