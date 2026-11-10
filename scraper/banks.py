"""Bank registry. `parser=None` → page not machine-readable yet (link only)."""
BANKS = [
    # id, name, short, kind, colour, url, method, parser
    ("bochk", "中銀香港", "中銀", "traditional", "#B71C1C", "https://www.bochk.com/tc/deposits/promotion/timedeposits.html", "browser", "bochk"),
    ("hsbc", "滙豐銀行", "滙豐", "traditional", "#D32F2F", "https://www.hsbc.com.hk/zh-hk/investments/market-information/hk/deposit-rate/", "browser", "hsbc"),
    ("hangseng", "恒生銀行", "恒生", "traditional", "#00796B", "https://www.hangseng.com/zh-hk/personal/banking/rates/deposit-interest-rates/", "browser", "hangseng"),
    ("sc", "渣打銀行", "渣打", "traditional", "#0277BD", "https://www.sc.com/hk/zh/deposits/online-time-deposit/", "browser", "sc"),
    ("dbs", "星展銀行", "星展", "traditional", "#C62828", "https://www.dbs.com.hk/personal-zh/deposits/time-deposit/default.page", "browser", "dbs"),
    ("ccba", "建行（亞洲）", "建行", "traditional", "#1565C0", "https://www.asia.ccb.com/hongkong_tc/personal/accounts/dep_rates.html", "static", "ccba"),
    ("publicbank", "大眾銀行", "大眾", "traditional", "#AD1457", "https://www.publicbank.com.hk/tc/usefultools/rates/depositinterestrates", "browser", "publicbank"),
    ("fubon", "富邦銀行", "富邦", "traditional", "#00897B", "https://www.fubonbank.com.hk/tc/rates-enquiry.html", "browser", "fubon"),
    ("chbank", "創興銀行", "創興", "traditional", "#6A1B9A", "https://www.chbank.com/tc/personal/banking-services/useful-information/deposit-rates/index.shtml", "browser", "chbank"),
    ("citi", "花旗銀行", "花旗", "traditional", "#1976D2", "https://www.citibank.com.hk/chinese/info/rates.html", "browser", "citi"),
    ("bea", "東亞銀行", "東亞", "traditional", "#C62828", "https://www.hkbea.com/hk-form/?formId=RATE&rateType=hkddr&language=tc#/forms/MISC", "browser", "bea"),
    ("dahsing", "大新銀行", "大新", "traditional", "#E65100", "https://www.dahsing.com/html/tc/deposit/fixed_deposit/usd_fixed_deposit.html", "browser", "dahsing"),
    ("icbcasia", "工銀亞洲", "工銀", "traditional", "#B71C1C", "https://www.icbcasia.com/hk/tc/personal/latest-promotion/online-time-deposit.html", "browser", "icbcasia"),
    ("cncbi", "中信銀行（國際）", "中信", "traditional", "#C2185B", "https://www.cncbinternational.com/personal/deposits/time-deposit/tc/index.jsp", "browser", None),
    ("ocbc", "華僑銀行", "華僑", "traditional", "#D84315", "https://www.ocbc.com.hk/iwov-resources/hk/ocbc/personal/pdf/HKD.pdf", "pdf", "ocbc"),
    ("shacom", "上海商業銀行", "上商", "traditional", "#283593", "https://www.shacombank.com.hk/tch/personal/promotion/fix-rate.jsp", "browser", "shacom"),
    ("chiyu", "集友銀行", "集友", "traditional", "#2E7D32", "https://www.chiyubank.com/wcs/trading-rate/", "browser", "chiyu"),
    ("za", "ZA Bank", "ZA", "virtual", "#00838F", "https://bank.za.group/hk/deposit", "browser", "za"),
    ("mox", "Mox Bank", "Mox", "virtual", "#212121", "https://mox.com/zh/promotions/time-deposit/", "browser", "mox"),
    ("livi", "livi bank", "livi", "virtual", "#F9A825", "https://www.livibank.com/zh_HK/features/livisave.html", "browser", "livi"),
    ("welab", "WeLab Bank", "WeLab", "virtual", "#4527A0", "https://www.welab.bank/zh/feature/gosave_2/", "browser", "welab"),
    ("antbank", "螞蟻銀行（香港）", "螞蟻", "virtual", "#1E88E5", "https://www.antbank.hk/rates?lang=zh_hk", "browser", "antbank"),
    ("paob", "平安壹賬通銀行", "平安", "virtual", "#EF6C00", "https://www.pingandb.com/tc/retail-savings.html", "browser", "paob"),
    ("airstar", "天星銀行", "天星", "virtual", "#5E35B1", "https://www.airstarbank.com/zh-hk/deposit.html", "browser", "airstar"),
    ("fusion", "富融銀行", "富融", "virtual", "#00695C", "https://www.fusionbank.com/deposit.html?lang=tc", "browser", None),
]
# Extra official pages fetched with the same method and appended to the main page text.
EXTRA_URLS = {
    "dbs": ["https://www.dbs.com.hk/personal-zh/promotion/OnlineTD-promo"],
    "sc": ["https://www.sc.com/hk/zh/deposits/board-rates/"],
    "dahsing": [
        "https://www.dahsing.com/html/tc/deposit/fixed_deposit/hkd_fixed_deposit.html",
    ],
    "airstar": ["https://www.elebank.com/vendor/json/deposit_rate.json"],
    "ccba": ["https://www.asia.ccb.com/hongkong_tc/personal/accounts/promotions/newfundtd/index.html"],
    "icbcasia": ["https://www.icbcasia.com/hk/tc/personal/latest-promotion/new-funds-time-deposit.html",
                 "https://www.icbcasia.com/hk/tc/personal/latest-promotion/hkd-new-funds-time-deposit.html"],
    "bea": ["https://www.hkbea.com/hk-form/?formId=RATE&rateType=fcdr&language=tc#/forms/MISC"],
}
REVEAL = {"dahsing"}  # rate tables sit in closed 「了解更多」 pop-ups

FIELDS = ("id", "name_zh", "short", "kind", "color", "url", "method", "parser")


def banks():
    return [dict(zip(FIELDS, b), extra=EXTRA_URLS.get(b[0], []), reveal=b[0] in REVEAL) for b in BANKS]
