# dingcun-data

香港銀行定期存款利率公開數據（定存雷達 app 用）。

- `data/rates.json`：最新利率（schema 1），每條附來源網址、抓取時間、條件。
- `data/history/YYYY-MM-DD.json`：每日快照；`data/history_index.json`：日期索引。
- `scraper/`：抓取程式（Playwright + 每間銀行一個 parser），`python run.py` 抓網上，`python run.py --fixtures` 用存低嘅網頁測試，`pytest -q tests`。
- `ci/scrape.yml`：GitHub Actions 每日兩次自動抓取（要手動複製去 `.github/workflows/`）。

抓唔到嘅銀行會沿用上次成功數據並標 `stale`；永不估算利率。HIBOR 來自香港金融管理局 API。
利率只供參考，以銀行最終確認為準。
