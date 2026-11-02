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


REVEAL_JS = """() => document.querySelectorAll('table').forEach(t => {
  for (let e = t; e && e !== document.body; e = e.parentElement) {
    const cs = getComputedStyle(e);
    if (cs.display === 'none') e.style.setProperty('display', 'block', 'important');
    if (cs.visibility === 'hidden') e.style.setProperty('visibility', 'visible', 'important');
  }
})"""


def fetch_browser(urls, reveal=()):
    """Render pages with Playwright; returns {url: text or Exception}.
    URLs in `reveal` keep their rate tables in closed pop-ups: un-hide them before reading."""
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
                    if url in reveal:
                        await page.evaluate(REVEAL_JS)
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


def join_pages(main, extra):
    """Main page decides success; a failed extra page stays as an empty slot so page n keeps URL n."""
    if not isinstance(main, str):
        return main
    return f"\n{parsers.PAGE_SEP}\n".join([main] + [t if isinstance(t, str) else "" for t in extra])


def hkma_records(url):
    """HKMA's gateway sometimes answers 405 to one query form; try a few, newest first."""
    import requests
    base = url.split("?")[0]
    key = "end_of_date" if "daily-monetary" in base else "end_of_day"
    last = None
    for q in (url, f"{base}?pagesize=5&sortby={key}&sortorder=desc", base):
        for attempt in range(2):
            try:
                r = requests.get(q, timeout=30)
                r.raise_for_status()
                recs = r.json()["result"]["records"]
                return sorted(recs, key=lambda x: x.get(key) or "", reverse=True)
            except Exception as e:  # noqa: BLE001
                last = e
    raise last


HKAB_URL = "https://www.hkab.org.hk/api/hibor"


def parse_hkab(j):
    """HKAB's official daily HIBOR fixing (published ~11:15am each business day)."""
    keys = {"ir_overnight": "Overnight", "ir_1w": "1 Week", "ir_1m": "1 Month",
            "ir_3m": "3 Months", "ir_6m": "6 Months", "ir_12m": "12 Months"}
    vals = {k: j.get(v) for k, v in keys.items()}
    if not all(isinstance(v, (int, float)) for v in vals.values()):
        raise ValueError("incomplete HKAB fixing")
    date = f"{int(j['year']):04d}-{int(j['month']):02d}-{int(j['day']):02d}"
    return {"date": date, **vals, "source": "HKAB"}


def fetch_hibor():
    import requests
    try:
        r = requests.get(HKAB_URL, timeout=30, headers={"User-Agent": UA})
        r.raise_for_status()
        return parse_hkab(r.json())
    except Exception as e:  # noqa: BLE001
        print("HKAB HIBOR failed, trying HKMA:", e, file=sys.stderr)
    recs = hkma_records(HIBOR_URL)
    for rec in recs:
        vals = {k: rec.get(k) for k in ("ir_overnight", "ir_1w", "ir_1m", "ir_3m", "ir_6m", "ir_12m")}
        if all(isinstance(v, (int, float)) for v in vals.values()):
            return merge_daily_hibor({"date": rec["end_of_day"], **vals, "source": "HKMA"})
    raise ValueError("no complete HIBOR record")


def merge_daily_hibor(h):
    """Overlay HKMA daily overnight / 1M fixing when newer than the monthly-bulletin record."""
    try:
        recs = hkma_records(HIBOR_DAILY_URL)
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
    today = fetched_at[:10]

    def live(o):
        return not o.get("promo_end") or o["promo_end"] >= today

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
        urls = [b["url"], *b.get("extra", [])]
        for o in got:
            page = o.pop("page", 0)
            o["source_url"] = urls[page] if page < len(urls) else b["url"]
            o["promo_end"] = o.get("promo_end") or promo_end(o.get("conditions_text_zh") or "")
        parsed = len(got)
        got = [o for o in got if live(o)]
        if parsed and not got:
            st.update(status="ok", offer_count=0, last_ok=fetched_at, error="所有推廣已過截止日")
            status.append(st)
            continue
        prev_live = [o for o in prev_offers.get(bid, []) if live(o)]
        if got and len(got) < 0.3 * len(prev_live):
            err = f"只抽到 {len(got)} 條（上次 {len(prev_live)} 條），當網頁未載完"
            got = []
        if got:
            for i, o in enumerate(got):
                o["id"] = f"{bid}-{i}"
                o["fetched_at"] = fetched_at
                o["status"] = "ok"
            offers += got
            st.update(status="ok", offer_count=len(got), last_ok=fetched_at, error=err)
        elif [o for o in prev_offers.get(bid, []) if live(o)]:
            old = [dict(o, status="stale") for o in prev_offers[bid] if live(o)]
            offers += old
            st.update(status="stale", offer_count=len(old), error=err or "0 offers parsed")
        else:
            st.update(status="error", error=err or "0 offers parsed")
        status.append(st)
    return offers, status


STALE_ALERT_HOURS = 72


def health(status, offers, hibor, previous, fetched_at):
    """Summary for data/health.json; non-empty `alerts` makes the workflow fail so GitHub emails the owner."""
    from datetime import datetime
    now = datetime.fromisoformat(fetched_at)
    alerts = []
    for s in status:
        if s["status"] in ("stale", "error"):
            last = s.get("last_ok")
            hours = (now - datetime.fromisoformat(last)).total_seconds() / 3600 if last else None
            if hours is None or hours > STALE_ALERT_HOURS:
                since = f"{last[:10]} 之後" if last else "從來"
                alerts.append(f"{s['bank_id']} {since}冇抓到（{s.get('error') or s['status']}）")
    before = len((previous or {}).get("offers", []))
    if before and len(offers) < before * 0.7:
        alerts.append(f"利率數目由 {before} 跌到 {len(offers)}")
    hd = (hibor or {}).get("date")
    if not hd or (now.date() - datetime.fromisoformat(hd).date()).days > 5:
        alerts.append(f"HIBOR 停咗喺 {hd}")
    count = lambda k: sum(1 for s in status if s["status"] == k)  # noqa: E731
    return {"generated_at": fetched_at, "offers": len(offers), "ok": count("ok"), "stale": count("stale"),
            "error": count("error"), "headline": count("headline"), "unsupported": count("unsupported"),
            "hibor_date": hd, "alerts": alerts,
            "problems": [{k: s.get(k) for k in ("bank_id", "status", "last_ok", "error")}
                         for s in status if s["status"] in ("stale", "error")]}


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
        live = [b for b in bl if b["parser"]]
        br = [u for b in live if b["method"] == "browser" for u in [b["url"], *b["extra"]]]
        got = fetch_browser(br, {u for b in live if b.get("reveal") for u in [b["url"], *b["extra"]]})
        for b in live:
            for u in [b["url"], *b["extra"]]:
                if b["method"] == "static":
                    try:
                        got[u] = fetch_static(u)
                    except Exception as e:  # noqa: BLE001
                        got[u] = e
            texts[b["id"]] = join_pages(got.get(b["url"]), [got.get(u) for u in b["extra"]])
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
    with open(os.path.join(a.out, "health.json"), "w", encoding="utf-8") as f:
        json.dump(health(status, offers, hibor, previous, fetched_at), f, ensure_ascii=False, indent=1)
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
