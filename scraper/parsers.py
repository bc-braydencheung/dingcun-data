"""Per-bank parsers. Each takes page text and returns a list of offers."""
import re

from common import (CURRENCIES, amount, currency, offer, rate, rows, snippet, tenor,
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


PAGE_SEP = "=====PAGE====="


def pages(text):
    return [t for t in text.split(PAGE_SEP)]


def on_page(offers, i):
    """Remember which fetched page (0 = main URL, n = n-th extra URL) an offer came from."""
    for o in offers:
        o["page"] = i
    return offers


def ccba(text):
    out = []
    main, *extra = pages(text)
    for start, nc_tier, ch in (("全新「貴賓理財」客戶定期存款推廣", "貴賓理財（全新客戶）", "分行"),
                               ("全新「智選理財」及一般個人銀行客戶定期存款推廣", None, "e賬戶服務")):
        toks = tokens(main, start, "了解更多")
        note = " ".join(toks[:2])[:220]
        curs, ten = [], None
        for i, t in enumerate(toks):
            cs = [currency(x) for x in t.split("/") if currency(x)]
            if cs:
                curs += cs
            elif tenor(t):
                ten = tenor(t)
            elif t == "高達" and i + 1 < len(toks) and ten and curs:
                v = rate(toks[i + 1])
                if v:
                    for c in curs:
                        out.append(offer("ccba", c, ten, v, new_customer=True, new_funds=True,
                                         tier=nc_tier, channel=ch, up_to=True, text=note))
                curs = []
    for pi, page in enumerate(extra, 1):
        # 網上新資金定存優惠: confirmed rates with minimum amounts
        toks = tokens(page, "年利率*", "以上新資金年利率")
        head = re.sub(r"\s+", "", snippet(page, "由20", 120))
        note = (head.split("，")[0] + "，經手機銀行／網上銀行／智慧櫃員機以新資金開立").strip()
        cur, mn, ten = None, None, None
        for t in toks:
            if currency(t):
                cur, mn = currency(t), None
            elif cur and mn is None and re.search(r"\d", t) and "或以上" in t:
                mn = amount(t)
            elif tenor(t):
                ten = tenor(t)
            elif cur and ten and rate(t):
                out += on_page([offer("ccba", cur, ten, rate(t), min_amount=mn, new_funds=True,
                                      channel="網上／手機銀行", text=note)], pi)
                cur = None
    return out


def icbcasia(text):
    """ICBC (Asia) promo pages: online TD table (by customer class) + new-funds branch promos."""
    out = []
    for pi, page in enumerate(pages(text)):
        new_customer = "全新客戶" in page[:3000] and "全新客戶港幣新資金" in page
        branch = "到分行" in page
        intro = snippet(page, "客戶於推廣期內", 200) or snippet(page, "全新客戶於推廣期內", 200) \
            or snippet(page, "個人客戶於辦公時間", 200)
        period = snippet(page, "推廣期：", 40)
        note = (intro + (" " + period if period else "")).strip()
        tenors, cur, tier, pending, cat = [], None, None, "", None
        for line in page.splitlines():
            cells = [c.strip() for c in line.split("\t") if c.strip()]
            if not cells:
                continue
            if cells[0] in ("工銀財富／理財金客戶", "e時代／綜合客戶") and len(cells) == 1:
                tier = "工銀財富／理財金" if cells[0].startswith("工銀") else None
                continue
            ts = [tenor(c) for c in cells if tenor(c)]
            if ts and len(ts) >= len(cells) - 2:
                tenors, cur, pending, cat = ts, None, "", tier
                continue
            if not tenors:
                continue
            n = 0
            while n < len(cells) and re.fullmatch(r"\d{1,2}\.\d+%", cells[-1 - n]):
                n += 1
            if n != len(tenors):
                pending = (pending + " " + " ".join(cells)).strip() if len(cells) <= 2 else ""
                continue
            label = (pending + " " + " ".join(cells[:-n])).strip()
            pending = ""
            for k, c in CURRENCIES.items():
                if k in label and len(k) > 1:
                    cur = c
                    break
            if "只適用於工銀財富客戶" in label:
                pass
            elif "工銀財富客戶" in label and "／" not in label.split("工銀財富客戶")[0][-3:]:
                cat = "工銀財富"
            elif "工銀財富／理財金客戶" in label:
                cat = "工銀財富／理財金"
            elif "零售銀行個人客戶" in label:
                cat = None
            row_tier = "工銀財富" if "只適用於工銀財富客戶" in label else cat
            nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]{3,}", label)]
            mn = mx = None
            if "上限" in label and "最低" in label and len(nums) >= 2:
                mx, mn = nums[0], nums[1]
            elif "以下" in label and len(nums) >= 2:
                mn, mx = nums[0], nums[1] - 1
            elif nums:
                mn = nums[0]
            if not cur:
                continue
            for ten, cell in zip(tenors, cells[-n:]):
                out += on_page([offer("icbcasia", cur, ten, rate(cell), min_amount=mn, max_amount=mx,
                                      new_customer=new_customer, new_funds="新資金" in page[:1500] and branch,
                                      tier=row_tier, channel="分行" if branch else "網上／手機銀行",
                                      text=note)], pi)
    return out


def bea(text):
    """BEA board rates (港元 + 外幣 pages): per-currency tables, first column = minimum amount."""
    out = []
    for pi, page in enumerate(pages(text)):
        tenors, cur = None, None
        for line in page.splitlines():
            cells = [c.strip() for c in line.split("\t") if c.strip()]
            if not cells:
                continue
            if "戶口種類" in cells[0] or cells[0] == "貨幣":
                tenors = None
                continue
            if all(tenor(c) or "隔夜" in c or "通知" in c for c in cells) and any(tenor(c) for c in cells):
                tenors = [tenor(c) for c in cells]
                continue
            if len(cells) == 1 and currency(cells[0]):
                cur = currency(cells[0])
                continue
            if tenors is None:
                continue
            if currency(cells[0]):
                cur, cells = currency(cells[0]), cells[1:]
            if cells and cells[0] == "存款":
                cells = cells[1:]
            if not cells or not re.fullmatch(r"[\d,]+", cells[0]) or len(cells) - 1 != len(tenors) or not cur:
                continue
            mn = int(cells[0].replace(",", ""))
            for ten, cell in zip(tenors, cells[1:]):
                v = rate(cell)
                if ten and v:
                    out += on_page([offer("bea", cur, ten, v, min_amount=mn, board=True, text="牌價")], pi)
    return out


def hsbc(text):
    """Board time-deposit rates page: one table per currency, first column = lowest tier."""
    out = []
    lines = text.splitlines()
    cur, mn = None, None
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.split("\t")]
        if cells[0] == "存款期":
            cur, mn = None, None
            for cand in [c for c in cells[1:] if c] + [l.strip() for l in lines[i + 1:i + 4]]:
                m = re.search(r"([\d,]+)\s*(\D+)$", cand) or re.search(r"^(\D+?)\s*([\d,]+)", cand)
                if m:
                    a, b = m.groups()
                    c, n = (currency(b), a) if a[0].isdigit() else (currency(a), b)
                    if c:
                        cur, mn = c, int(n.replace(",", ""))
                        break
            continue
        if not cur:
            continue
        ten = tenor(cells[0])
        if ten and len(cells) > 1:
            v = rate(cells[1])
            if v:
                out.append(offer("hsbc", cur, ten, v, min_amount=mn, board=True,
                                 text="滙豐定期存款牌價（最低存款級別）"))
    return out


def citi(text):
    """'全新客戶定期存款優惠' table: new customers, new funds, branch / RM only."""
    out = []
    note = snippet(text, "以下港元/美元/人民幣定期存款年利率優惠", 400)
    cur, ten = None, None
    for cells in rows(text, "貨幣\t全新客戶", "\n\n\n"):
        if currency(cells[0]):
            cur, cells = currency(cells[0]), cells[1:]
        if not cur or len(cells) < 3:
            continue
        tier = cells[0].replace(" 客戶", "").strip()
        vals = [rate(c) for c in cells[1:3]]
        t = next((tenor(c) for c in cells if tenor(c)), None) or ten
        ten = t
        amt = re.findall(r"HK\$([\d,]+)", cells[-1])
        if not t or not all(vals):
            continue
        out.append(offer("citi", cur, t, vals[1], new_customer=True, new_funds=True, tier=tier,
                         channel="分行／客戶經理（唔適用網上）",
                         min_amount=int(amt[0].replace(",", "")) if amt else None,
                         max_amount=int(amt[1].replace(",", "")) if len(amt) > 1 else None,
                         text=note + "（只做到條款 a 嘅利率；再有 HK$78,000 投資／保險結存可高 0.2%）"))
    return out


def shacom(text):
    out = []
    end = None
    m = re.search(r"由(\d{4})年(\d{1,2})月(\d{1,2})日起", text)
    mins_branch = {"HKD": 500000, "CNH": 450000, "USD": 65000, "GBP": 50000}
    mins_online = {"HKD": 1000, "USD": 5000, "CNH": 10000, "GBP": 5000}
    for start, kw in (("新資金定期存款年利率優惠\n", dict(new_funds=True, channel="分行", mins=mins_branch)),
                      ("個人網上銀行 / 流動銀行定期存款年利率優惠\n", dict(channel="網上／流動銀行", mins=mins_online))):
        i = text.rfind(start, 0, text.find("特別優惠條款")) if "特別優惠條款" in text else text.rfind(start)
        sec = text[i:]
        tens = None
        for cells in rows(sec)[:12]:
            ts = [tenor(c) for c in cells]
            if sum(1 for t in ts if t) >= 3:
                tens = ts
                continue
            c = currency(cells[0]) if cells else None
            if tens and c:
                for t, cell in zip(tens, cells):
                    v = rate(cell) if t else None
                    if v:
                        out.append(offer("shacom", c, t, v, min_amount=kw["mins"].get(c),
                                         new_funds=kw.get("new_funds", False), channel=kw["channel"],
                                         text=snippet(sec, "由", 160)))
            elif tens and out and not c:
                break
    return out


def dbs(text):
    """星展: registration 3-month new-funds promo + 網上定存優惠 table (default tab 港幣／新資金)."""
    out = []
    for pi, page in enumerate(pages(text)):
        page = page.replace("\u200b", "")
        if "網上定存優惠" not in page:
            continue
        lines = [l for l in page.splitlines()]
        reg = snippet(page, "成功以合資格新資金開立", 80)
        heads = None
        for i, line in enumerate(lines):
            cells = [c.strip() for c in line.split("\t") if c.strip()]
            if cells[:2] == ["港元", "美元"]:
                heads = ["HKD", "USD"]
                continue
            if heads and cells and tenor(cells[0]) and len(cells) == 3:
                for cur, cell, mn in zip(heads, cells[1:], (500000, 65000)):
                    if rate(cell):
                        out += on_page([offer("dbs", cur, tenor(cells[0]), rate(cell), min_amount=mn,
                                              new_funds=True, channel="網上登記", text="網上登記後" + reg)], pi)
                heads = None
                continue
            if cells and cells[0] == "存款期" and "優惠編號" in cells:
                m = re.search(r"存款額：港幣([\d,]+)", page)
                mn = amount(m.group(1)) if m else None
                for row in lines[i + 1:]:
                    rc = [c.strip() for c in row.split("\t") if c.strip()]
                    if len(rc) < 5 or not tenor(rc[0]):
                        break
                    ten = tenor(rc[0])
                    note = "網上定存優惠（新資金），網上／手機銀行開立"
                    out += on_page([offer("dbs", "HKD", ten, rate(rc[1]), min_amount=mn, new_funds=True,
                                          channel="網上／手機銀行", text=note)], pi)
                    if rate(rc[3]) != rate(rc[1]):
                        out += on_page([offer("dbs", "HKD", ten, rate(rc[3]), min_amount=mn, new_funds=True,
                                              tier="星展豐盛理財／私人客戶", channel="網上／手機銀行",
                                              text=note)], pi)
                break
    return out


HKD_PER_USD = 7.75  # peg strong side: the USD figure needed to reach an HKD-equivalent threshold


def _hkd_band(label):
    nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]{3,}", label)]
    if not nums:
        return None, None
    if "或以上" in label or len(nums) == 1:
        return nums[0], None
    return nums[0], nums[1] - 1 if "以下" in label else nums[1]


def dahsing(text):
    """大新 高息定存 promo pages: tables banded by HKD-equivalent amount, VIP / 其他客戶."""
    out = []
    for pi, page in enumerate(pages(text)):
        title = page[:900]
        cur = "USD" if "美元定期存款" in title else "HKD" if "港元定期存款" in title else None
        if not cur:
            continue
        period = snippet(page, "推廣期由", 40)
        tenors, tier, fx = None, None, False
        for line in page.splitlines():
            cells = [c.strip() for c in line.split("\t") if c.strip()]
            if not cells:
                continue
            if cells[0].startswith("VIP"):
                tier, fx = "VIP 銀行服務", False
            elif cells[0].startswith("其他") and "客戶" in cells[0]:
                tier, fx = None, False
            elif "兌換及定期存款優惠" in cells[0]:
                tier, fx = None, True
            elif all(tenor(c) for c in cells):
                tenors = [tenor(c) for c in cells]
            elif tenors and len(cells) == len(tenors) + 1 and re.search(r"\d,\d{3}", cells[0]):
                lo, hi = _hkd_band(cells[0])
                if cur == "USD":
                    lo = lo and -(-lo // HKD_PER_USD)
                    hi = hi and int(hi // HKD_PER_USD)
                note = (f"分行以全新資金開立；存款金額以港元等值計：{cells[0]}" if not fx
                        else f"分行以港元兌換{('美元' if cur == 'USD' else '')}同時開立；金額以港元計：{cells[0]}")
                for ten, cell in zip(tenors, cells[1:]):
                    v = rate(cell)
                    if v:
                        out += on_page([offer("dahsing", cur, ten, v, min_amount=lo and int(lo), max_amount=hi,
                                              new_funds=not fx, fx_conversion=fx, tier=tier, channel="分行",
                                              text=f"{note}。{period}")], pi)
            elif tenors and not re.search(r"\d", cells[0]):
                tenors = None if "上述年利率" in cells[0] else tenors
    return out


def chiyu(text):
    """集友 存款利率 page (港元 default): 定期 board table, columns = amount bands."""
    out = []
    bands = None
    for line in text[text.find("港元定期存款利率表"):].splitlines():
        cells = [c.strip() for c in line.split("\t") if c.strip()]
        if cells and cells[0] == "存款金額":
            bands = [_hkd_band(c) if "以下" not in c or re.search(r"\d.*至|-", c) else (None, amount(c) - 1)
                     for c in cells[1:]]
            continue
        if bands and cells and tenor(cells[0]) and len(cells) == len(bands) + 1:
            for (lo, hi), cell in zip(bands, cells[1:]):
                v = rate(cell)
                if v:
                    out.append(offer("chiyu", "HKD", tenor(cells[0]), v, min_amount=lo, max_amount=hi,
                                     board=True, text="分行牌價"))
        elif bands and cells and not tenor(cells[0]):
            break
    return out


def airstar(text):
    """天星: the deposit page loads /vendor/json/deposit_rate.json; offers link to the page itself."""
    import json
    out = []
    for page in pages(text)[1:]:
        try:
            data = json.loads(page.strip())
        except ValueError:
            continue
        for x in data:
            if x.get("rate_type") != "Time Deposit Rate":
                continue
            cur = currency(x["currency"]["code"])
            for t in x.get("tenors", []):
                ten, v = tenor(t["zh"].replace(" ", "")), rate(t["rate"])
                if cur and ten and v:
                    out.append(offer("airstar", cur, ten, v, board=True, channel="App",
                                     text="天星銀行 App 定期存款標準利率；1,000 起存（多幣種適用）"))
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
    "hsbc": hsbc, "citi": citi, "shacom": shacom, "dbs": dbs, "dahsing": dahsing, "chiyu": chiyu, "airstar": airstar,
    "icbcasia": icbcasia, "bea": bea,
}
