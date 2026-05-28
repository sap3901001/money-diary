# MyAB 記帳 Web App (Daily Ledger) 開發計畫

> ✅ **本文件已定稿（2026-04-08）。**
> 詳細討論進度請參閱 `Daily_Ledger_討論進度.md`。
>
> **✅ 已確認章節（1–7）**：所有章節均已定案（2026-04-08）。
>
> **實作進度（2026-04-10）**：Step 1–8 已完成，測試總數 454 tests 全部通過。0 skipped。

## Context

使用者目前使用 Windows 軟體 MyAB 記帳，但希望改用自行開發的 Python Web App 來記錄日常交易。需求包括：基本記帳、統計報表（月報 + 分類統計 + 趨勢圖）、匯入現有 MyAB 資料、匯出 CSV 供 Excel / Power BI 分析。僅在本機 localhost 使用。

## 技術選型

- **後端**：FastAPI + uvicorn（提供 REST API，並以 `StaticFiles` 掛載 `frontend/` 目錄）
- **前端**：純靜態 HTML/CSS/JS + Bootstrap 5（本機化，離線可用）+ Chart.js（本機化，離線可用），不使用 Jinja2 templates
- **架構模式**：前後端目錄分離、**單一 process** 同時 serve API 與靜態前端（port 8000，零 CORS）
- **部署模式**：單一 APP——整個專案目錄（含 `data/`）可攜式，複製即可移植（筆電↔桌機）
- **啟動方式**：`start.bat`（Windows）/ `start.sh`（Linux/Mac）一鍵啟動 FastAPI 並開啟瀏覽器
- **儲存**：CSV 檔案（標準函式庫 `csv` 讀寫）
- **套件管理**：venv + requirements.txt
- **無需資料庫**：資料量極小（每日 ≤ 10 筆，10 年約 36,500 筆）

## 專案目錄結構

```
/mnt/c/test_soft/MyAB/note/daily_ledger/      ← 整個目錄可攜式，複製即可移植
├── app.py                    # FastAPI 主應用（REST API + StaticFiles 掛載 frontend/）
├── data_manager.py           # CSV 讀寫 + CRUD 邏輯
├── import_export.py          # MyAB CSV 匯入 / 匯出
├── report_engine.py          # 統計報表計算
├── requirements.txt          # Python 依賴清單
├── start.bat                 # Windows 一鍵啟動器（啟動 uvicorn + 開瀏覽器）
├── start.sh                  # Linux/Mac 一鍵啟動器
├── data/                     # 資料檔（移植時一併帶走）
│   ├── main_db.csv           # 交易記錄主檔
│   └── categories.csv        # 分類設定
└── frontend/                 # 純靜態前端（由 FastAPI StaticFiles 掛載於 /）
    ├── index.html            # 首頁 = 記帳輸入頁（最常用動作）
    ├── list.html             # 交易記錄列表
    ├── report.html           # 統計報表（圖表）
    ├── categories.html       # 分類管理
    ├── import.html           # MyAB 匯入
    ├── export.html           # CSV 匯出（供 Power BI 分析）
    ├── style.css             # 自訂樣式（單一檔）
    ├── js/                   # 前端共用 module
    │   ├── api.js            # fetch 包裝（統一錯誤處理）
    │   ├── format.js         # 千分位、日期、類型字串轉換
    │   ├── toast.js          # 訊息提示
    │   └── navbar.js         # navbar active 狀態
    └── lib/                  # 本機化靜態資源
        ├── bootstrap/        # Bootstrap 5
        ├── bootstrap-icons/  # Bootstrap Icons（Icon 唯一來源）
        └── chart.js/         # Chart.js

> 所有頁面共用頂部 Bootstrap 5 navbar：`<i class="bi bi-journal-text"></i> Daily Ledger | 記帳 | 列表 | 報表 | 分類 | 匯入 | 匯出`
> 所有 icon 一律使用 Bootstrap Icons，不使用 emoji。
```

### 啟動器範例

**Windows `start.bat`**
```bat
@echo off
cd /d %~dp0
call venv\Scripts\activate
start "" http://localhost:8000/
uvicorn app:app --port 8000
```

**Linux/Mac `start.sh`**
```bash
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
(sleep 1 && xdg-open http://localhost:8000/) &
uvicorn app:app --port 8000
```

## CSV 欄位設計

### main_db.csv

```
id,日期,類型,類別主類,類別次類,金額,明細,備註,建立時間
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | str | UUID4 前 8 碼，唯一識別 |
| `日期` | str | `YYYY-MM-DD`（ISO 8601，Excel/Power BI 原生支援）|
| `類型` | str | `E`=支出, `I`=收入 |
| `類別主類` | str | 如「餐飲費」|
| `類別次類` | str | 如「早餐」，可為空 |
| `金額` | int | 全部儲存正整數，收支由「類型」欄決定（E=支出、I=收入）|
| `明細` | str | 交易說明 |
| `備註` | str | 附加備註 |
| `建立時間` | str | ISO 8601 |

### categories.csv

```
類型,主類,次類
E,餐飲費,早餐
E,餐飲費,午餐
E,生活雜支,
I,薪資,
I,其他收入,
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `類型` | str | `E`=支出, `I`=收入 |
| `主類` | str | 如「餐飲費」 |
| `次類` | str | 如「早餐」，可為空（代表只有主類層級）|


## API 路由

> ✅ **第四章已定案**（2026-04-07）。所有頁面由 FastAPI `StaticFiles` 掛載 `frontend/` 提供，無獨立頁面路由。

### 交易 CRUD（4.2）

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/transactions` | 新增交易（回傳含 id 與建立時間的完整物件）|
| GET | `/api/transactions` | 查詢（分頁 + 篩選），response 含 `items/total/page/size/pages/summary`，summary 為篩選範圍的全部統計 |
| GET | `/api/transactions/{id}` | 取單筆 |
| PUT | `/api/transactions/{id}` | 修改交易（**全欄位覆蓋**）|
| DELETE | `/api/transactions/{id}` | 刪除交易（**硬刪除**）|
| GET | `/api/transactions/date_range` | 取得資料的最早/最晚日期 + 總筆數（供匯出頁預設值用）|

- 查詢篩選參數：`from`、`to`、`type`、`category_main`、`category_sub`、`keyword`、`amount_min`、`amount_max`、`page`、`size`
- 分頁：預設 `size=100`、上限 500
- 排序：固定日期 DESC + 建立時間 DESC
- Response 格式：HTTP status + 純資料；錯誤回 `{"detail": "..."}`
- 驗證：Pydantic model（日期 `YYYY-MM-DD`、類型 `E`/`I`、金額正整數 >0、分類必須存在於 categories.csv）

### 分類管理（4.3）

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/categories` | 取得**平鋪陣列** `[{類型,主類,次類}, ...]`；支援 `?type=E/I` 篩選、`?include_count=1` 附加交易引用筆數 |
| POST | `/api/categories` | 新增分類（重複回 409）|
| DELETE | `/api/categories` | 刪除分類（body 傳類型/主類/次類；有交易引用則回 409）|
| POST | `/api/categories/merge` | 合併分類（改名場景亦由此處理；回傳更新筆數與被刪分類）|

- **不提供獨立改名 API**：改名/合併統一由 `merge` 端點處理
- 採平鋪格式理由：與 `categories.csv` 1:1 對應（後端零轉換）、`include_count` 擴充無破壞性、分類管理頁列表可直接使用、過濾與搜尋簡單
- 前端記帳輸入頁的連動下拉以 `Array.filter` 自行 group（資料量小，無效能顧慮）
- GET 範例 response：
  ```json
  [
    {"類型":"E","主類":"餐飲費","次類":"早餐"},
    {"類型":"E","主類":"餐飲費","次類":"午餐"},
    {"類型":"E","主類":"生活雜支","次類":""},
    {"類型":"I","主類":"薪資","次類":""}
  ]
  ```
- GET `?include_count=1` 範例：每筆物件加上 `"count": 234`

### 匯入/匯出（4.4）

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/import/preview` | 上傳 MyAB CSV，解析後回傳預覽摘要 + `preview_token`，**不寫入** |
| POST | `/api/import/confirm` | 提交 `preview_token` 確認寫入 |
| GET | `/api/export` | 匯出 CSV（參數：`from`、`to`），下載檔名 `daily_ledger_{YYYYMMDD}_{YYYYMMDD}.csv` |

- 匯入暫存：**記憶體 dict + TTL 10 分鐘**；token 不存在或過期回 **410 Gone**
- 匯入原子性：後端先寫暫存檔再 rename，達成全有全無
- 匯出編碼：UTF-8 with BOM（Excel 友善）
- 匯出排序：日期 ASC + 建立時間 ASC
- 不提供 MyAB 相容格式，不提供 JSON 匯出

### 統計報表（4.5）

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/report/monthly` | 月度收支摘要（長條圖 + 淨額折線用）|
| GET | `/api/report/category` | 分類佔比（甜甜圈圖用），支援 `level=main\|sub` |
| GET | `/api/report/trend` | 月度趨勢（折線圖用），支援 `category_main` 篩選 |

- 共用參數：`from`、`to`（預設最近 12 個月）、`type`（`E`/`I`/`all`）
- 後端聚合（`report_engine.py`）；佔比由後端計算
- 空月份補 0，避免折線圖斷裂
- 不快取（資料量小，每次重算即可）

## 前端頁面摘要

> ✅ **第五章全部已定案**（2026-04-07）。

所有頁面共用頂部 Bootstrap 5 navbar：**`<i class="bi bi-journal-text"></i> Daily Ledger | 記帳 | 列表 | 報表 | 分類 | 匯入 | 匯出`**（所有 icon 採 Bootstrap Icons，不使用 emoji）

### 1. index.html — 記帳輸入頁（首頁）
- **欄位**：日期（預設今天，**左右兩側 `[◀ 前一日]` / `[下一日 ▶]` 按鈕**供批次輸入快速切換）、類型（Bootstrap button group：支出/收入）、主類（下拉）、次類（下拉，連動）、金額（正整數）、明細、備註
- **載入時**：`fetch /api/categories` 取全部分類（平鋪陣列）
- **類型切換**：重刷主類下拉
- **新增成功後**：保留日期與類型、清空其他欄位（方便連續記帳）
- **底部**：「今日已記錄」列表（最多 10 筆）即時回饋

### 2. list.html — 交易記錄列表
- **篩選區**：可收合（預設展開），支援 4.2 全部篩選參數（日期區間預設本月、類型、主類、次類、金額區間、關鍵字）
- **摘要列**：顯示篩選範圍的總筆數/總收入/總支出/淨額（取自 `GET /api/transactions` response 的 `summary` 欄位）
- **表格**：金額紅/綠色區分；固定排序（日期 DESC + 建立時間 DESC，不開放自訂）
- **編輯**：採 Modal（不離開列表）；**刪除二次確認**
- **不支援**：批次操作
- **分頁**：100 筆，底部上一頁/下一頁

### 3. report.html — 統計報表
- **共用**：頂部日期範圍選擇器，**快捷按鈕**：本月 / 本季 / 本年 / 近 12 月 / 全部 + 自訂區間（預設近 12 月）
- **圖一 月度收支長條圖**：收入綠 / 支出紅 bar + **淨額折線疊加**
- **圖二 分類佔比甜甜圈圖**：**預設顯示支出**，提供「支出/收入」「主類/次類」切換
- **圖三 月度趨勢折線圖**：收入 / 支出 / 淨額三線，可選分類篩選（`category_main`）
- **不支援**：drill-down 點擊跳列表
- **顏色方案**：固定色系（收入綠、支出紅、淨額藍）

### 4. categories.html — 分類管理
- **類型 tab 切換**：支出 / 收入
- **新增**：上方內嵌新增表單（類型/主類/次類）
- **列表**：採**樹狀展開**（主類折疊次類），**顯示每筆分類的交易引用筆數**（API `?include_count=1`）
- **刪除**：二次確認，有引用則拒絕（API 回 409）
- **改名**：獨立改名按鈕（前端 UI 為改名，內部呼叫 `POST /api/categories/merge`）
- **合併分類** modal：來源/目標下拉，**即時試算影響筆數**
- **不提供**：合併復原功能

### 5. import.html — MyAB 匯入
- **三步驟**：
  1. **上傳區**：拖放 + 點擊選擇 .csv → `POST /api/import/preview`
  2. **預覽區**：顯示摘要（新增 / 重複 / **A/L/Equity 過濾** / 新分類數量、日期範圍）+ **全部新分類清單** + **前 5 筆新交易範例**，按確認送 `POST /api/import/confirm`
  3. **完成區**：顯示匯入結果，提供「繼續匯入」/「查看列表」按鈕
- **新分類**：全部自動匯入（不逐個確認）
- **匯入失敗**：採全有全無（後端先寫暫存檔再 rename 達成原子性）

### 6. export.html — CSV 匯出
- **目的**：提供使用者將交易資料下載成 CSV 供 Power BI / Excel 分析
- **載入時**：`fetch /api/transactions/date_range` 取 `{min, max, count}` 作為日期預設值
- **元素**：
  - 開始日期 / 結束日期（預設 = 資料最早 / 最晚日期）
  - 快捷按鈕：`[全部資料] [本年] [近 12 月] [本月]`
  - 預覽資訊：「將匯出 X 筆交易（YYYY-MM-DD ~ YYYY-MM-DD）」
  - 下載按鈕 → `GET /api/export?from=...&to=...`
- **下載檔名**：`daily_ledger_{YYYYMMDD}_{YYYYMMDD}.csv`（後端以 `Content-Disposition` 指定）
- **不顯示**：「最近匯出時間」

## UI 風格與 CSS 方案

> ✅ **5.6 已定案**（2026-04-07）。

### 主題與配色
- **主題色系**：冷色系藍/灰（primary 深藍 + 中性灰背景，不干擾金額紅綠判讀）
- **收入**：`#198754`（Bootstrap success 綠）
- **支出**：`#dc3545`（Bootstrap danger 紅）
- **淨額**：`#0d6efd`（Bootstrap primary 藍）

### 字體
- **一般文字**：系統字體堆疊 + 中文 fallback
  ```css
  font-family: system-ui, -apple-system, "Segoe UI", Roboto,
               "Microsoft JhengHei", "PingFang TC", "Noto Sans TC", sans-serif;
  ```
- **金額數字**：採等寬數字對齊
  ```css
  .amount {
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }
  ```

### 響應式
- 基本響應（桌機優先）
- ≥ 768px 完整優化
- < 768px 可用但不特別優化
- 不為手機投資額外 CSS

### CSS 組織
- **單一 `style.css`**（集中所有自訂樣式）
- 客製樣式量少，主要依賴 Bootstrap 5 預設元件
- 超過 500 行再考慮拆分

### Icon 方案
- **唯一方案：Bootstrap Icons**（本機化至 `frontend/lib/bootstrap-icons/`）
- **不使用 emoji**
- 常用對照表：

| 用途 | Class |
|------|-------|
| 應用標題 | `bi-journal-text` |
| 記帳（新增）| `bi-pencil-square` |
| 列表 | `bi-list-ul` |
| 報表 | `bi-bar-chart` |
| 分類 | `bi-tags` |
| 匯入 | `bi-box-arrow-in-down` |
| 匯出 | `bi-box-arrow-up` |
| 編輯 | `bi-pencil` |
| 刪除 | `bi-trash` |
| 前一日 / 下一日 | `bi-chevron-left` / `bi-chevron-right` |
| 成功提示 | `bi-check-circle` |
| 錯誤提示 | `bi-exclamation-triangle` |

### 深色模式
- **不支援**（個人單機 APP，亮色背景最利於數字判讀）

### 互動回饋
- **成功/錯誤訊息**：Bootstrap Toast（右上角，3 秒自動消失）
- **表格 row**：加 `table-hover` class
- **按鈕 hover**：Bootstrap 預設
- **載入中**：Bootstrap spinner（資料量小，多數情況不顯示）
- **頁面切換**：純連結跳轉，無動畫

### 前端 JS 共用 module

每頁透過 `<script src="./js/xxx.js"></script>` 載入，無需打包工具。

| 檔案 | 職責 |
|------|------|
| `js/api.js` | fetch 包裝：統一錯誤處理、JSON parse |
| `js/format.js` | 格式化函式：金額千分位、日期、類型字串轉換 |
| `js/toast.js` | Toast 顯示（成功/錯誤） |
| `js/navbar.js` | 依當前 URL 動態設定 navbar active 狀態 |

## 匯入流程

> ✅ **6.1 / 6.1a / 6.1b / 6.2 / 6.3 全部已定案**（2026-04-07）。

### 匯入來源

MyAB 備份 CSV（欄位：`日期,類型,類別主類,類別次類,帳戶,金額,明細,備註`），例如：
- `note/myab_export/target/backup_20260402.csv`
- `note/myab_export/target/transactions.csv`

### 欄位對映規則

| MyAB 欄位 | 處理方式 |
|-----------|----------|
| `日期` | `YYYY/MM/DD` → `YYYY-MM-DD` |
| `類型` | `A`/`L`/`Equity` **直接過濾掉**；只保留 `E`/`I` |
| `類別主類` / `類別次類` | 原樣保留 |
| `帳戶` | **丟棄**（已移除帳戶功能）|
| `金額` | 取絕對值（正負號由 `類型` 決定）|
| `明細` / `備註` | 原樣保留 |
| `id` | 自動產生（UUID4 前 8 碼）|
| `建立時間` | 匯入當下的系統時間 |

### 分類差異處理（聯集累積）

不同時期的 MyAB 備份可能有不同的分類設置，採「**聯集累積 + 人工合併**」策略：

1. 匯入時，將備份中出現但 `categories.csv` 尚無的分類**新增**到 categories.csv
2. **不刪除**現有分類（即使新備份不包含），以保護舊交易引用
3. 若出現改名或結構變動（例如 `餐飲` vs `餐飲費`），系統無法自動判斷，由使用者透過**分類管理頁的「合併」功能**人工處理：選擇來源分類 + 目標分類，系統將所有引用來源的交易改為目標分類，並刪除來源分類

### 交易去重

唯一鍵：`日期 + 類型 + 主類 + 次類 + 金額 + 明細` 六欄組合完全相同則視為重複，跳過匯入（因為 MyAB 備份沒有 id 可用）。

### 匯入流程（使用者視角）

1. **上傳** MyAB 備份 CSV
2. **解析與預覽**：
   ```
   將匯入 backup_20260402.csv：
     ✓ 交易：新增 450 筆，重複 520 筆（跳過）
     ✓ 分類：新增 3 個（餐飲費/宵夜零食、電腦/週邊附件、...）
     ⚠ 過濾：15 筆 A/L/Equity 初值記錄
     [確認匯入] [取消]
   ```
3. **確認**後，新分類 append 至 `categories.csv`、新交易 append 至 `main_db.csv`

### 建議匯入順序

由舊到新：**舊備份 → 新備份 → 最新 transactions.csv**。這樣交易與分類會自然累積，也符合時序邏輯。

## 實作步驟

### Step 1：專案骨架 + CSV 資料層
- 建立目錄結構（`app.py`、`data_manager.py`、`data/`、`frontend/`、`frontend/lib/` 等）
- 實作 `data_manager.py`：transactions / categories 的 CRUD
- 首次啟動自動建立空 CSV（含 header）
- 本機化 Bootstrap 5 + Chart.js 至 `frontend/lib/`
- `start.bat` / `start.sh` 一鍵啟動器

### Step 2：FastAPI 應用 + 記帳輸入頁
- `app.py` 基本框架（FastAPI + `StaticFiles` 掛載 `frontend/`）
- `index.html` 記帳輸入頁（含日期前/後日按鈕、類型 button group、連動下拉、今日已記錄列表）
- API：`POST /api/transactions`、`GET /api/categories`（平鋪陣列）、`GET /api/transactions`（篩選 today）
- Pydantic 驗證

### Step 3：交易記錄列表
- `list.html` + 篩選區（可收合）+ 摘要列 + Modal 編輯 + 分頁
- API：`GET /api/transactions`（含 summary）、`PUT /api/transactions/{id}`、`DELETE /api/transactions/{id}`、`GET /api/transactions/{id}`

### Step 4：分類管理 + 合併功能
- `categories.html`（類型 tab、樹狀展開、引用筆數、改名/合併 modal）
- API：`POST /api/categories`、`DELETE /api/categories`、`POST /api/categories/merge`、`GET /api/categories?include_count=1`

### Step 5：MyAB 匯入（✅ 完成，2026-04-09）
- `import_export.py`：MyAB CSV 解析（UTF-8 BOM 支援、欄位對映、A/L 過濾、無效日期/金額過濾）
- `import.html`：三步驟匯入頁（拖放上傳 → 預覽摘要/分類/樣本 → 完成結果）
- API：`POST /api/import/preview`（回傳 preview_token + 摘要）、`POST /api/import/confirm`（寫入並清除 token）
- 安全防護：檔案副檔名驗證（.csv）、10MB 大小限制
- 暫存：記憶體 dict + TTL 10 分鐘；每次 preview 自動清理過期 token
- 原子性：先寫暫存檔再 rename
- 測試：83 tests（17 unit + 21 API/security + 45 functional requirements）

### Step 6：CSV 匯出（✅ 完成，2026-04-09）
- `data_manager.py`：新增 `export_transactions(from_date, to_date)`（篩選 + 日期 ASC 排序）
- `export.html`：載入時自動取日期範圍為預設值；快捷按鈕（全部/本年/近12月/本月）；防抖更新預覽筆數；無資料時顯示警示；`<a>` click 觸發下載
- API：`GET /api/export?from=...&to=...`（驗證日期格式與先後順序、`utf-8-sig` 編碼、`Content-Disposition` 指定檔名）
- 檔名：`daily_ledger_{YYYYMMDD}_{YYYYMMDD}.csv`；UTF-8 with BOM（Excel 友善）
- 程式碼審查修正：①日期值驗證（`strptime`，防 month=13 等非法值）②Content-Type charset 改為標準 `utf-8`（BOM 在 bytes 內容）③前端 `from > to` 防衛
- 測試：60 tests（8 unit 追加 + 18 API + 34 functional；AT-011/012/018 ✅）；AT-017 round-trip 留待 Step 8 整合測試

### Step 7：統計報表（✅ 完成，2026-04-09）
- `report_engine.py`：monthly_report / category_report / trend_report（空月補 0）
- `report.html`：日期快捷（本月/本季/本年/近12月/全部/自訂）、月度長條+淨額折線、分類甜甜圈、趨勢折線
- API：`GET /api/report/monthly`、`GET /api/report/category`（`level=main|sub`）、`GET /api/report/trend`（`category_main`）
- 測試：22 unit + 28 API + 61 functional = 111 tests；AT-014（空月補0）、AT-015（報表與交易摘要一致）

### Step 8：收尾（✅ 完成，2026-04-10）
- `frontend/report.html`：修正「全部」模式無資料時顯示提示而非 fallback 到今日
- 整合測試目錄 `tests/integration/`：建立 `__init__.py`
- `tests/integration/test_import_to_report_flow.py`（19 tests）：匯入→列表/報表/匯出一致性、邊界字元、AT-017 round-trip
- `tests/integration/test_merge_consistency.py`（15 tests）：合併後交易引用、報表、匯出一致性
- `tests/integration/test_step8_level2.py`（30 tests）：Level 2 全自動化
  - `TestAtomicity`（4）：寫入失敗不損壞主檔、無孤立 .tmp、init 清理殘留
  - `TestPowerBiCsvFormat`（9）：BOM、YYYY-MM-DD 日期、整數金額、欄位標題、Content-Type/Disposition
  - `TestImportPreviewNewCatsFromNewRows`（3）：Bug-1 修正驗證（new_rows 擷取）
  - `TestCategoryMergeTypeValidation`（6）：Bug-2 修正驗證（類型 E/I 欄位驗證）
  - `TestImportCsvHeaderValidation`（8）：Bug-3 修正驗證（缺少必要欄位回 400）
- **程式碼審查修正**：
  - Bug-1：`import_preview` 從 `new_rows` 擷取新分類（非全部 rows）
  - Bug-2：`CategoryMerge` 加入 `@field_validator`，限制類型欄為 `{"E","I"}`
  - Bug-3：`parse_myab_csv` 加入 `_REQUIRED_HEADERS` 前置驗證，缺欄回 400
- 測試：49 tests（integration/test_import_to_report_flow.py 19 + test_merge_consistency.py 15 + test_step8_level2.py 30）；AT-017 ✅ Level 2 全自動 ✅

## 關鍵參考檔案

| 用途 | 路徑 |
|------|------|
| 現有匯出工具 | `/mnt/c/test_soft/MyAB/note/myab_export/myab_export.py`（331 行）|
| MyAB 匯出資料 | `/mnt/c/test_soft/MyAB/note/myab_export/target/transactions.csv`（975 筆）|
| 原始 MyAB 分類/帳戶清單（僅供匯入測試對照，帳戶功能已不採用） | `/mnt/c/test_soft/MyAB/note/myab_export/target/accounts.csv`（44 筆）|

## 驗證方式

### Level 1：每 Step 輕量驗收
每個 Step 完成時，手動跑過該 Step 的核心流程確認基本可用。

### Level 2：Step 8 整合測試
1. **匯入驗證**：匯入現有 MyAB transactions.csv（975 筆），確認總筆數與金額合計一致
2. **去重測試**：重複匯入同一份 CSV，確認不產生重複筆數
3. **合併功能**：合併兩個分類後，確認所有引用正確更新
4. **原子性**：模擬匯入途中失敗，確認 CSV 不會變成半寫入的損壞狀態
5. **邊界字元**：明細含逗號/引號/中文特殊字元，確認 CSV 讀寫正常
6. **Round-trip 測試**：匯出 CSV 後再匯入，驗證資料無損
7. **報表驗證**：選定月份手動加總，與報表數值比對
8. **Power BI 驗證**：匯出 CSV 丟進 Power BI，確認日期欄識別正確、金額可計算

### Level 3：瀏覽器相容
- Chrome + Edge 必驗（所有頁面正常顯示，無 JS 報錯）
- Firefox 選配

### pytest 自動化測試（現況）

```
tests/
├── unit/
│   ├── test_data_manager.py      # CSV CRUD、去重鍵、分類 merge（含匯出單元測試）
│   ├── test_import_export.py     # MyAB CSV 解析、過濾、欄位對映
│   └── test_report_engine.py     # 報表聚合（monthly/category/trend、空月補0）
├── api/
│   ├── test_transactions_api.py  # 交易 CRUD API（AT-001~005）
│   ├── test_list_filtering.py    # 篩選、分頁、摘要（AT-003~005）
│   ├── test_step3_extra.py       # 列表頁邊界案例
│   ├── test_categories_api.py    # 分類 API（AT-006~008）
│   ├── test_categories_extra.py  # 分類邊界/特殊字元
│   ├── test_import_api.py        # 匯入 API + 安全性（AT-009~010）
│   ├── test_import_functional.py # 匯入功能需求全覆蓋（FR-IMP-1~7，45 tests）
│   ├── test_export_api.py        # 匯出 API 基本測試（AT-011/012/018，18 tests）
│   ├── test_export_functional.py # 匯出功能需求全覆蓋（FR-EXP-1~8，34 tests）
│   ├── test_report_api.py        # 報表 API（AT-014/015，28 tests）
│   └── test_report_functional.py # 報表功能需求全覆蓋（FR-RPT-1~6，61 tests）
└── integration/
    ├── test_import_to_report_flow.py  # 匯入→列表/報表/匯出一致性（19 tests）
    ├── test_merge_consistency.py      # 合併一致性（15 tests）
    └── test_step8_level2.py           # Level 2 自動化：原子性/Power BI/Bug 修正驗證（30 tests）
```

**執行**：`pytest tests/`（目前 454 tests，全部通過）
