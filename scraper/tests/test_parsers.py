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
    "dbs": (8, "HKD", 3, None, 2.80),
    "dahsing": (30, "USD", 6, None, 4.1),
    "chiyu": (40, "HKD", 60, None, 0.25),
    "airstar": (20, "USD", 12, None, 4.2),
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
    sc = [o for o in parsers.sc(fx("sc")) if not o["conditions"]["board"]]
    assert sc and all(o["conditions"]["new_funds"] for o in sc)
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
    bl = [b for b in banks() if b["id"] in ("welab", "mox", "cncbi", "dbs")]
    texts = {"welab": fx("welab"), "mox": fx("mox"), "dbs": fx("dbs")}
    offers, status = build(bl, texts, None, "2026-10-31T08:30:00+08:00")
    st = {s["bank_id"]: s for s in status}
    assert st["welab"]["status"] == "ok" and st["cncbi"]["status"] == "unsupported"
    assert st["dbs"]["status"] == "ok" and st["dbs"]["headline_max"]
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


def test_expired_promos_dropped_and_extra_pages_keep_their_url():
    bl = [b for b in banks() if b["id"] == "icbcasia"]
    t = fx("icbcasia")
    before, _ = build(bl, {"icbcasia": t}, None, "2026-10-31T08:30:00+08:00")
    after, st = build(bl, {"icbcasia": t}, None, "2026-11-02T08:30:00+08:00")
    gone = [o for o in before if o["promo_end"] == "2026-10-31"]
    assert gone and len(after) == len(before) - len(gone)
    assert not find(after, "HKD", 3, new_customer=True)
    stale, _ = build(bl, {"icbcasia": RuntimeError("x")}, {"offers": before}, "2026-11-02T08:30:00+08:00")
    assert len(stale) == len(after) and all(o["status"] == "stale" for o in stale)
    urls = [bl[0]["url"], *bl[0]["extra"]]
    assert {o["source_url"] for o in before} == set(urls)
    assert all("page" not in o for o in before)
    d98 = [o for o in after if o["tenor_days"] == 98]
    assert d98 and all(o["source_url"] == urls[1] for o in d98)


def test_failed_extra_page_keeps_slot():
    from run import join_pages
    j = join_pages("main", [RuntimeError("x"), "second"])
    assert parsers.pages(j)[2].strip() == "second"


def test_dbs_promo_conditions():
    got = parsers.dbs(fx("dbs"))
    reg = find(got, "USD", 3, None, new_funds=True)
    assert [o["rate_pa"] for o in reg] == [4.3] and reg[0]["min_amount"] == 65000
    assert all(o["page"] == 1 for o in got)


def test_dahsing_bands_and_fx():
    got = parsers.dahsing(fx("dahsing"))
    vip = [o for o in got if o["conditions"]["tier"] == "VIP 銀行服務" and o["tenor_months"] == 6
           and o["currency"] == "USD"]
    assert {o["rate_pa"] for o in vip} == {3.9, 4.0, 4.1}
    top = [o for o in vip if o["max_amount"] is None][0]
    assert top["min_amount"] == 645162 and top["conditions"]["channel"] == "分行"
    conv = [o for o in got if o["conditions"]["fx_conversion"]]
    assert conv and all(not o["conditions"]["new_funds"] for o in conv)
    hkd6 = {(o["conditions"]["tier"], o["min_amount"]): o["rate_pa"] for o in got
            if o["currency"] == "HKD" and o["tenor_months"] == 6}
    assert hkd6[("VIP 銀行服務", 200000)] == 3.2 and hkd6[(None, 1000000)] == 3.1
    assert all(o["page"] == 1 for o in got if o["currency"] == "HKD")


def test_chiyu_amount_columns():
    got = parsers.chiyu(fx("chiyu"))
    three = find(got, "HKD", 3)
    assert [(o["min_amount"], o["max_amount"]) for o in three] == [(None, 99999), (100000, 499999), (500000, None)]
    assert all(o["conditions"]["board"] for o in got)


def test_airstar_only_time_deposits():
    got = parsers.airstar(fx("airstar"))
    assert {o["currency"] for o in got} == {"HKD", "USD", "CNH"}
    assert find(got, "HKD", None, 7)[0]["rate_pa"] == 0.01
    assert "page" not in got[0]


def test_health_alerts():
    from run import health
    prev = {"offers": [{}] * 100, "hibor": {"date": "2026-11-01"}}
    st = [{"bank_id": "a", "status": "ok", "last_ok": "2026-11-02T08:40:00+08:00", "error": None},
          {"bank_id": "b", "status": "stale", "last_ok": "2026-10-29T08:40:00+08:00", "error": "timeout"},
          {"bank_id": "c", "status": "stale", "last_ok": "2026-11-01T17:40:00+08:00", "error": "timeout"},
          {"bank_id": "d", "status": "unsupported", "last_ok": None, "error": None}]
    h = health(st, [{}] * 60, {"date": "2026-10-20"}, prev, "2026-11-02T08:40:00+08:00")
    text = " ".join(h["alerts"])
    assert "b" in text and " c " not in f" {text} " and "60" in text and "HIBOR" in text
    assert h["ok"] == 1 and h["stale"] == 2
    assert health(st[:1], [{}] * 100, {"date": "2026-11-02"}, prev, "2026-11-02T08:40:00+08:00")["alerts"] == []


def test_big_shrink_keeps_previous_as_stale():
    bl = [b for b in banks() if b["id"] == "fubon"]
    offers, status = build(bl, {"fubon": fx("fubon")}, None, "2026-11-01T08:40:00+08:00")
    assert len(offers) >= 50
    few = "\n".join(fx("fubon").splitlines()[:0]) or "nothing"
    short = [dict(o) for o in offers[:4]]
    import parsers as P
    orig = P.PARSERS["fubon"]
    P.PARSERS["fubon"] = lambda t: [dict(o, conditions=dict(o["conditions"])) for o in short]
    try:
        o2, s2 = build(bl, {"fubon": few}, {"offers": offers, "bank_status": status}, "2026-11-02T08:40:00+08:00")
    finally:
        P.PARSERS["fubon"] = orig
    assert s2[0]["status"] == "stale" and "只抽到 4 條" in s2[0]["error"] and len(o2) == len(offers)


def test_sc_board_page():
    got = parsers.sc(fx("sc"))
    board = [o for o in got if o["conditions"]["board"]]
    assert {o["page"] for o in board} == {1}
    hkd3 = find(board, "HKD", 3)
    assert len(hkd3) == 7 and hkd3[0]["rate_pa"] == 0.125
    assert (hkd3[0]["min_amount"], hkd3[0]["max_amount"]) == (10000, 29999)
    assert hkd3[-1]["min_amount"] == 5000000 and hkd3[-1]["max_amount"] is None
    assert find(board, "USD", 12)[0]["rate_pa"] == 0.60
    assert not any(o["conditions"]["new_funds"] for o in board)


def test_page_promo_end():
    from run import page_promo_end
    assert page_promo_end("推廣期：2026年11月2日至2026年11月30日（包括首尾") == "2026-11-30"
    assert page_promo_end("推廣期由2026年10月1日至2026年12月31日 ... 優惠期至2027年1月31日") is None
    assert page_promo_end("截至2023年11月20日就本港") is None


def test_build_fills_promo_end_from_page():
    b = dict(id="x", url="u", parser="x", extra=[])
    parsers.PARSERS["x"] = lambda t: [offer("x", "HKD", (3, None), 3.0, new_funds=True),
                                      offer("x", "HKD", (3, None), 0.1, board=True)]
    try:
        out, _ = build([b], {"x": "推廣期：2026年11月2日至2026年11月30日"}, None, "2026-11-03T08:40:00+08:00")
    finally:
        del parsers.PARSERS["x"]
    ends = {o["conditions"]["board"]: o["promo_end"] for o in out}
    assert ends == {False: "2026-11-30", True: None}


def test_promo_log_tracks_first_seen_and_end():
    from run import update_promo_log, promo_key

    def o(bank, rate, board=False, st="ok"):
        c = {"new_funds": True, "new_customer": False, "up_to": False, "board": board}
        return {"bank_id": bank, "currency": "HKD", "tenor_months": 3, "tenor_days": None,
                "rate_pa": rate, "min_amount": 10000, "conditions": c, "status": st}

    ok = [{"bank_id": b, "status": "ok"} for b in ("a", "b")]
    k = promo_key("a", "HKD", 3, None, 3.5, 10000, 1, 0)
    hist = [("2026-11-01", {k}, {"a"}), ("2026-11-02", set(), {"a"}),
            ("2026-11-03", {k}, {"a"}), ("2026-11-04", {k}, {"a"})]
    day1 = [o("a", 3.5), o("b", 3.0), o("b", 1.0, board=True)]
    log = update_promo_log(None, day1, ok, "2026-11-05", hist)
    assert day1[0]["first_seen"] == "2026-11-03"  # latest unbroken run only
    assert day1[1]["first_seen"] == "2026-11-05"
    assert "first_seen" not in day1[2] and len(log["promos"]) == 2
    # a's promo vanishes while a scrapes ok → ended; b goes stale → not ended
    day2 = [o("a", 3.6), o("b", 3.0, st="stale")]
    log = update_promo_log(log, day2, [ok[0], {"bank_id": "b", "status": "stale"}], "2026-11-06")
    by = {e["k"]: e for e in log["promos"]}
    assert by[k]["ended"] == "2026-11-06" and by[k]["last_seen"] == "2026-11-05"
    assert by[promo_key("b", "HKD", 3, None, 3.0, 10000, 1, 0)]["ended"] is None
    # comes back → reopened, first_seen kept
    log = update_promo_log(log, [o("a", 3.5)], ok, "2026-11-07")
    e = {e["k"]: e for e in log["promos"]}[k]
    assert e["ended"] is None and e["first_seen"] == "2026-11-03"
    # pruned 180 days after ending
    log = update_promo_log(log, [], ok, "2027-01-01")
    assert all(e["ended"] for e in log["promos"])
    assert len(update_promo_log(log, [], ok, "2027-06-30")["promos"]) == 1
    assert update_promo_log(log, [], ok, "2027-07-01")["promos"] == []
