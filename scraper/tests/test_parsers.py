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
    "hsbc": (60, "HKD", 12, None, 0.15),
    "citi": (5, "USD", 3, None, 3.8),
    "shacom": (30, "GBP", 12, None, 3.55),
    "icbcasia": (100, "HKD", 3, None, 3.00),
    "bea": (80, "HKD", 12, None, 0.15),
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
    vip = [o for o in cc if o["conditions"]["up_to"]]
    assert vip and all(o["conditions"]["new_customer"] for o in vip)
    assert 8.88 in [o["rate_pa"] for o in find(vip, "USD", 3)]
    online = find(cc, "USD", 3, up_to=False)
    assert online[0]["rate_pa"] == 4.05 and online[0]["min_amount"] == 100000
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
    bl = [b for b in banks() if b["id"] in ("welab", "mox", "dahsing", "dbs")]
    texts = {"welab": fx("welab"), "mox": fx("mox"), "dbs": fx("dbs")}
    offers, status = build(bl, texts, None, "2026-10-31T08:30:00+08:00")
    st = {s["bank_id"]: s for s in status}
    assert st["welab"]["status"] == "ok" and st["dahsing"]["status"] == "unsupported"
    assert st["dbs"]["status"] == "headline" and st["dbs"]["headline_max"]
    prev = {"offers": offers, "bank_status": status}
    texts2 = {"welab": RuntimeError("timeout"), "mox": "nothing here"}
    offers2, status2 = build(bl, texts2, prev, "2026-11-01T08:30:00+08:00")
    st2 = {s["bank_id"]: s for s in status2}
    assert st2["welab"]["status"] == "stale" and st2["mox"]["status"] == "stale"
    assert st2["welab"]["last_ok"] == "2026-10-31T08:30:00+08:00"
    assert all(o["status"] == "stale" for o in offers2)
    assert len(offers2) == len(offers)


def test_daily_hibor_overlay():
    from run import apply_daily_hibor
    h = {"date": "2026-09-30", "ir_overnight": 4.09, "ir_1m": 3.01, "ir_3m": 3.24}
    out = apply_daily_hibor(h, [{"end_of_date": "2026-10-30", "hibor_overnight": 2.65, "hibor_fixing_1m": 2.70923}])
    assert out["date"] == "2026-10-30" and out["ir_overnight"] == 2.65 and out["ir_3m"] == 3.24
    assert out["terms_date"] == "2026-09-30"
    assert apply_daily_hibor(h, [{"end_of_date": "2026-09-01", "hibor_overnight": 1, "hibor_fixing_1m": 1}]) == h


def test_citi_new_customer_only():
    o = parsers.citi(fx("citi"))
    assert all(x["conditions"]["new_customer"] and x["conditions"]["new_funds"] for x in o)


def test_promo_end_extraction():
    from run import promo_end
    assert promo_end("優惠由2026年10月1日起至2026年12月31日止") == "2026-12-31"
    assert promo_end("推廣期至2026/11/30") == "2026-11-30"
    assert promo_end("由2026年10月21日起") is None


def test_icbcasia_tiers_and_promos():
    ic = parsers.icbcasia(fx("icbcasia"))
    usd = find(ic, "USD", 1, tier="工銀財富／理財金")
    assert sorted(o["rate_pa"] for o in usd) == [3.10, 3.20]
    assert find(ic, "HKD", 1, tier="工銀財富")[0]["rate_pa"] == 1.70
    d98 = find(ic, "USD", None, 98, tier="工銀財富")
    assert d98[0]["rate_pa"] == 4.10 and d98[0]["conditions"]["new_funds"]
    nc = find(ic, "HKD", 3, new_customer=True)
    assert nc[0]["rate_pa"] == 6.00 and nc[0]["max_amount"] == 200000 and nc[0]["min_amount"] == 10000
    assert "2026年10月31日" in nc[0]["conditions_text_zh"]


def test_bea_board_both_pages():
    b = parsers.bea(fx("bea"))
    assert all(o["conditions"]["board"] for o in b)
    assert find(b, "USD", 12)[0]["rate_pa"] == 0.225
    assert {o["min_amount"] for o in find(b, "HKD", 3)} == {400000, 50000, 30000, 1000}


def test_join_pages_keeps_main_failure():
    from run import join_pages
    e = RuntimeError("x")
    assert join_pages(e, ["a"]) is e
    assert parsers.PAGE_SEP in join_pages("main", ["extra", e])


def test_parse_hkab():
    from run import parse_hkab
    j = {"Overnight": 2.45048, "1 Week": 2.47512, "2 Weeks": 2.53101, "1 Month": 2.6775,
         "2 Months": 3.04786, "3 Months": 3.20548, "6 Months": 3.43411, "12 Months": 3.91964,
         "year": 2026, "month": 11, "day": 2, "date": "2026-11-2", "time": "11:15am", "isHoliday": False}
    h = parse_hkab(j)
    assert h["date"] == "2026-11-02" and h["ir_3m"] == 3.20548 and h["source"] == "HKAB"
