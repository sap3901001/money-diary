# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 專案概覽

本 repository 包含兩個各自獨立的子專案：

| 子專案 | 說明 |
|--------|------|
| `daily-ledger/` | FastAPI 個人記帳網頁應用（port 8000） |
| `myab-export/` | MyAB 記帳簿二進位格式逆向匯出工具 |

開發文件（歷史規劃、設計筆記、CLAUDE.md 備份）統一存放於 `development-plan/`。

---

## daily-ledger

### 常用指令

```bash
# 啟動（WSL/Linux）
cd daily-ledger && bash start.sh

# 關閉（WSL/Linux）
bash stop.sh

# 啟動（Windows cmd）
cd daily-ledger && start.bat

# 關閉（Windows cmd）
stop.bat

# 執行全部測試（WSL/Linux）
cd daily-ledger && venv/bin/pytest tests/

# 執行全部測試（Windows cmd）
cd daily-ledger && venv-win\Scripts\pytest tests\

# 執行單一測試檔（WSL/Linux）
venv/bin/pytest tests/unit/test_data_manager.py

# 執行含 coverage（WSL/Linux）
venv/bin/pytest tests/ --cov=. --cov-report=term-missing
```

`start.sh` 與 `start.bat` 首次執行時會自動建立 venv 並安裝 `requirements.txt`，無需手動操作。

**venv 目錄分離**：WSL 使用 `venv/`（Linux 二進位），Windows cmd 使用 `venv-win/`（Windows 二進位），兩者不相容、不可混用。

**`.bat` 檔換行格式**：從 WSL 寫入的 `.bat` 檔預設為 LF，必須轉換為 CRLF 才能在 Windows cmd 正常執行。轉換方式：
```bash
python3 -c "
import pathlib, sys
for f in sys.argv[1:]:
    p = pathlib.Path(f)
    p.write_bytes(p.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
" start.bat stop.bat
```

### 架構

單一 FastAPI process 同時 serve REST API 與靜態前端：

```
app.py              ← FastAPI 路由、Pydantic 模型、匯入暫存（_preview_store）
data_manager.py     ← CSV 讀寫（原子性）、分類與交易的全部業務邏輯
import_export.py    ← 解析 MyAB CSV（UTF-8 BOM）→ 轉換為內部資料格式
report_engine.py    ← 月度/分類/趨勢/前十大支出報表聚合計算
frontend/           ← 靜態 HTML + Bootstrap 5 + Chart.js（無前端框架）
data/               ← main_db.csv（交易記錄）、categories.csv（分類設定）
tests/              ← unit/、api/、integration/ 三層
```

`app.py` 透過 `import data_manager as dm`、`import import_export as ie`、`import report_engine as re_` 引入其他模組，所有模組須在同一目錄執行。

### 關鍵設計決策

- **路由順序**：`/transactions/date_range` 必須在 `/transactions/{id}` 之前定義，否則 `date_range` 會被當作 id 捕捉。`StaticFiles` 掛載必須在所有 API 路由之後。
- **CSV 原子性寫入**：所有 CSV 寫入先存 `.tmp`，再用 `os.replace()` 覆蓋，防止寫入中途崩潰產生損壞檔案。
- **匯入兩階段**：`POST /import/preview` 上傳 CSV → 回傳 `preview_token`（TTL 10 分鐘，存於記憶體 `_preview_store`）；`POST /import/confirm` 帶 token 執行實際匯入。
- **去重鍵**：日期 + 類型 + 主類 + 次類 + 金額 + 明細，六欄組合一致視為重複。
- **分類排序**：`categories.csv` 含 `sort_order` 欄位（整數），用於自訂顯示順序；舊版無此欄時由 `_migrate_sort_order()` 補齊。
- **測試 fixture**：測試使用 `monkeypatch` 將 `dm.DATA_FILE` / `dm.CAT_FILE` 重導至暫存路徑，不污染 `data/`。
- **統計報表圖表順序**：月度收支 → 分類佔比 → 支出金額前十大項目 → 月度趨勢。前十大支出圖表有獨立的月份/年度篩選下拉，不隨全域日期範圍聯動。
- **前十大支出圖表**：`report_engine.top_expense_report()` 回傳指定期間金額最大的前 N 筆支出（逐筆，不依分類彙總）；API 端點為 `GET /api/report/top-expense?from=&to=`；Chart.js 水平柱狀圖（`indexAxis: y`），右側以 inline plugin 標註金額。

### 資料欄位

`main_db.csv`：`id, 日期, 類型, 類別主類, 類別次類, 金額, 明細, 備註, 建立時間`  
`categories.csv`：`類型, 主類, 次類, sort_order`  
類型值：`E`（支出）、`I`（收入）

---

## myab-export

### 常用指令

```bash
# 執行（WSL/Linux）
cd myab-export && bash start.sh
# 或直接
python3 myab_export.py

# 執行（Windows cmd）
cd myab-export && start.bat
```

無測試套件，無常駐服務（執行完畢即結束），無需關閉腳本。

### 架構

單一檔案腳本（`myab_export.py`，284 行），僅用標準庫（`csv`、`os`、`struct`、`sys`）：

```
source/   ← 放入 MyAB 的 .abd 或 .mbu 檔案
target/   ← 匯出結果（CSV）
```

**自動偵測模式**（`detect_mode()`）：
- `db 模式`：`source/Main.abd` 存在 → 讀本機資料庫（可選加 `Main1.abd` 備註、`Accounts.abd` 科目）
- `mbu 模式`：`source/*.mbu` 存在 → 從備份封包提取

**輸出檔案**：
- `target/transactions.csv`（db 模式）
- `target/accounts.csv`（db 模式，若有 Accounts.abd）
- `target/backup_{stem}.csv`（mbu 模式，每個 .mbu 各一份）

### 關鍵解碼邏輯

- **記錄大小**：`Main.abd` 每筆 284 bytes（`REC_SIZE`）
- **金額解碼**（`decode_amount`）：4 bytes LE → 位元組反序後補 4 個 `\x00` 組成 8 bytes → 解為 IEEE 754 double → 除以 100 → 四捨五入為整數台幣
- **備註對齊**（`Main1.abd`）：`notes[n]` 對應原始交易索引 `n+1`（差一位）
- **科目名稱**（`Accounts.abd`）：名稱含 `.` 時分割為 `主類.次類`；不含則整串為主類
- **Big5 解碼**：所有中文字串以 Big5 儲存，輸出轉 UTF-8

輸出 CSV 使用 UTF-8 BOM（`utf-8-sig`），可直接在 Excel 開啟不亂碼。
