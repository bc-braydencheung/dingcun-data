"""Per-bank parsers. Each takes page text and returns a list of offers."""
import re

from common import (amount, currency, offer, rate, rows, snippet, tenor,
                    tokens)


def _first_rate_cells(cells):
    return [rate(c) if c not in ("-", "--", "-------") else None for c in cells]


def bochk(text):
    out = []
    note = snippet(text, "個人銀行客戶經網上銀行或手機銀行")
    mins = {"HKD": 10000, "USD": 1000, "CNH": 10000}
    cur = None
    for cells in rows(text, "新資金特優定期存款", "以上為"):
        c0 = currency(cells[0]) if cells else None
        if c0:
            cur, cells = c0, cells[1:]
        if not cur or not cells:
            continue
        tier_label = cells[0]
        vals = [v for v in (rate(c) if c != "-" else "skip" for c in cells[1:])
                if v is not None][:3]
        if len(vals) < 2:
            continue
        tier = "私人財富／中銀理財" if "私人財富" in tier_label else None
        for ten, v in zip([(3, None), (6, None), (12, None)], vals):
            if v == "skip":
                continue
            out.append(offer("bochk", cur, ten, v, min_amount=mins[cur],
                             new_funds=True, tier=tier, channel="網上／手機銀行",
                             text=note))
    toks = tokens(text, "特優人民幣及外幣定期存款優惠", "請登入")
    curs = [currency(t) for t in toks if currency(t)]
    note2 = snippet(text, "選用「綜合理財服務」的個人銀行客戶以兌換資金")
    for i, t in enumerate(toks):
        ten = tenor(t)
        if not ten:
            continue
        vals = [rate(x) for x in toks[i + 1:i + 1 + len(curs)]]
        for c, v in zip(curs, vals):
            if v:
                out.append(offer("bochk", c, ten, v, min_amount=10000 if c == "CNH" else 1000,
                                 fx_conversion=True, tier="綜合理財服務",
                                 channel="網上／手機銀行", text=note2))
    return out


def hangseng(text):
    out = []
    rs = rows(text, "港元定期存款利率\n牌價", "相關連結")
    header = next((r for r in rs if r and r[0] == "存款期"), None)
    if not header:
        return out
    tiers = []
    for h in header[1:]:
        nums = [int(x.replace(",", "")) for x in re.findall(r"[\d,]{4,}", h)]
        tiers.append((nums[0] if nums else None, nums[1] if len(nums) > 1 else None))
    for r in rs:
        ten = tenor(r[0]) if r else None
        if not ten:
            continue
        for (lo, hi), v in zip(tiers, _first_rate_cells(r[1:])):
            if v:
                out.append(offer("hangseng", "HKD", ten, v, min_amount=lo, max_amount=hi,
                                 board=True, text="分行牌價（一般客戶）"))
    return out


def sc(text):
    out = []
    note = snippet(text, "由即日起至")
    promo = re.search(r"至(\d{4})年(\d{1,2})月(\d{1,2})日", note)
    end = f"{promo.group(1)}-{int(promo.group(2)):02d}-{int(promo.group(3)):02d}" if promo else None
    toks = tokens(text, "網上新資金定期存款優惠", "\n註")
    cur, mn, pending = None, None, None
    for t in toks:
        m = re.match(r"新資金達(\D+?)([\d,]+)或以上", t)
        if m:
            cur, mn = currency(m.group(1)), int(m.group(2).replace(",", ""))
            continue
        if currency(t) and not cur:
            cur = currency(t)
        ten = tenor(t)
        if ten:
            pending = ten
            continue
        v = rate(t)
        if v is not None and pending and cur:
            o = offer("sc", cur, pending, v, min_amount=mn, new_funds=True,
                      channel="SC Mobile App／網上理財", text=note)
            o["promo_end"] = end
            out.append(o)
            pending = None
    return out


def livi(text):
    out = []
    rs = rows(text, "存款期及年利率 (HKD)", "以上定期存款利率")
    for r in rs:
        ten = tenor(r[0])
        if ten and len(r) >= 3:
            lo, hi = _first_rate_cells(r[1:3])
            if lo:
                out.append(offer("livi", "HKD", ten, lo, min_amount=500, max_amount=49999))
            if hi:
                out.append(offer("livi", "HKD", ten, hi, min_amount=50000))
    for cur, start, mn in (("USD", "存款期及年利率 (USD)", 100), ("CNH", "存款期及年利率 (CNY)", 500)):
        toks = tokens(text, start, "風險")
        for i, t in enumerate(toks[:-1]):
            ten, v = tenor(t), rate(toks[i + 1])
            if ten and v:
                out.append(offer("livi", cur, ten, v, min_amount=mn))
    return out


def publicbank(text):
    out = []
    rs = rows(text, "港元定期存款年利率", "外幣定期存款年利率")
    hdr = next((r for r in rs if r[0] == "貨幣"), [])
    tiers = []
    for h in hdr[1:]:
        n = amount(h)
        tiers.append((None, n - 1) if "<" in h else (n, None))
    # close the >= tiers
    fixed = []
    for i, (lo, hi) in enumerate(tiers):
        if lo is not None and i + 1 < len(tiers) and tiers[i + 1][0]:
            hi = tiers[i + 1][0] - 1
        fixed.append((lo, hi))
    for r in rs:
        ten = tenor(r[0])
        if ten:
            for (lo, hi), v in zip(fixed, _first_rate_cells(r[1:])):
                if v:
                    out.append(offer("publicbank", "HKD", ten, v, min_amount=lo, max_amount=hi,
                                     board=True, text="牌價"))
    rs = rows(text, "外幣定期存款年利率", "風險聲明")
    hdr = next((r for r in rs if r[0] == "貨幣"), [])
    curs = [currency(h) for h in hdr[1:]]
    for r in rs:
        ten = tenor(r[0])
        if ten:
            for c, v in zip(curs, _first_rate_cells(r[1:])):
                if c and v:
                    out.append(offer("publicbank", c, ten, v, board=True, text="牌價"))
    return out


def antbank(text):
    out = []
    note = "新資金額外加息只適用於新資金；可提前支取全部存款（不收手續費）"
    for cur, start in (("HKD", "港幣定期存款年利率"), ("USD", "美元定期存款年利率")):
        toks = tokens(text, start, "註" if cur == "HKD" else "港幣定期存款年利率")
        for i, t in enumerate(toks):
            ten = tenor(t)
            if not ten:
                continue
            vals = [rate(x) for x in toks[i + 1:i + 5]]
            if len(vals) < 4 or None in vals:
                continue
            base, extra, _large, total = vals
            if base:
                out.append(offer("antbank", cur, ten, base, min_amount=1, text=note))
            if extra and total > base:
                out.append(offer("antbank", cur, ten, total, min_amount=1, new_funds=True, text=note))
    return out


def paob(text):
    out = []
    rs = rows(text, "定期存款年利率", "年利率根據")
    hdr = next((r for r in rs if r[0] == "存款期"), [])
    curs = [currency(h.split()[0].replace("(年利率)", "")) for h in hdr[1:]]
    for r in rs:
        ten = tenor(r[0])
        if ten:
            for c, v in zip(curs, _first_rate_cells(r[1:])):
                if c and v:
                    out.append(offer("paob", c, ten, v, channel="App"))
    return out


def welab(text):
    out = []
    for r in rows(text, "年利率*", "*以上為"):
        ten = tenor(r[0])
        v = rate(r[1]) if len(r) > 1 else None
        if ten and v:
            out.append(offer("welab", "HKD", ten, v, channel="App"))
    return out


def mox(text):
    out = []
    note = snippet(text, "由即日起，以新資金開立定期存款")
    for cur, start, end in (("USD", "美元新資金定期存款：", "港元新資金定期存款："),
                            ("HKD", "港元新資金定期存款：", "*提提你")):
        for r in rows(text, start, end):
            ten = tenor(r[0])
            v = rate(r[1]) if len(r) > 1 else None
            if ten and v:
                out.append(offer("mox", cur, ten, v, new_funds=True, channel="App", text=note))
    for r in rows(text, "存款期 (美元)", "「智安存」"):
        ten = tenor(r[0])
        v = rate(r[1]) if len(r) > 1 else None
        if ten and v:
            out.append(offer("mox", "USD", ten, v, fx_conversion=True, channel="App",
                             text="先用 Mox 兌換美元再開立美元定存"))
    return out


def _dec(x):
    return rate(x) if "." in x else None


def fubon(text):
    out = []
    toks = tokens(text, "港元定期存款", "外幣定期存款年利率")
    tiers = [(50000, 199999), (200000, 499999), (500000, None)]
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.isdigit() and 1 <= int(t) <= 36:
            vals = [_dec(x) for x in toks[i + 1:i + 4]]
            if len(vals) == 3 and None not in vals:
                for (lo, hi), v in zip(tiers, vals):
                    if v:
                        out.append(offer("fubon", "HKD", (int(t), None), v, min_amount=lo,
                                         max_amount=hi, board=True, text="牌價"))
                i += 4
                continue
        i += 1
    toks = tokens(text, "人民幣定期存款年利率", "港元定期存款")
    for i, t in enumerate(toks[:-1]):
        if t.isdigit() and 1 <= int(t) <= 36 and rate(toks[i + 1]) and "%" in toks[i + 1]:
            out.append(offer("fubon", "CNH", (int(t), None), rate(toks[i + 1]), min_amount=10000,
                             board=True, text="牌價"))
    toks = tokens(text, "外幣定期存款年利率", "註")
    curs = [currency(t) for t in toks[:12] if currency(t)]
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.isdigit() and 1 <= int(t) <= 36:
            vals = [_dec(x) for x in toks[i + 1:i + 1 + len(curs)]]
            if len(vals) == len(curs) and None not in vals:
                for c, v in zip(curs, vals):
                    if v:
                        out.append(offer("fubon", c, (int(t), None), v, board=True,
                                         text="牌價；最少存款相等於港幣200,000"))
                i += 1 + len(curs)
                continue
        i += 1
    return out


def chbank(text):
    out = []
    tens = [(None, 1), (None, 7), (None, 14), (1, None), (2, None), (3, None),
            (6, None), (9, None), (12, None), (24, None)]
    cur = None
    for r in rows(text, "定期存款（牌價）", "\n雲利率\n"):
        c0 = currency(r[0])
        if c0:
            cur, r = c0, r[1:]
        if not cur or len(r) < 11 or not re.search(r"\d", r[0]):
            continue
        nums = [int(x.replace(",", "")) for x in re.findall(r"[\d,]{3,}", r[0])]
        lo = nums[0] if nums else None
        hi = nums[1] if len(nums) > 1 else None
        for ten, v in zip(tens, _first_rate_cells(r[1:11])):
            if v:
                out.append(offer("chbank", cur, ten, v, min_amount=lo, max_amount=hi,
                                 board=True, text="牌價"))
    return out


def za(text):
    out = []
    for m in re.finditer(r"([\d.]+)%\s*p\.a\.\s*(\d+)\s*天\s*(人民幣|美元|港元)定存", text):
        out.append(offer("za", currency(m.group(3)), (None, int(m.group(2))), float(m.group(1)),
                         fx_conversion=m.group(3) != "港元", channel="App",
                         text="外幣兌換定存：開立時自動兌換貨幣，以 ZA Bank App 內顯示為準"))
    return out


def ccba(text):
    out = []
    for start, nc_tier, ch in (("全新「貴賓理財」客戶定期存款推廣", "貴賓理財（全新客戶）", "分行"),
                               ("全新「智選理財」及一般個人銀行客戶定期存款推廣", None, "e賬戶服務")):
        toks = tokens(text, start, "了解更多")
        note = " ".join(toks[:2])[:220]
        for i, t in enumerate(toks):
            if "港元" in t and i + 3 < len(toks):
                ten = tenor(toks[i + 1])
                v = rate(toks[i + 3]) if toks[i + 2] == "高達" else None
                if ten and v:
                    for c in ("HKD", "CNH"):
                        out.append(offer("ccba", c, ten, v, new_customer=True, new_funds=True,
                                         tier=nc_tier, channel=ch, up_to=True, text=note))
                break
    return out


def headline_only(text):
    return []


def headline(text):
    """'高達 3.70%' style headline numbers, for banks without a parsable table."""
    vals = [float(x) for x in re.findall(r"高達\s*(\d{1,2}(?:\.\d+)?)\s*%", text)]
    return max(vals) if vals else None


PARSERS = {
    "bochk": bochk, "hangseng": hangseng, "sc": sc, "livi": livi,
    "publicbank": publicbank, "antbank": antbank, "paob": paob, "welab": welab,
    "mox": mox, "fubon": fubon, "chbank": chbank, "za": za, "ccba": ccba,
    "hsbc": headline_only, "dbs": headline_only,
}
