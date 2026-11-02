"""One-off: rebuild past months of history from Wayback Machine snapshots of the same official pages.

python backfill.py --since 2025-01 [--banks bochk,hangseng]
Writes data/history/<date>.json (marked "source": "wayback") without overwriting real daily files.
"""
import argparse, json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
import requests
import parsers
from banks import banks
from common import sane

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(HERE, "..", "data", "history")
CDX = "https://web.archive.org/cdx/search/cdx"
HIBOR = ("https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/"
         "er-ir/hk-interbank-ir-daily?pagesize=1000&sortby=end_of_day&sortorder=desc&offset={}")


def snapshots(url, since):
    import json, subprocess, urllib.parse
    q = urllib.parse.urlencode({"url": url, "from": since.replace("-", ""), "output": "json",
                                "fl": "timestamp", "filter": "statuscode:200", "collapse": "timestamp:8"})
    for attempt in range(3):
        try:
            r = subprocess.run(["curl", "-s", "--max-time", "60", f"{CDX}?{q}"], capture_output=True, timeout=70)
            rows = json.loads(r.stdout or b"[]")
            return [x[0] for x in rows[1:]]
        except Exception:
            time.sleep(5)
    return []


def fetch(url, ts):
    # curl: Python sockets get refused by web.archive.org on some networks
    import subprocess
    for attempt in range(3):
        try:
            r = subprocess.run(["curl", "-sL", "--max-time", "90", f"https://web.archive.org/web/{ts}id_/{url}"],
                               capture_output=True, timeout=100)
            html = r.stdout.decode("utf-8", "replace")
            if r.returncode == 0 and len(html) > 1000:
                return html
        except Exception:
            pass
        time.sleep(5)
    return None


def render(html):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.route("**/*", lambda route: route.abort() if route.request.resource_type in ("image", "font", "media") else route.continue_())
        try:
            pg.set_content(html, wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(1500)
            return pg.inner_text("body")
        except Exception:
            return ""
        finally:
            b.close()


def hibor_series():
    out = {}
    for off in (0, 1000):
        try:
            recs = requests.get(HIBOR.format(off), timeout=60).json()["result"]["records"]
        except Exception:
            break
        for r in recs:
            vals = {k: r.get(k) for k in ("ir_overnight", "ir_1w", "ir_1m", "ir_3m", "ir_6m", "ir_12m")}
            if all(isinstance(v, (int, float)) for v in vals.values()):
                out[r["end_of_day"]] = {"date": r["end_of_day"], **vals, "source": "HKMA"}
    return out


def hibor_on(series, day):
    ks = [k for k in series if k <= day]
    return series[max(ks)] if ks else None


def render_live(url, ts):
    """Open the archived page in a real browser so its own JS (tables loaded by XHR) runs."""
    from playwright.sync_api import sync_playwright
    for attempt in range(3):
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(locale="zh-HK")
            pg.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "font", "media") else r.continue_())
            try:
                pg.goto(f"https://web.archive.org/web/{ts}/{url}", timeout=90000, wait_until="domcontentloaded")
                try:
                    pg.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                pg.wait_for_timeout(4000)
                text = pg.inner_text("body")
                if len(text) > 800:
                    return text
            except Exception:
                pass
            finally:
                b.close()
        time.sleep(10 * (attempt + 1))
    return ""


def parse(b, text):
    try:
        return [o for o in parsers.PARSERS[b["parser"]](text) if sane(o)]
    except Exception:
        return []


def one_bank(b, since):
    got = {}
    for ts in snapshots(b["url"], since):
        offers = parse(b, render_live(b["url"], ts))
        if not offers:
            html = fetch(b["url"], ts)
            offers = parse(b, render(html)) if html else []
        day = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"
        print(b["id"], day, len(offers), flush=True)
        if offers:
            got[day] = offers
    return b["id"], got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2025-01")
    ap.add_argument("--banks", default="")
    a = ap.parse_args()
    wanted = set(filter(None, a.banks.split(",")))
    bl = [b for b in banks() if b["parser"] and parsers.PARSERS[b["parser"]] is not parsers.headline_only
          and (not wanted or b["id"] in wanted)]
    series = hibor_series()
    with ThreadPoolExecutor(3) as ex:
        results = list(ex.map(lambda b: one_bank(b, a.since), bl))
    os.makedirs(HIST, exist_ok=True)
    days = {}
    for bid, got in results:
        for day, offers in got.items():
            days.setdefault(day, []).extend(offers)
    written = 0
    for day, offers in sorted(days.items()):
        p = os.path.join(HIST, f"{day}.json")
        rows = [[o["bank_id"], o["currency"], o["tenor_months"], o["tenor_days"], o["rate_pa"],
                 o["min_amount"], int(o["conditions"]["new_funds"]), int(o["conditions"]["new_customer"])]
                for o in offers]
        if os.path.exists(p):
            h = json.load(open(p, encoding="utf-8"))
            have = {r[0] for r in h["offers"]}
            h["offers"] += [r for r in rows if r[0] not in have]
        else:
            h = {"date": day, "hibor": hibor_on(series, day), "source": "wayback", "offers": rows}
        json.dump(h, open(p, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        written += 1
    alld = sorted(x[:-5] for x in os.listdir(HIST) if x.endswith(".json"))
    json.dump({"days": alld[-400:]}, open(os.path.join(HIST, "..", "history_index.json"), "w"))
    print("DONE days written:", written, file=sys.stderr)


if __name__ == "__main__":
    main()
