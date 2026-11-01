"""Shared helpers: tenor / currency / rate parsing and offer building."""
import re

CURRENCIES = {
    "港元": "HKD", "港幣": "HKD", "HKD": "HKD",
    "美元": "USD", "美金": "USD", "USD": "USD",
    "人民幣": "CNH", "CNY": "CNH", "CNH": "CNH",
    "英鎊": "GBP", "英磅": "GBP", "GBP": "GBP",
    "澳元": "AUD", "澳洲元": "AUD", "AUD": "AUD",
    "加元": "CAD", "加拿大元": "CAD", "CAD": "CAD",
    "紐元": "NZD", "紐西蘭元": "NZD", "NZD": "NZD",
    "歐羅": "EUR", "歐元": "EUR", "EUR": "EUR",
    "日圓": "JPY", "日元": "JPY", "JPY": "JPY",
    "新加坡元": "SGD", "SGD": "SGD",
    "瑞士法郎": "CHF", "CHF": "CHF",
}
DAY_BASIS_365 = {"HKD", "GBP", "SGD"}

_CN = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6,
       "七": 7, "八": 8, "九": 9, "十": 10, "十二": 12, "十八": 18,
       "二十四": 24, "三十六": 36}


def cn_num(s):
    s = s.strip()
    if s.isdigit():
        return int(s)
    return _CN.get(s)


def currency(token):
    t = re.sub(r"\s+", "", token or "")
    t = re.sub(r"[（(].*$", "", t)
    return CURRENCIES.get(t)


def tenor(token):
    """Return (months, days) for a tenor label, or None."""
    t = re.sub(r"\s+", "", token or "")
    if t == "一年半":
        return (18, None)
    m = re.fullmatch(r"(\d+|[一二兩三四五六七八九十]+)(天|日|星期|週|周|個月|月|年)", t)
    if not m:
        return None
    n = cn_num(m.group(1))
    if not n:
        return None
    unit = m.group(2)
    if unit in ("天", "日"):
        return (None, n)
    if unit in ("星期", "週", "周"):
        return (None, 7 * n)
    if unit == "年":
        return (12 * n, None)
    return (n, None)


def rate(token):
    """Parse '2.40%', '0.27', '3%' → float; '-' / '--' → None."""
    t = (token or "").strip().replace("p.a.", "").strip()
    m = re.fullmatch(r"(\d{1,2}(?:\.\d+)?)\s*%?", t)
    return float(m.group(1)) if m else None


def tokens(text, start=None, end=None):
    """Split text into stripped non-empty cells (tabs + newlines), optionally
    restricted to the first section between `start` and `end` markers."""
    if start:
        i = text.find(start)
        if i < 0:
            return []
        text = text[i + len(start):]
    if end:
        j = text.find(end)
        if j >= 0:
            text = text[:j]
    out = []
    for line in text.splitlines():
        for cell in line.split("\t"):
            c = cell.strip()
            if c:
                out.append(c)
    return out


def rows(text, start=None, end=None):
    """Lines split by tab (cells stripped), for tab-rendered tables."""
    if start:
        i = text.find(start)
        if i < 0:
            return []
        text = text[i + len(start):]
    if end:
        j = text.find(end)
        if j >= 0:
            text = text[:j]
    out = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.split("\t")]
        if any(cells):
            out.append(cells)
    return out


def amount(s):
    """'HKD50,000' / '5萬' / '1仟' → number."""
    t = (s or "").replace(",", "").replace(" ", "")
    m = re.search(r"(\d+(?:\.\d+)?)(萬|仟|千)?", t)
    if not m:
        return None
    v = float(m.group(1))
    mult = {"萬": 10000, "仟": 1000, "千": 1000}.get(m.group(2), 1)
    return int(v * mult)


def offer(bank, cur, ten, r, *, min_amount=None, max_amount=None,
          new_customer=False, new_funds=False, tier=None, channel=None,
          fx_conversion=False, up_to=False, board=False, text=""):
    months, days = ten
    return {
        "bank_id": bank,
        "currency": cur,
        "tenor_months": months,
        "tenor_days": days,
        "rate_pa": r,
        "day_basis": 365 if cur in DAY_BASIS_365 else 360,
        "min_amount": min_amount,
        "max_amount": max_amount,
        "conditions": {
            "new_customer": new_customer,
            "new_funds": new_funds,
            "tier": tier,
            "channel": channel,
            "fx_conversion": fx_conversion,
            "up_to": up_to,
            "board": board,
        },
        "conditions_text_zh": text,
    }


def sane(o):
    r = o.get("rate_pa")
    if r is None or not (0 < r < 25):
        return False
    m, d = o.get("tenor_months"), o.get("tenor_days")
    if m is not None and not (1 <= m <= 60):
        return False
    if d is not None and not (1 <= d <= 1830):
        return False
    return m is not None or d is not None


def snippet(text, marker, n=220):
    i = text.find(marker)
    if i < 0:
        return ""
    return re.sub(r"\s+", " ", text[i:i + n]).strip()
