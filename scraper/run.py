"""Scrape all banks → data/rates.json + data/history/<date>.json.

  python run.py                # live fetch
  python run.py --fixtures     # parse saved fixtures (offline, for tests)
"""
import argparse
import datetime as dt
import json
import os
import sys

import parsers
from banks import banks
from common import sane

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
HKT = dt.timezone(dt.timedelta(hours=8))
HIBOR_DAILY_URL = ("https://api.hkma.gov.hk/public/market-data-and-statistics/"
                   "daily-monetary-statistics/daily-figures-interbank-liquidity"
                   "?pagesize=5&sortby=end_of_date&sortorder=desc")
HIBOR_URL = ("https://api.hkma.gov.hk/public/market-data-and-statistics/"
             "monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily"
             "?pagesize=5&sortby=end_of_day&sortorder=desc")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124 Safari/537.36")


def now_iso():
    return dt.datetime.now(HKT).replace(microsecond=0).isoformat()


def fetch_static(url):
    import requests
    from bs4 import BeautifulSoup
    r = requests.get(url, headers={"User-Agent": UA}, timeout=40)
    r.raise_for_status()
    return BeautifulSoup(r.content, "lxml").get_text("\n")


def fetch_browser(urls):
    """Render pages with Playwright; returns {url: text or Exception}."""
    import asyncio
    from playwright.async_api import async_playwright

    async def one(b, url, sem, out):
        async with sem:
            for attempt in range(3):
                ctx = await b.new_context(locale="zh-HK", user_agent=UA)
                page = await ctx.new_page()
                try:
                    await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                    try:
                        await page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(3000 + 4000 * attempt)
                    out[url] = await page.inner_text("body")
                except Exception as e:  # noqa: BLE001
                    out[url] = e
                await ctx.close()
                if isinstance(out[url], str) and len(out[url]) > 800:
                    break

    async def main():
        out = {}
        async with async_playwright() as pw:
            b = await pw.chromium.launch()
            sem = asyncio.Semaphore(5)
            await asyncio.gather(*[one(b, u, sem, out) for u in urls])
            await b.close()
        return out

    return asyncio.run(main())


def fetch_hibor():
    import requests
    r = requests.get(HIBOR_URL, timeout=30)
    r.raise_for_status()
    recs = r.json()["result"]["records"]
    for rec in recs:
        vals = {k: rec.get(k) for k in ("ir_overnight", "ir_1w", "ir_1m", "ir_3m", "ir_6m", "ir_12m")}
        if all(isinstance(v, (int, float)) for v in vals.values()):
            return merge_daily_hibor({"date": rec["end_of_day"], **vals, "source": "HKMA"})
    raise ValueError("no complete HIBOR record")


def merge_daily_hibor(h):
    """Overlay HKMA daily overnight / 1M fixing when newer than the monthly-bulletin record."""
    import requests
    try:
        r = requests.get(HIBOR_DAILY_URL, timeout=30)
        r.raise_for_status()
        recs = r.json()["result"]["records"]
    except Exception as e:  # monthly data is still valid on its own
        print("daily HIBOR failed:", e, file=sys.stderr)
        return h
    return apply_daily_hibor(h, recs)


def apply_daily_hibor(h, recs):
    for rec in recs:
        on, m1 = rec.get("hibor_overnight"), rec.get("hibor_fixing_1m")
        if isinstance(on, (int, float)) and isinstance(m1, (int, float)):
            if rec["end_of_date"] > h["date"]:
                return {**h, "terms_date": h["date"], "date": rec["end_of_date"],
                        "ir_overnight": on, "ir_1m": m1}
            break
    return h


def promo_end(text):
    """Latest '至2026年12月31日' / '至2026-12-31' style end date in the condition text."""
    import re
    ds = [f"{y}-{int(m):02d}-{int(d):02d}" for y, m, d in
          re.findall(r"(?:至|截至|到)\s*(20\d\d)\s*[年/-]\s*(\d{1,2})\s*[月/-]\s*(\d{1,2})", text)]
    return max(ds) if ds else None


def build(bank_list, texts, previous, fetched_at):
    """Pure merge step (tested): parse texts, fall back to previous offers."""
    prev_offers = {}
    for o in (previous or {}).get("offers", []):
        prev_offers.setdefault(o["bank_id"], []).append(o)
    prev_status = {s["bank_id"]: s for s in (previous or {}).get("bank_status", [])}
    offers, status = [], []
    for b in bank_list:
        bid = b["id"]
        st = {"bank_id": bid, "status": "unsupported", "offer_count": 0,
              "last_ok": prev_status.get(bid, {}).get("last_ok"), "error": None,
              "headline_max": None}
        text = texts.get(bid)
        if b["parser"] is None:
            st["error"] = "網頁冇可讀利率表，請去官網睇"
            status.append(st)
            continue
        got, err = [], None
        if isinstance(text, Exception):
            err = f"fetch: {type(text).__name__}: {str(text)[:120]}"
        elif text is None:
            err = "fetch: no text"
        else:
            st["headline_max"] = parsers.headline(text)
            try:
                raw = parsers.PARSERS[b["parser"]](text)
                bad = [o for o in raw if not sane(o)]
                got = [o for o in raw if sane(o)]
                if bad:
                    err = f"rejected {len(bad)} invalid offers"
            except Exception as e:  # noqa: BLE001
                err = f"parse: {type(e).__name__}: {e}"
        if parsers.PARSERS[b["parser"]] is parsers.headline_only:
            st.update(status="headline", error="網頁只寫「高達」利率，冇分年期表")
            status.append(st)
            continue
        if got:
            for i, o in enumerate(got):
                o["id"] = f"{bid}-{i}"
                o["source_url"] = b["url"]
                o["fetched_at"] = fetched_at
                o["status"] = "ok"
                o["promo_end"] = o.get("promo_end") or promo_end(o.get("conditions_text_zh") or "")
            offers += got
            st.update(status="ok", offer_count=len(got), last_ok=fetched_at, error=err)
        elif prev_offers.get(bid):
            old = [dict(o, status="stale") for o in prev_offers[bid]]
            offers += old
            st.update(status="stale", offer_count=len(old), error=err or "0 offers parsed")
        else:
            st.update(status="error", error=err or "0 offers parsed")
        status.append(st)
    return offers, status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", action="store_true")
    ap.add_argument("--out", default=DATA)
    a = ap.parse_args()
    bl = banks()
    rates_path = os.path.join(a.out, "rates.json")
    previous = json.load(open(rates_path, encoding="utf-8")) if os.path.exists(rates_path) else None
    fetched_at = now_iso()
    texts = {}
    if a.fixtures:
        for b in bl:
            p = os.path.join(HERE, "fixtures", f"{b['id']}.txt")
            if os.path.exists(p):
                texts[b["id"]] = open(p, encoding="utf-8").read()
    else:
        br = {b["url"]: b["id"] for b in bl if b["parser"] and b["method"] == "browser"}
        for url, t in fetch_browser(list(br)).items():
            texts[br[url]] = t
        for b in bl:
            if b["parser"] and b["method"] == "static":
                try:
                    texts[b["id"]] = fetch_static(b["url"])
                except Exception as e:  # noqa: BLE001
                    texts[b["id"]] = e
    offers, status = build(bl, texts, previous, fetched_at)
    try:
        hibor = fetch_hibor()
    except Exception as e:  # noqa: BLE001
        print("HIBOR failed:", e, file=sys.stderr)
        hibor = (previous or {}).get("hibor")
    meta = [{k: b[k] for k in ("id", "name_zh", "short", "kind", "color", "url")} for b in bl]
    doc = {"schema": 1, "generated_at": fetched_at, "hibor": hibor, "banks": meta,
           "offers": offers, "bank_status": status}
    os.makedirs(os.path.join(a.out, "history"), exist_ok=True)
    with open(rates_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    day = fetched_at[:10]
    hist = {"date": day, "hibor": hibor, "offers": [
        [o["bank_id"], o["currency"], o["tenor_months"], o["tenor_days"], o["rate_pa"],
         o["min_amount"], int(o["conditions"]["new_funds"]), int(o["conditions"]["new_customer"])]
        for o in offers if o["status"] == "ok"]}
    with open(os.path.join(a.out, "history", f"{day}.json"), "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, separators=(",", ":"))
    days = sorted(x[:-5] for x in os.listdir(os.path.join(a.out, "history")) if x.endswith(".json"))
    with open(os.path.join(a.out, "history_index.json"), "w", encoding="utf-8") as f:
        json.dump({"days": days[-400:]}, f)
    for s in status:
        print(f"{s['bank_id']:11s} {s['status']:11s} {s['offer_count']:4d} {s['error'] or ''}")
    print("offers:", len(offers), "hibor:", (hibor or {}).get("date"))


if __name__ == "__main__":
    main()
