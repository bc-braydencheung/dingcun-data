# dingcun-data

香港銀行定期存款利率公開數據（定存雷達 app 用）。

- `data/rates.json`：最新利率（schema 1），每條附來源網址、抓取時間、條件。
- `data/history/YYYY-MM-DD.json`：每日快照；`data/history_index.json`：日期索引。
- `scraper/`：抓取程式（Playwright + 每間銀行一個 parser），`python run.py` 抓網上，`python run.py --fixtures` 用存低嘅網頁測試，`pytest -q tests`。
- `ci/scrape.yml`：GitHub Actions 每日兩次自動抓取（要手動複製去 `.github/workflows/`）。

抓唔到嘅銀行會沿用上次成功數據並標 `stale`；永不估算利率。HIBOR 來自香港銀行公會每日定價（金管局 API 做後備）。
利率只供參考，以銀行最終確認為準。

## 健康檢查
每次抓完會寫 `data/health.json`（各狀態銀行數、利率數目、HIBOR 日期、`alerts`）。以下情況會出 alert，`scraper/health.py` 會以 exit 1 結束，令 GitHub Actions 變紅並 email 通知觸發者：
- 某間銀行超過 72 小時冇成功抓到（或者從來未成功過）
- 利率總數比上次少咗 30% 以上
- HIBOR 超過 5 日冇更新

某間銀行今次抽到嘅利率少過上次三成，會當抓取失敗，沿用上次數據並標 `stale`（避免網頁未載完就覆蓋）。

## 覆蓋
可讀官方利率：中銀、滙豐、恒生、渣打、星展（網上定存優惠頁）、建行（亞洲）、大眾、富邦、創興、花旗、東亞、大新（高息港元／美元定存，表喺「了解更多」彈窗）、工銀亞洲、上海商業、集友（港元牌價）、眾安、Mox、livi、WeLab、螞蟻、平安壹賬通、天星（官方 JSON）。
未支援（官網擋程式或冇可讀利率表，app 只會顯示「去官網睇」）：中信銀行國際（HTTP 403）、華僑銀行（跳去新加坡頁）、富融（HTTP 567）。
