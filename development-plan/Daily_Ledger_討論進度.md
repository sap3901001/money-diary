# Daily Ledger 開發計畫 — 討論進度追蹤

> 搭配 `Daily_Ledger_開發計畫.md` 使用，逐項討論並記錄決議。

## 狀態說明

- ✅ 已確認：討論完成，有明確結論
- 🔄 討論中：尚在討論，未有定論
- ⬜ 待討論：尚未開始討論

---

## 一、需求與範圍

| # | 議題 | 狀態 | 決議 |
|---|------|------|------|
| 1.1 | 介面形式 | ✅ | 網頁 Web App（FastAPI） |
| 1.2 | 儲存方式 | ✅ | CSV 格式（方便 Excel / Power BI） |
| 1.3 | 功能範圍 | ✅ | 基本記帳 + 統計報表（月報、分類、趨勢圖） |
| 1.4 | 分類體系 | ✅ | 匯入 MyAB 分類，之後可自由新增修改 |
| 1.5 | MyAB 匯入 | ✅ | 需要，支援匯入 MyAB 匯出的 CSV |
| 1.6 | 使用情境 | ✅ | 僅本機 localhost |

## 二、技術選型

| # | 議題 | 狀態 | 決議 |
|---|------|------|------|
| 2.1 | 後端框架（Flask vs FastAPI vs 其他） | ✅ | FastAPI + uvicorn |
| 2.2 | 前端方案（純 HTML/JS vs 輕量框架） | ✅ | 純 HTML/CSS/JS + Bootstrap 5（本機化，離線可用）|
| 2.3 | 圖表庫（Chart.js vs 其他） | ✅ | Chart.js（本機化，離線可用）|
| 2.4 | Python 版本與套件管理（venv / requirements.txt） | ✅ | venv + requirements.txt |
| 2.5 | 架構模式（MPA+Jinja2 vs 純前後端分離） | ✅ | 純前後端分離：FastAPI 只提供 REST API（JSON），前端為純靜態 HTML/CSS/JS，不使用 Jinja2 templates |

## 三、CSV 欄位設計

| # | 議題 | 狀態 | 決議 |
|---|------|------|------|
| 3.1 | 主資料檔名稱與欄位定義 | ✅ | 檔名改為 `main_db.csv`，欄位：id/日期/類型/類別主類/類別次類/帳戶/金額/明細/備註/建立時間 |
| 3.2 | id 格式 | ✅ | UUID4 前 8 碼（如 `a3f7c2d1`）|
| 3.3 | 日期格式 | ✅ | `YYYY-MM-DD`（ISO 8601，Excel/Power BI 原生支援）|
| 3.4 | 金額儲存方式 | ✅ | 全部儲存正整數，收支由「類型」欄決定（E=支出、I=收入）|
| 3.5 | 分類資料儲存 | ✅ | 獨立 `categories.csv`（欄位：類型/主類/次類）|
| 3.6 | accounts.csv 欄位 | ✅ | 簡單三欄：帳戶代碼/帳戶名稱/類型（A=資產/L=負債）（→ 已被 3.7 推翻）|
| 3.7 | 帳戶功能是否需要 | ✅ | 不需要：屬輕度使用，移除 main_db.csv 的帳戶欄位、accounts.csv、帳戶管理頁與帳戶相關 API |
| 3.8 | 是否新增 `年月` 欄輔助分析 | ✅ | 不需要：Power BI 自動識別 `YYYY-MM-DD` 日期欄並建立年/季/月階層，`年月` 欄屬冗餘資料 |
| 3.9 | 是否新增 `淨額`（帶符號金額）欄 | ✅ | 不需要：分析採 Power BI，可用 measure 處理符號邏輯，`金額`（正整數）+ `類型`（E/I）已足夠 |

## 四、API 路由設計

| # | 議題 | 狀態 | 決議 |
|---|------|------|------|
| 4.1 | 頁面路由規劃 | ✅ | FastAPI 以 `StaticFiles` 掛載 `frontend/` 目錄，單一 process 同時 serve API 與靜態前端（port 8000）；零 CORS、整個目錄可攜、`start.bat`/`start.sh` 一鍵啟動。頁面：`index.html`（**記帳輸入頁 = 首頁**，最常用動作）、`list.html`（交易列表）、`report.html`（統計報表）、`categories.html`（分類管理）、`import.html`（MyAB 匯入）、`export.html`（CSV 匯出，5.7 新增）；所有頁面共用頂部 Bootstrap 5 navbar 作為功能切換選單：**📒 Daily Ledger \| 記帳 \| 列表 \| 報表 \| 分類 \| 匯入 \| 匯出** |
| 4.2 | 交易 CRUD API | ✅ | 端點：POST/GET/PUT/DELETE `/api/transactions[/id]`；Response：HTTP status + 純資料；查詢篩選：from/to/type/category_main/category_sub/keyword/amount_min/amount_max/page/size；分頁預設 100、上限 500；修改採 PUT 全欄位覆蓋；刪除採硬刪除；排序固定日期+建立時間 DESC；`GET /api/transactions` response 除 items/total/page/size/pages 外另含 `summary` 欄位（count/total_income/total_expense/net，為篩選範圍的全部統計，非僅當前頁）|
| 4.3 | 分類管理 API | ✅ | 端點：`GET /api/categories`（**平鋪陣列** `[{類型,主類,次類}, ...]`，支援 `?type=E/I` 篩選、`?include_count=1` 附加交易引用筆數）、`POST /api/categories`（新增，重複回 409）、`DELETE /api/categories`（body 傳類型/主類/次類，有交易引用則拒絕回 409）、`POST /api/categories/merge`（合併/改名統一由此處理）。不提供獨立改名 API；採平鋪格式理由：與 categories.csv 1:1 對應、`include_count` 擴充無破壞性、分類管理頁列表可直接使用 |
| 4.4 | 匯入/匯出 API | ✅ | 匯入兩階段：`POST /api/import/preview`（上傳檔案 → 回傳預覽 + preview_token，不寫入）、`POST /api/import/confirm`（提交 token → 實際寫入）；預覽結果暫存於**記憶體 dict + TTL 10 分鐘**；匯出：`GET /api/export`（支援同交易查詢的篩選參數，回傳 CSV 檔下載）|
| 4.5 | 統計報表 API | ✅ | 三支端點：`GET /api/report/monthly`（月度收支摘要，長條圖 + 淨額折線用）、`GET /api/report/category`（分類佔比，支援 `level=main\|sub`）、`GET /api/report/trend`（月度趨勢，支援 `category_main` 篩選單一分類）；共用參數 `from`/`to`（預設最近 12 個月）/`type`（E/I/all）；後端聚合（report_engine.py），佔比由後端計算；空月份補 0；不快取 |

## 五、前端頁面設計

| # | 議題 | 狀態 | 決議 |
|---|------|------|------|
| 5.1 | 記帳輸入頁（index.html）流程與欄位 | ✅ | 欄位：日期（預設今天，左右兩側 `[◀ 前一日]` / `[下一日 ▶]` 按鈕供批次輸入快速切換，不限未來日期，不加鍵盤快捷）、類型（Bootstrap button group：支出/收入）、主類（下拉）、次類（下拉，連動）、金額（正整數）、明細、備註；載入時 `fetch /api/categories` 取全部分類；類型切換時重刷主類下拉；新增成功後**保留日期與類型、清空其他欄位**（方便連續記帳）；頁面底部顯示「今日已記錄」列表（最多 10 筆）即時回饋 |
| 5.2 | 交易列表頁篩選與分頁 | ✅ | 篩選區可收合（預設展開）支援 4.2 全部篩選參數（日期區間預設本月、類型、主類、次類、金額區間、關鍵字）；**摘要列**顯示篩選範圍的總筆數/總收入/總支出/淨額（後端 `GET /api/transactions` response 加 `summary` 欄位）；表格金額紅/綠色區分；編輯採 **Modal**（不離開列表）；刪除二次確認；**固定排序**（日期 DESC + 建立時間 DESC，不開放自訂）；**不支援批次操作**；分頁 100 筆，底部上一頁/下一頁 |
| 5.3 | 統計報表頁圖表類型與互動 | ✅ | 三張圖共用頂部日期範圍選擇器（**快捷按鈕**：本月/本季/本年/近 12 月/全部 + 自訂區間，預設近 12 月）；①月度收支長條圖（收入綠/支出紅 bar + **淨額折線疊加**）；②分類佔比甜甜圈圖（**預設顯示支出**，提供「支出/收入」「主類/次類」切換）；③月度趨勢折線圖（收入/支出/淨額三線，可選分類篩選）；**不支援 drill-down 點擊跳列表**；顏色方案**固定色系**（收入綠、支出紅、淨額藍）|
| 5.4 | 分類管理頁操作方式 | ✅ | 類型 tab 切換（支出/收入）；上方內嵌新增表單（類型/主類/次類）；列表採**樹狀展開**（主類折疊次類）；**顯示每筆分類的交易引用筆數**（4.3 API 加 `?include_count=1`）；刪除二次確認，有引用則拒絕；獨立**改名按鈕**（前端 UI 為改名，內部呼叫 merge API）；**合併分類** modal（來源/目標下拉，即時試算影響筆數，呼叫 `POST /api/categories/merge`）；**不提供合併復原功能** |
| 5.5 | 匯入頁流程（上傳→預覽→確認） | ✅ | 三步驟：①上傳區（拖放 + 點擊選擇 .csv）→ POST /api/import/preview；②預覽區顯示摘要（新增/重複/**A/L/Equity** 過濾/新分類數量、日期範圍）+ **全部新分類清單** + **前 5 筆新交易範例**，按確認送 POST /api/import/confirm；③完成區顯示匯入結果，提供「繼續匯入」/「查看列表」按鈕。新分類**全部自動匯入**（不逐個確認）；匯入失敗採**全有全無**（後端用先寫暫存檔再 rename 達成原子性）|
| 5.6 | 整體 UI 風格與 CSS 方案 | ✅ | **A 主題**：冷色系藍/灰（primary 深藍 + 中性灰背景，不干擾金額紅綠判讀）；**B 收支色**：收入綠 `#198754` / 支出紅 `#dc3545` / 淨額藍 `#0d6efd`；**C 字體**：系統字體 + 中文 fallback（`"Microsoft JhengHei","PingFang TC","Noto Sans TC"`）；**D 金額數字**：採 `font-variant-numeric: tabular-nums` 等寬對齊；**E 響應式**：基本響應，桌機 ≥768px 優化，< 768px 可用但不優化；**F CSS 組織**：單一 `style.css`；**G Icon**：**Bootstrap Icons 唯一方案**（本機化至 `frontend/lib/bootstrap-icons/`，**不使用 emoji**，原 `📒` 改為 `<i class="bi bi-journal-text">`）；**H 深色模式**：不支援；**I 互動回饋**：Toast（右上角 3 秒）+ `table-hover` + 無頁面切換動畫；**J 前端 JS module**：拆 4 檔 `api.js` / `format.js` / `toast.js` / `navbar.js` 放於 `frontend/js/` |
| 5.7 | 匯出頁設計（export.html） | ✅ | 元素：日期範圍選擇器（預設 = 資料最早/最晚日期）、快捷按鈕（全部/本年/近12月/本月）、預覽筆數、下載按鈕；新增 API `GET /api/transactions/date_range` → `{min, max, count}` 供預設值載入；下載觸發 `GET /api/export?from=...&to=...`；不顯示「最近匯出時間」；navbar 擴為 6 項加入「匯出」 |

## 六、匯入/匯出邏輯

| # | 議題 | 狀態 | 決議 |
|---|------|------|------|
| 6.1 | MyAB CSV 欄位對映規則 | ✅ | 丟棄 `帳戶` 欄；金額取絕對值（正負由類型決定）；日期 `YYYY/MM/DD` → `YYYY-MM-DD`；自動產生 id（UUID4 前 8 碼）與建立時間 |
| 6.1a | A/L/Equity 記錄處理 | ✅ | 直接過濾（A 資產、L 負債、Equity 權益類型記錄在匯入時丟棄，因已移除帳戶功能）|
| 6.1b | 分類差異處理策略 | ✅ | 聯集累積：每次匯入只新增未出現過的分類到 `categories.csv`，不刪除舊分類；情境改名/結構變動由分類管理頁「合併」功能人工處理 |
| 6.2 | 重複偵測策略 | ✅ | 唯一鍵：`日期 + 類型 + 主類 + 次類 + 金額 + 明細`；完全相同則跳過；匯入預覽顯示「新增 X 筆、重複 Y 筆」 |
| 6.3 | 匯出格式選項（完整 vs MyAB 相容） | ✅ | 只支援本系統 `main_db.csv` 原生格式；不提供 MyAB 相容格式（分析用 Power BI，不需倒回 MyAB）；不提供 JSON 匯出 |

## 七、實作順序與驗證

| # | 議題 | 狀態 | 決議 |
|---|------|------|------|
| 7.1 | 7 個 Step 的優先順序是否調整 | ✅ | 採建議順序 A：Step 6 = CSV 匯出（提前，Power BI 核心價值），Step 7 = 統計報表（延後） |
| 7.2 | 驗證方式是否足夠 | ✅ | 採 A 三層驗證：Level 1 每 Step 輕量驗收 + Level 2 Step 8 整合測試（去重/合併/原子性/邊界字元/Power BI）+ Level 3 Chrome+Edge 瀏覽器相容；另補：後端 API 寫基本 pytest（data_manager / import_export 核心函式）|

---

## 實作進度（2026-04-08 起）

### Step 狀態總覽

| Step | 內容 | 狀態 | 測試 | 備註 |
|------|------|------|------|------|
| 1 | 專案骨架 + CSV 資料層 + 啟動器 | ✅ 完成 | 23 tests | 含程式碼審查修正 |
| 2 | 記帳輸入頁（index.html）+ 基本 API | ✅ 完成 | 24 tests | 含程式碼審查修正 |
| 3 | 交易列表頁（list.html）+ CRUD API 完整 | ✅ 完成 | 24 tests | 含程式碼審查修正 |
| 4 | 分類管理頁（categories.html）| ✅ 完成 | 40 tests | AT-006~008, AT-016；補充 17 tests，修正 5 個 bug |
| 5 | MyAB 匯入（import.html + import_export.py）| ✅ 完成 | 83 tests | AT-009~010；17 unit + 21 API/security + 45 functional |
| 6 | CSV 匯出（export.html）| ✅ 完成 | 60 tests | AT-011/012/018；8 unit + 18 API + 34 functional；含程式碼審查修正 3 項 |
| 7 | 統計報表（report.html + report_engine.py）| ✅ 完成 | 111 tests | AT-014/015；22 unit + 28 API + 61 functional；含程式碼審查修正 2 項 |
| 8 | 收尾（錯誤處理、UI 收斂、整合測試）| ✅ 完成 | 49 tests | AT-017 整合版；Level 2 整合測試；前端無資料修正；Level 2 自動化強化（test_step8_level2.py） |

**目前測試總數：454 tests，全部通過（0 skipped）。**

---

### Step 1：專案骨架 + CSV 資料層（✅ 完成）

**實作內容：**
- `data_manager.py`：CSV CRUD、去重、分類 merge 邏輯
- `start.sh` / `start.bat`：一鍵啟動器
- `requirements.txt`：`fastapi`, `uvicorn[standard]`, `python-multipart`, `pytest`, `httpx`, `pytest-cov`
- `pytest.ini`：測試設定
- `data/`：`main_db.csv`, `categories.csv`

**測試：** `tests/unit/test_data_manager.py`（23 tests）

**審查後修正（2026-04-08）：**
1. `check_duplicates` 批次內自去重缺漏：加入 `seen_keys.add(k)` 防止批次內重複被誤計為新增
2. `merge_categories` src==dst 會刪除分類：加入 `if (src...) == (dst...): raise ValueError("src_equals_dst")` 防衛
3. `query_transactions` page/size 驗證缺失：加入 `ValueError` 明確訊息
4. 殘留 `.tmp` 檔清理：`init_data_files()` 加入 `DATA_DIR.glob("*.tmp")` 清理

---

### Step 2：記帳輸入頁（✅ 完成）

**實作內容：**
- `app.py`：FastAPI 主程式，含 lifespan、所有交易 CRUD API、分類 API、`StaticFiles` 掛載
- `frontend/index.html`：記帳輸入頁
- `frontend/style.css`：全域樣式
- `frontend/js/api.js`：fetch 包裝
- `frontend/js/format.js`：格式化工具（`escHtml`, `amount`, `typeBadge` 等）
- `frontend/js/toast.js`：Toast 通知
- `frontend/js/navbar.js`：導覽列 active 狀態

**測試：** `tests/api/test_transactions_api.py`（24 tests）

**審查後修正（2026-04-08）：**
1. GET 請求不應送 `Content-Type: application/json`：`api.js` 加 `hasBody` 判斷
2. Pydantic 錯誤訊息帶 `"Value error, "` 前綴：`api.js` 加 `.replace(/^Value error,\s*/i, "")`
3. `escHtml` 未共用：移入 `fmt.escHtml()` 並加入 `'` 轉義
4. `toast.js` XSS 風險：`message` 改為先 `escHtml` 再插入 innerHTML
5. 日期清空後按鈕行為：`shiftDate()` 加 `|| todayStr()` 與 `isNaN` 防衛
6. 手動修改日期不觸發列表刷新：加 `inputDate.addEventListener("change", loadTodayList)`
7. 日期清空時 `loadTodayList` 顯示錯誤：加早期 return 顯示「請選擇日期」
8. 非今日日期的列表標題：動態顯示「YYYY-MM-DD 已記錄」vs「今日已記錄」
9. 表單送出缺少日期驗證：加 `if (!body["日期"])` 檢查

---

### Step 3：交易列表頁（✅ 完成）

**實作內容：**
- `frontend/list.html`：交易列表頁，含篩選（可收合）、摘要列、表格、Bootstrap Modal 編輯/刪除、分頁

**測試：** `tests/api/test_list_filtering.py`（24 tests）
- 篩選：7 個案例（日期範圍、類型、主類、次類、關鍵字、金額範圍、複合）
- 排序：1 個案例（日期 DESC）
- 摘要：3 個案例（欄位存在、數值正確、空結果）
- 分頁：6 個案例（結構、最後一頁、超出範圍、page=0、size=0、size>500）
- 編輯：4 個案例（全欄位、保留 id/建立時間、不存在、非法分類）
- 刪除：3 個案例（正常刪除、不存在、總數驗證）

**審查後修正（2026-04-08）：**
1. `btnReset` 不清除主類/次類選擇：在 `buildFilterMain()` 前先將 `fMain.value` 和 `fSub.value` 設為 `""`
2. 金額下限 > 上限靜默回空：`loadList()` 加入驗證，`amount_min > amount_max` 時 toast 錯誤並提前 return
3. Enter 鍵不觸發篩選：為 `fKeyword`、`fAmtMin`、`fAmtMax`、`fFrom`、`fTo` 加 `keydown Enter` 事件

---

### Step 4：分類管理頁（✅ 完成）

**實作內容：**
- `frontend/categories.html`：分類管理頁，含類型 tab（支出/收入切換）、上方內嵌新增表單、樹狀列表（主類折疊次類）、交易引用筆數（`?include_count=1`）、刪除確認 Modal、改名 Modal（內部呼叫 merge API）、合併 Modal（即時試算影響筆數）
- `frontend/style.css`：新增 `.cat-main-row`、`.cat-sub-row` 樣式

**測試：** `tests/api/test_categories_api.py`（23 tests）、`tests/api/test_categories_extra.py`（17 tests）

**審查後修正（2026-04-08）：**
1. Disabled 按鈕事件穿透：event delegation 的 `closest(".btn-delete")` 在點擊 `<i>` 子元素時仍觸發已停用按鈕 → 加入 `!delBtn.disabled` 防衛
2. 混合群組中孤立項目遺失：同主類同時存在 `次類=""` 與 `次類≠""` 時，`次類=""` 項目在樹狀展開中消失 → 單獨提取 `mainLeafItem`，在次類清單首位顯示為「（無次類）」
3. `|||` 分隔符脆弱性（合併 Modal 選項 value）：分類名稱若含 `|||` 會破壞 split 解析 → 改用陣列索引作為 option value（`_mergeCats` 快照陣列）

**補充測試後修正（2026-04-09）：**

新增 `tests/api/test_categories_extra.py`（17 tests），涵蓋 response shape、邊界條件、次類空白正規化、merge 來源驗證、跨類型驗證、特殊字元等缺口，發現並修正 5 個 bug：

1. **BUG-1：次類前後空白未 trim** — `CategoryCreate` 缺少 `validate_sub` validator，`"  午餐  "` 原樣存入 CSV，導致後續交易新增 422 → 新增 `validate_sub`（`return v.strip()`）
2. **BUG-2：次類純空白未正規化為 `""`** — 同 BUG-1 根因，`"   "` 被存為三個空白 → 同修正（`strip()` 自動正規化為 `""`）
3. **BUG-3：merge 來源不存在靜默回 200** — merge handler 只檢查目標存在，未檢查來源；`data_manager.merge_categories` 靜默回 `{updated:0, deleted:0}` → 加入來源存在檢查，不存在回 422
4. **BUG-4：允許跨類型 merge（E→I）** — 無類型一致驗證，merge 會將交易的 `類型` 欄位改掉，導致支出變收入，報表數字錯誤 → 加入 `if 來源類型 != 目標類型` → 422
5. **BUG-5：`GET /api/categories?type=X` 回 200 空陣列 / `DELETE` body 無效 type 靜默回 404** — query param 與 body 皆缺少類型驗證 → GET handler 加入 `type not in ("E","I")` 回 422；`CategoryDelete` 加入 `validate_type` validator

---

### Step 5：MyAB 匯入（✅ 完成）

**實作內容：**
- `import_export.py`：MyAB CSV 解析核心；UTF-8 BOM 自動去除；A/L 類型過濾；日期 YYYY/MM/DD → YYYY-MM-DD；金額取絕對值；無效日期/金額（≤0）計入 filtered_count；批次共用建立時間
- `frontend/import.html`：三步驟匯入頁（拖放上傳 → 預覽/確認 → 完成）；摘要卡片（原始/已過濾/新增/重複）；全部新分類清單；前 5 筆交易樣本；「繼續匯入」/「查看列表」按鈕
- `frontend/style.css`：新增步驟徽章（`.step-badge`）與拖放區（`.drop-zone`）樣式
- `app.py`：`POST /api/import/preview`（副檔名驗證、10MB 大小限制、過期 token 清理）；`POST /api/import/confirm`（回 410 Gone）；`_preview_store` TTL 10 分鐘

**測試（83 tests，全部通過）：**
- `tests/unit/test_import_export.py`（17 tests）：解析邏輯、BOM、過濾規則、id 唯一性
- `tests/api/test_import_api.py`（21 tests）：AT-009~010、安全性（副檔名/大小限制）、過期 token 清理
- `tests/api/test_import_functional.py`（45 tests）：FR-1～FR-7 全規格驗證

**程式碼審查後修正（2026-04-09）：**
1. **BUG-1：金額解析失敗 fallback 為 0** — `except` 捕捉 ValueError 時 `amount=0`，0 金額 E/I 行會寫入 DB → 加入 `amount <= 0` 判斷，計入 `filtered_count`
2. **BUG-2：日期空白或格式錯誤不過濾** — 空日期寫入 DB 為空字串 → 加入 regex 驗證（`^\d{4}-\d{2}-\d{2}$`），不合格計入 `filtered_count`
3. **BUG-3：`_preview_store` 記憶體洩漏** — 用戶放棄 preview 後 token 永久殘留 → 新增 `_cleanup_preview_store()`，每次 preview 呼叫時清理
4. **BUG-4：無上傳大小限制** — 可能耗盡伺服器記憶體 → 加入 10MB 限制，超過回 413
5. **BUG-5：無後端副檔名驗證** — 前端 `accept=".csv"` 可繞過 → 加入 `.endswith(".csv")` 檢查

**功能需求測試結論（2026-04-09）：**
- 45 個功能需求案例（FR-1~FR-7）首次執行全部通過，無新缺陷
- 確認設計行為：備註不在去重鍵（FR-5）、帳戶欄不在去重鍵（FR-5）、批次內自去重（FR-5）、A/L 分類不加入 categories（FR-3）均符合規格

---

### Step 6：CSV 匯出（✅ 完成，2026-04-09）

**實作內容：**
- `data_manager.py`：新增 `export_transactions(from_date, to_date)` — 篩選日期範圍並依日期 ASC + 建立時間 ASC 排序
- `app.py`：新增 `GET /api/export?from=...&to=...` — 驗證日期格式與先後順序、產生 CSV、`utf-8-sig` 編碼（含 BOM）、`Content-Disposition` 指定下載檔名 `daily_ledger_{YYYYMMDD}_{YYYYMMDD}.csv`
- `frontend/export.html`：頁面載入時自動取 `/api/transactions/date_range` 作為預設日期；快捷按鈕（全部/本年/近12月/本月）；日期變更後防抖 400ms 更新預覽筆數；無資料時顯示警示並隱藏表單；下載以 `<a>` click 觸發，保留瀏覽器原生檔名
- 新增 `import csv, io, StreamingResponse` 至 `app.py`

**手動驗證（2026-04-09）：**
- `export_transactions` 篩選結果正確（2 筆），排序為日期 ASC
- `GET /api/export` 200 OK，Content-Type = `text/csv; charset=utf-8-sig`，檔名格式正確
- 反向日期（from > to）回 422
- 日期格式錯誤回 422
- AT-011 / AT-012 / AT-018 手動驗證通過

**AT-017 round-trip 一致性**：留待 Step 8 整合測試階段（需有完整匯入資料後驗證匯出再匯入筆數一致）

**程式碼審查修正（2026-04-09）：**
1. **BUG-1：日期值驗證不足** — 正規式 `^\d{4}-\d{2}-\d{2}$` 只驗格式，不擋 `2025-13-01`；`app.py` 加入 `datetime.strptime` 二次驗證
2. **BUG-2：Content-Type charset 非標準** — `text/csv; charset=utf-8-sig` 使用非 IANA 標準名稱；改為 `text/csv; charset=utf-8`（BOM 已含於 bytes 內容）
3. **BUG-3：前端缺 from > to 防衛** — `export.html` 下載按鈕點擊只檢查空值，未阻擋日期前後顛倒；加入 `from > to` 判斷

**測試（60 tests，全部通過）：**
- `tests/unit/test_data_manager.py`（+8 tests）：`export_transactions` 篩選、排序、邊界
- `tests/api/test_export_api.py`（18 tests）：AT-011/012/018、Content-Type、BOM、Content-Disposition、日期驗證
- `tests/api/test_export_functional.py`（34 tests）：FR-EXP-1~8 全規格（日期範圍、排序、CSV 格式、檔名、輸入驗證、特殊字元、無分頁限制、round-trip 一致性）

**功能需求測試結論（2026-04-09）：**
- 34 個功能需求案例（FR-EXP-1~FR-EXP-8）首次執行全部通過，無新缺陷
- AT-017 round-trip 確認：匯出欄位（含 `id`/`建立時間`）與 MyAB 匯入格式不同，無法直接再匯入；留 Step 8 決策

---

### Step 7：統計報表（✅ 完成，2026-04-09）

**實作內容：**
- `report_engine.py`：`monthly_report` / `category_report` / `trend_report`；`_month_range` 輔助函式（空月補 0 核心）
- `frontend/report.html`：頁面頂部日期範圍快捷（本月/本季/本年/近12月/全部/自訂）預設近12月；Chart.js 三圖（月度長條+淨額折線、分類甜甜圈+自訂圖例、趨勢折線）；分類佔比支援 E/I 切換與 main/sub 切換；趨勢圖支援 category_main 下拉篩選
- `app.py`：新增 `GET /api/report/monthly`、`GET /api/report/category`（`type=E/I`、`level=main/sub`）、`GET /api/report/trend`（`category_main`）；共用 `_parse_report_dates` 驗證與預設值（近 12 個月）

**程式碼審查修正（2026-04-09）：**
1. **BUG-1：月度圖缺頂層 `type: "bar"`** — Chart.js 4.x 混合圖（bar + line）必須設定頂層 type，否則不渲染；加入 `type: "bar"`
2. **BUG-2：categoryLegend innerHTML XSS** — 分類名稱直接插入 innerHTML，`"` 字元會破壞 attribute；改用 DOM API（`textContent`）+ `_esc()` 輔助函式

**測試（111 tests，全部通過）：**
- `tests/unit/test_report_engine.py`（22 tests）：`_month_range`、`monthly_report`、`category_report`、`trend_report` 單元測試
- `tests/api/test_report_api.py`（28 tests）：三支 API、AT-014（空月補0）、AT-015（與交易 summary 一致）、輸入驗證、預設值
- `tests/api/test_report_functional.py`（61 tests）：FR-RPT-1~6 全規格（月度收支、分類佔比、月度趨勢、輸入驗證、跨年邊界、AT-015 一致性）

**功能需求測試結論（2026-04-09）：**
- 61 個功能需求案例（FR-RPT-1~FR-RPT-6）首次執行全部通過，無新缺陷
- AT-014 確認：空月補 0 邏輯正確（跨年、三年範圍均驗證）
- AT-015 確認：monthly income/expense/net 加總 == transactions summary；category total == summary；trend == monthly（無篩選）；level=sub total == level=main total

**改進事項（留 Step 8）：**
1. 月度收支圖缺 E/I/all 切換 UI（前端無此按鈕，API 支援但未開放）→ 原設計 5.3 即為 type=all，不加 toggle
2. 「全部」模式無資料時退回「今日」，語意稍混淆（應提示「無交易資料」）→ **Step 8 已修正**
3. 前後端「近12月」計算各自獨立（客戶端明確帶參數時無影響，僅影響直接呼叫 API 場景）→ 無影響，不修正

---

### Step 8：收尾（✅ 完成，2026-04-10）

**實作內容：**
- `tests/integration/__init__.py`：建立整合測試目錄
- `tests/integration/test_import_to_report_flow.py`：匯入→列表/報表/匯出一致性（19 tests）
  - `TestRealCsvImport`（4 tests）：真實 975 筆 CSV 匯入驗證、去重、報表一致性（skipif 無真實 CSV）
  - `TestEdgeCharacters`（4 tests）：逗號、引號、中文特殊字元、換行
  - `TestRoundTrip`（4 tests）：AT-017 round-trip 欄位/筆數/金額/不修改 DB
- `tests/integration/test_merge_consistency.py`：合併一致性（15 tests）
  - `TestBasicMergeConsistency`（4 tests）：交易引用更新、來源分類移除、count 增加、回傳值
  - `TestMergeReportConsistency`（3 tests）：合併後金額不變、月報一致、分類報表正確
  - `TestMergeExportConsistency`（2 tests）：匯出反映合併結果、金額不變
  - `TestMainCategoryMerge`（2 tests）：主類合併（次類空）、無交易引用合併
- `frontend/report.html`：修正「全部」模式無資料時提示錯誤而非 fallback 到今日
- `tests/integration/test_step8_level2.py`（2026-04-10 新增）：Level 2 整合測試自動化補強（30 tests）
  - `TestAtomicity`（4 tests）：寫入失敗不損壞主檔、不留孤立 .tmp、init 清理殘留、分類先寫後主檔失敗
  - `TestPowerBiCsvFormat`（9 tests）：BOM 存在、日期 YYYY-MM-DD、整數金額、欄位標題、無額外欄、E/I 類型值、日期範圍篩選、Content-Type、Content-Disposition 檔名
  - `TestImportPreviewNewCatsFromNewRows`（3 tests）：預覽新分類取自 new_rows 而非全部 rows（Bug-1 修正驗證）
  - `TestCategoryMergeTypeValidation`（6 tests）：CategoryMerge 模型驗收「E」/「I」類型欄（Bug-2 修正驗證）
  - `TestImportCsvHeaderValidation`（8 tests）：缺少必要欄位（類型/日期/金額）回 400，附欄位名稱（Bug-3 修正驗證）

**程式碼審查修正（2026-04-10，搭配 test_step8_level2.py）：**
1. **Bug-1：import_preview 從全部 rows 擷取新分類** — 應從 `new_rows`（未重複行）取分類，避免已存在分類被誤報為「新分類」→ `app.py` 修正（修正 15 行）
2. **Bug-2：CategoryMerge 無類型驗證** — `來源類型`/`目標類型` 未驗證合法值，可傳入任意字串 → `app.py` 新增 `@field_validator` 限制 `{"E","I"}`
3. **Bug-3：parse_myab_csv 無必要欄位驗證** — 缺少 `類型`/`日期`/`金額` 欄時拋出 KeyError 而非 400 → `import_export.py` 新增 `_REQUIRED_HEADERS` 前置驗證

**測試（49 tests，全部通過）：**
- `tests/integration/test_import_to_report_flow.py`（8 tests + 4 skipped）
- `tests/integration/test_merge_consistency.py`（15 tests）
- `tests/integration/test_step8_level2.py`（30 tests）← Level 2 自動化補強（2026-04-10 新增）

**Level 2 整合測試驗收狀態：**
1. 匯入驗證（975 筆）：✅ TestRealCsvImport::test_import_count（skipif）
2. 去重測試：✅ TestRealCsvImport::test_duplicate_import_no_new_rows（skipif）
3. 合併功能：✅ TestMergeConsistency 全套
4. 原子性：✅ TestAtomicity（4 tests，test_step8_level2.py）— 寫入失敗不損壞主檔、無孤立 .tmp、啟動清除、分類先寫主檔後失敗驗證
5. 邊界字元：✅ TestEdgeCharacters 全套
6. Round-trip（AT-017）：✅ TestRoundTrip 全套
7. 報表驗證：✅ test_import_then_report_monthly_consistent
8. Power BI 驗證：✅ TestPowerBiCsvFormat（9 tests，test_step8_level2.py）— BOM、YYYY-MM-DD 格式、整數金額、欄位名稱、E/I 類型值、日期篩選、Content-Type、Content-Disposition

---

### 自動測試案例對應表（AT-001 ~ AT-018）

| 編號 | 案例 | 狀態 | 所在測試檔 |
|------|------|------|----------|
| AT-001 | POST /api/transactions 合法新增 | ✅ | test_transactions_api.py |
| AT-002 | POST /api/transactions 非法金額 | ✅ | test_transactions_api.py |
| AT-003 | GET /api/transactions 篩選+分頁 | ✅ | test_list_filtering.py |
| AT-004 | PUT /api/transactions/{id} 全覆蓋 | ✅ | test_list_filtering.py |
| AT-005 | DELETE /api/transactions/{id} | ✅ | test_list_filtering.py |
| AT-006 | POST /api/categories 重複新增 | ✅ | test_categories_api.py |
| AT-007 | DELETE /api/categories 有引用 | ✅ | test_categories_api.py |
| AT-008 | POST /api/categories/merge | ✅ | test_categories_api.py |
| AT-009 | POST /api/import/preview | ✅ | test_import_api.py |
| AT-010 | POST /api/import/confirm token 過期 | ✅ | test_import_api.py |
| AT-011 | GET /api/export 範圍匯出 | ✅ | test_export_api.py / test_export_functional.py |
| AT-012 | GET /api/export 空範圍 | ✅ | test_export_functional.py |
| AT-013 | 去重鍵判定 | ✅ | test_data_manager.py |
| AT-014 | 報表 monthly 補空月份 | ✅ | test_report_api.py / test_report_functional.py |
| AT-015 | 匯入後報表一致性 | ✅ | test_report_api.py / test_report_functional.py |
| AT-016 | merge 後一致性 | ✅ | test_categories_api.py |
| AT-017 | round-trip 一致性 | ✅ | test_import_to_report_flow.py（TestRoundTrip，4 tests）|
| AT-018 | 匯出 UTF-8 BOM | ✅ | Step 6（utf-8-sig 編碼驗證通過）|

---

## 討論紀錄

### 2026-04-02（第一次）

- 確認需求與範圍（第一章全部議題）
- 儲存方式經比較 CSV / JSON 後決定採用 CSV

### 2026-04-02（第二次）

- 確認技術選型（第二章全部議題）
- 後端改為 FastAPI（比 Flask 更嚴謹的型別驗證）
- 前端採純 HTML/CSS/JS + Bootstrap 5，靜態資源本機化以支援離線使用
- 圖表採 Chart.js（本機化）
- 套件管理採 venv + requirements.txt
- 待續：從第三章「CSV 欄位設計」開始

### 2026-04-02（第三次）

- 確認 CSV 欄位設計（第三章全部議題）
- 主資料檔改名為 `main_db.csv`
- id：UUID4 前 8 碼
- 日期：`YYYY-MM-DD`（Excel/Power BI 原生支援，HTML input 原生格式）
- 金額：全部儲存正整數，收支由類型欄決定，Excel 分析更直覺
- 分類：獨立 `categories.csv`，可預建未使用的分類
- 帳戶：簡單三欄 `accounts.csv`，不含起始餘額
- accounts.csv 確認採三欄式（帳戶代碼/帳戶名稱/類型），不含起始餘額，不需查看帳戶餘額功能
- 待續：從第四章「API 路由設計」開始

### 2026-04-07（第四次）

- 確認 2.5 架構模式：採純前後端分離，FastAPI 僅提供 REST API（回傳 JSON），前端為純靜態 HTML/CSS/JS，不使用 Jinja2 templates
- 確認 3.7 帳戶功能：不需要，移除帳戶欄位、accounts.csv 及相關頁面與 API
- 確認 3.9 淨額欄：不需要，Power BI 用 measure 處理
- 確認 6.1 MyAB 匯入欄位對映：丟棄帳戶、金額取絕對值、日期格式轉換、自動產生 id 與建立時間
- 確認 6.1a A/L/Equity 過濾：直接丟棄（因已移除帳戶功能）
- 確認 6.1b 分類差異：聯集累積 + 人工合併；分類管理頁需提供「合併分類」功能
- 確認 6.2 交易去重：以「日期+類型+主類+次類+金額+明細」為唯一鍵
- 建議匯入順序：由舊到新（舊備份 → 新備份 → transactions.csv）
- 確認 3.8 年月欄：不需要，Power BI 自動建立日期階層
- 金額正負號議題重新檢視：維持 3.4 原決議（正整數 + 類型欄決定方向）
- 第三章全部收尾完成
- 確認 4.1 頁面路由規劃：採「單一 APP」架構——FastAPI 用 `StaticFiles` 掛載 `frontend/`，單一 process 同時提供 API 與靜態前端（port 8000），整個專案目錄可攜式（筆電↔桌機移植只需複製目錄）
- ~~確認新增首頁 Dashboard：`index.html` 改為功能切換中心，原記帳輸入頁改名為 `entry.html`~~（**本條於同次討論後段被推翻**：最終決議改為 `index.html` = 記帳輸入頁，所有頁面共用頂部 navbar 作為功能切換，不另設 Dashboard 頁、不改檔名）
- 確認 4.2 交易 CRUD API：端點、Response 格式（HTTP status + 純資料）、查詢篩選（含金額區間）、分頁（預設 100、上限 500，依每月最多 77 筆實測）、修改採 PUT 全覆蓋、刪除採硬刪除
- 確認 4.3 分類管理 API：GET（**平鋪陣列** `[{類型,主類,次類}, ...]`，與 categories.csv 1:1 對應）/POST/DELETE/merge 四個端點；不提供獨立改名 API（統一由 merge 處理）；GET 支援 `?type=E/I` 篩選與 `?include_count=1` 附加交易引用筆數（採平鋪而非巢狀的關鍵理由：`include_count` 擴充無破壞性、分類管理頁列表可直接使用）
- 確認 4.4 匯入/匯出 API：匯入兩階段（preview + confirm）、暫存採記憶體 dict + TTL 10 分鐘、匯出支援篩選參數
- 確認 6.3 匯出格式：只支援本系統 CSV 原生格式，不提供 MyAB 相容、不提供 JSON
- 確認 4.5 統計報表 API：monthly / category / trend 三支端點；monthly 與 trend 支援 category_main 篩選；預設最近 12 個月；佔比由後端算好
- **第四章全部完成** ✅
- 待續：第五章（前端頁面細節）、第七章（實作順序與驗證）

### 2026-04-07（第五次）

- 確認 5.1 記帳輸入頁：日期欄左右加 [前一日]/[下一日] 按鈕（批次輸入用）；類型 button group；連動下拉；新增成功後保留日期/類型、清空其他欄位；底部顯示今日已記錄列表（最多 10 筆）
- 確認 5.2 列表頁：篩選區可收合、摘要列（總筆數/收入/支出/淨額）、Modal 編輯、刪除二次確認、固定排序、不支援批次操作、分頁 100
- 確認 5.3 報表頁：三圖共用日期範圍快捷按鈕；月度收支長條圖 + 淨額折線疊加；分類佔比甜甜圈（預設支出，可切支出/收入、主類/次類）；月度趨勢三線（收/支/淨額）+ 可選分類篩選；不支援 drill-down；固定色系
- 確認 5.4 分類管理頁：類型 tab 切換；上方內嵌新增表單；樹狀展開列表；顯示交易引用筆數（API `?include_count=1`）；改名按鈕內部呼叫 merge API；合併 modal 即時試算影響筆數
- 確認 5.5 匯入頁：三步驟流程；新分類自動匯入；匯入失敗全有全無（先寫暫存檔再 rename）

### 2026-04-07（第六次）

- 新增 5.7 匯出頁設計（export.html）：日期範圍選擇器、快捷按鈕、預覽筆數、下載按鈕；新增 API `GET /api/transactions/date_range`
- 確認 6.3 匯出範圍與格式：僅匯出 main_db.csv（不含 categories.csv）、UTF-8 with BOM、不實作 MyAB 相容格式
- 確認匯出檔名格式：`daily_ledger_{YYYYMMDD}_{YYYYMMDD}.csv`（純 ASCII、按名稱排序天然依時序、不同範圍不撞名）
- 金額正負號處理：維持 3.9 決議（正整數 + 類型欄），Power BI 端以 Power Query 計算資料行 `if [類型]="E" then -[金額] else [金額]` 產生淨額
- navbar 擴為 6 項：`記帳 \| 列表 \| 報表 \| 分類 \| 匯入 \| 匯出`
- **修正 4.3 GET 格式**：先決議為巢狀格式 → 再次討論後改回**平鋪陣列**（理由：與 categories.csv 1:1 對應、`include_count` 擴充無破壞性、分類管理頁列表可直接使用）
- 待續：5.6 整體 UI 風格、第七章 實作順序與驗證

### 2026-04-07（第七次）

- 確認 5.6 整體 UI 風格與 CSS 方案：A3 冷色系藍/灰主題、系統字體+中文 fallback、金額採 tabular-nums、基本響應式（桌機優先）、單一 style.css、**Bootstrap Icons 唯一 Icon 方案（不使用 emoji）**、不支援深色模式、Toast + table-hover 互動回饋、前端 JS 拆為 api/format/toast/navbar 四個 module
- 重要調整：原 navbar 標題 `📒 Daily Ledger` 改為 `<i class="bi bi-journal-text"></i> Daily Ledger`；所有原 emoji 改用 Bootstrap Icons
- **第五章全部完成** ✅
- 待續：第七章 實作順序與驗證

### 2026-04-09（第九次）

- Step 4 補充測試：針對分類管理 API 進行缺口分析，新增 `test_categories_extra.py`（17 tests）
- 新增測試涵蓋：response shape 驗證、次類空白正規化、特殊字元（逗號、雙引號）、GET type 驗證、DELETE type 驗證、merge 來源不存在、merge 跨類型、merge response shape、merge 影響範圍隔離、204 無 body、插入順序保留等
- 發現並修正 5 個 bug（BUG-1 ~ BUG-5，見 Step 4 詳細記錄）
- **Step 5 實作完成**：`import_export.py`、`frontend/import.html`、匯入 API（preview/confirm）
- **Step 5 程式碼審查**：發現並修正 5 個 bug（金額=0 不過濾、無效日期不過濾、記憶體洩漏、無大小限制、無副檔名驗證）
- **Step 5 功能需求測試**：新增 `test_import_functional.py`（45 tests），覆蓋 FR-1~FR-7 全規格，首次執行全部通過
- **測試總數 230，全部通過**

---

### 2026-04-08（第八次完成）

- 確認 7.2 驗證方式：採 A 三層
  - Level 1：每個 Step 完成時輕量手動驗收核心流程
  - Level 2：Step 8 收尾時執行整合測試清單（去重、合併、原子性、邊界字元、Power BI 驗證）
  - Level 3：Chrome + Edge 必驗，Firefox 選配
- 確認補充：後端 API 邏輯撰寫基本 pytest（data_manager / import_export 核心函式）
- 確認 7.1 Step 優先順序：採 A（Step 6 = CSV 匯出提前，Step 7 = 統計報表延後）
- **第七章全部完成** ✅
- 至此所有章節定案，進入實作階段

---

### 2026-04-09（第十次）

- **Step 6 實作完成**：`export_transactions`、`GET /api/export`、`frontend/export.html`
- **Step 6 程式碼審查**：發現並修正 3 個問題（日期值驗證不足、Content-Type charset 非標準、前端缺 from>to 防衛）
- **Step 6 功能需求測試**：新增 `test_export_api.py`（18 tests）、`test_export_functional.py`（34 tests），8 個單元測試追加至 `test_data_manager.py`，共 60 tests，全部通過
- **Step 7 實作完成**：`report_engine.py`（三支聚合函式）、`GET /api/report/*`（三端點）、`frontend/report.html`（三圖 + 日期快捷）
- **Step 7 程式碼審查**：發現並修正 2 個問題（Chart.js 混合圖缺頂層 type、categoryLegend innerHTML XSS）
- **Step 7 功能需求測試**：新增 `test_report_engine.py`（22 tests）、`test_report_api.py`（28 tests）、`test_report_functional.py`（61 tests），共 111 tests，全部通過
- **測試總數 401，全部通過**（Step 1–7 完成，剩 Step 8 收尾）

### 2026-04-10（第十一次）

- **Step 8 完成**：整合測試 `test_import_to_report_flow.py`（19 tests）、`test_merge_consistency.py`（15 tests）、`report.html` 無資料提示修正
- **Step 8 Level 2 自動化補強**：新增 `test_step8_level2.py`（30 tests）強化原子性、Power BI 格式、3 個 Bug 修正驗證
- **程式碼審查修正**：Bug-1（import_preview new_rows 擷取）、Bug-2（CategoryMerge 類型驗證）、Bug-3（parse_myab_csv 必要欄位驗證）
- **測試總數 454，全部通過（0 skipped）**（Step 1–8 全數完成）

---

## 新需求討論（2026-04-13 起）

> 搭配 `Daily_Ledger_新增需求開發計畫.md` 使用，逐項討論並記錄決議。

### 狀態說明

- ✅ 已確認：討論完成，有明確結論
- 🔄 討論中：尚在討論，未有定論
- ⬜ 待討論：尚未開始討論

---

### 新需求議題清單

| # | 議題 | 狀態 | 決議 |
|---|------|------|------|
| R-01 | 列表頁篩選條件：新增月份快捷按鈕 | ✅ | 見下方 |
| R-02 | 分類管理頁：新增手動排序功能，排序結果套用至所有下拉選單 | ✅ | 見下方 |
| R-03 | 各頁面新增明顯頁面標題，方便辨認目前所在頁面 | ✅ | 見下方 |

### 需求彙總（2026-04-13 定案）

| 需求 | 頁面 | 類型 | 核心變更 | 複雜度 |
|------|------|------|----------|--------|
| R-01 月份快捷按鈕 | `list.html` | 純前端 | 新增三個按鈕 + 日期連動邏輯 | 低 |
| R-02 分類手動排序 | `categories.html` + 後端 | 前後端 | 新增 `sort_order` 欄位、reorder API、上移/下移按鈕 | 高 |
| R-03 頁面標題 | 六個 HTML 頁面 | 純前端 | 各頁加 `<h5>` 標題列 | 極低 |

**建議實作順序：R-03 → R-01 → R-02**

---

### R-01：列表頁篩選條件新增月份快捷按鈕

**需求描述：**
在 `list.html` 篩選條件區塊中，「篩選條件」標題列與「開始日期」標籤列之間，插入一排三個快捷按鈕：`上一月` / `本月` / `下一月`。

**決議：**
- 按鈕位置：篩選條件區塊內，緊接在標題列（含「收合」按鈕那列）下方、開始日期標籤列上方
- 按鈕文字：`上一月` / `本月` / `下一月`
- 預設行為：頁面載入時自動套用「本月」，開始日期與結束日期分別填入當月第一天與最後一天（格式 `YYYY-MM-DD`）
- 連動規則：點擊任一按鈕 → 自動更新開始日期與結束日期欄位，並立即觸發「套用篩選」（等同按下套用篩選按鈕）
- 手動修改日期欄位後，三個按鈕均不高亮（無 active 狀態）
- 按鈕樣式：沿用既有 Bootstrap outline 風格，active 按鈕有明顯 active 狀態標示
- 影響範圍：`frontend/list.html`（純前端，無需後端修改）

---

### R-02：分類管理頁新增手動排序功能

**需求描述：**
在 `categories.html` 的分類樹狀列表中，為每筆分類（主類與次類）新增「↑ 上移」「↓ 下移」按鈕，讓使用者手動調整顯示順序。排序結果永久儲存，並影響所有頁面的分類下拉選單顯示順序。

**決議：**

**UI 互動：**
- 操作方式：按鈕式（不使用拖曳），參考 MyAB 風格
- 主類列：右側加「↑ 上移」「↓ 下移」兩個按鈕（位於合並按鈕左側）
- 次類列：右側加「↑ 上移」「↓ 下移」兩個按鈕（位於改名/刪除按鈕左側）
- 邊界處理：已在最頂的分類「↑ 上移」按鈕 disabled；已在最底的「↓ 下移」按鈕 disabled
- 排序範圍獨立：主類在同類型（E/I）內排序，次類在同主類內排序，跨主類不可互移

**資料儲存：**
- `categories.csv` 新增 `sort_order` 整數欄位（欄位格式：`類型,主類,次類,sort_order`）
- `sort_order` 為同一排序範圍內的序號（從 1 起，不需全域唯一）
- 既有資料遷移：後端 `init_data_files()` 啟動時若偵測到無 `sort_order` 欄位，自動依現有排列順序補齊（不改變現有順序）
- 新增分類時：`sort_order` 自動設為同範圍最大值 + 1（插入末尾）

**排序 API：**
- 新增端點 `POST /api/categories/reorder`，body：`{類型, 主類, 次類, direction: "up"|"down"}`
- 後端執行交換相鄰 `sort_order`，回傳 200 OK
- 前端收到回應後重新 fetch 分類列表並重繪（不做樂觀更新）

**影響範圍（下拉選單排序）：**
- `GET /api/categories` 回傳結果改為依 `sort_order` 排序（原為依 CSV 寫入順序）
- 影響頁面：`frontend/index.html`（記帳主類/次類下拉）、`frontend/list.html`（篩選主類/次類下拉）、`frontend/categories.html`（分類樹狀列表）

**影響檔案：**
- `data/categories.csv`（新增欄位）
- `data_manager.py`（遷移邏輯、reorder 邏輯、GET 排序改為 sort_order）
- `app.py`（新增 `/api/categories/reorder` 端點）
- `frontend/categories.html`（新增上移/下移按鈕）
- `frontend/index.html`、`frontend/list.html`（下拉選單順序自動跟隨，無需修改邏輯，僅受 API 回傳順序影響）

---

### R-03：各頁面新增明顯頁面標題

**需求描述：**
切換功能頁面後，使用者無法快速辨認目前所在頁面。navbar 的 active 樣式字體小且位於右上角，不夠顯眼。需在每個頁面的內容區頂部加入明顯的頁面標題。

**決議：**

- 每個頁面的主內容區最上方加入一個頁面標題列（`<h4>` 或同等層級），含對應 Bootstrap Icon 與中文頁面名稱
- 標題樣式：與既有 UI 風格一致（深色文字 + icon，不加底線或分隔線），不需加背景色塊
- 六個頁面標題如下：

| 頁面 | 檔案 | 標題文字 |
|------|------|----------|
| 記帳輸入 | `index.html` | `記帳` |
| 交易列表 | `list.html` | `交易列表` |
| 統計報表 | `report.html` | `統計報表` |
| 分類管理 | `categories.html` | `分類管理` |
| 匯入 | `import.html` | `匯入` |
| 匯出 | `export.html` | `匯出` |

- Icon 沿用各頁面 navbar 已使用的同款 Bootstrap Icon
- 影響範圍：`frontend/` 下六個 HTML 檔，純前端修改，無需動後端

---

**R-02 後置設定：依指定順序套用初始排序**

R-02 實作完成後，直接修改 `categories.csv` 的 `sort_order` 欄位套用以下順序（不透過 UI 逐筆上移/下移操作）。

實作前需先確認下列分類是否存在，缺少者須先新增：
- `E, 月租費, ""`
- `E, 無謂損失, ""`
- `E, 娛樂交際, 淘寶購物`

目標排序：

| 類型 | 主類 | 次類 | sort_order（主類） | sort_order（次類） |
|------|------|------|------|------|
| I | 薪資 | | 1 | — |
| I | 其他收入 | | 2 | — |
| E | 給父母親錢 | | 1 | — |
| E | 餐飲費 | | 2 | — |
| E | 餐飲費 | 早餐 | — | 1 |
| E | 餐飲費 | 午餐 | — | 2 |
| E | 餐飲費 | 晚餐 | — | 3 |
| E | 餐飲費 | 家庭用餐 | — | 4 |
| E | 餐飲費 | 飲料 | — | 5 |
| E | 餐飲費 | 宵夜零食 | — | 6 |
| E | 生活雜支 | | 3 | — |
| E | 書籍雜誌 | | 4 | — |
| E | 加油 | | 5 | — |
| E | 加油 | 機車加油 | — | 1 |
| E | 加油 | 汽車加油 | — | 2 |
| E | 停車費 | | 6 | — |
| E | 停車費 | 機車停車費 | — | 1 |
| E | 停車費 | 汽車停車費 | — | 2 |
| E | 機車修理費 | | 7 | — |
| E | 汽車修理費 | | 8 | — |
| E | 電腦 | | 9 | — |
| E | 電腦 | 主機配備 | — | 1 |
| E | 電腦 | 週邊附件 | — | 2 |
| E | 水電固定支出 | | 10 | — |
| E | 教育訓練 | | 11 | — |
| E | 醫療健康 | | 12 | — |
| E | 健身運動 | | 13 | — |
| E | 衣物 | | 14 | — |
| E | 娛樂交際 | | 15 | — |
| E | 娛樂交際 | 旅遊 | — | 1 |
| E | 娛樂交際 | 淘寶購物 | — | 2 |
| E | 稅負保費 | | 16 | — |
| E | 月租費 | | 17 | — |
| E | 無謂損失 | | 18 | — |
