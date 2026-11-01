"""Check every parsed offer against its source text: the rate must literally appear on the page."""
import collections, os, re, sys
import parsers
from banks import banks

HERE = os.path.dirname(os.path.abspath(__file__))


def variants(v):
    s = {f"{v:.2f}", f"{v:.3f}", f"{v:.1f}", f"{v:g}", f"{v:.4f}"}
    return s


def audit(texts):
    rows = []
    for b in banks():
        t = texts.get(b["id"])
        if not t or not b["parser"]:
            continue
        nums = set(re.findall(r"\d+\.\d+", t)) | set(re.findall(r"(\d+)\s*%", t))
        offers = parsers.PARSERS[b["parser"]](t)
        bad = [o for o in offers if not (variants(o["rate_pa"]) & nums)]
        rows.append((b["id"], b["name_zh"], len(offers), len(bad), offers[:3], bad[:3]))
    return rows


def main():
    texts = {}
    for b in banks():
        p = os.path.join(HERE, "fixtures", f"{b['id']}.txt")
        if os.path.exists(p):
            texts[b["id"]] = open(p, encoding="utf-8").read()
    out = ["# 數據核對（每條利率都要喺銀行網頁原文搵到）", "", "| 銀行 | 條數 | 原文搵唔到 | 抽樣 |", "|---|---|---|---|"]
    for bid, name, n, nbad, sample, bad in audit(texts):
        s = "；".join(f"{o['currency']} {o['tenor_months'] or ''}{'月' if o['tenor_months'] else str(o['tenor_days']) + '日'} {o['rate_pa']}%" for o in sample)
        out.append(f"| {name} | {n} | {nbad} | {s} |")
    print("\n".join(out))


if __name__ == "__main__":
    main()
