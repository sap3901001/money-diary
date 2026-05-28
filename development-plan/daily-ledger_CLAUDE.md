# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用指令

```bash
# 啟動開發伺服器（http://localhost:8000）
source venv/bin/activate
uvicorn app:app --port 8000 --reload

# 執行測試
pytest tests/                          # 全部 500 tests
pytest tests/unit/                     # 只跑單元測試
pytest tests/api/                      # 只跑 API 測試
pytest tests/ -k "test_merge"          # 執行特定測試
pytest tests/ -v                       # 詳細輸出
pytest tests/ --cov=. --cov-report=term-missing  # 含覆蓋率

# 安裝依賴（requirements.txt 已包含 runtime + pytest/httpx/pytest-cov）
pip install -r requirements.txt
```

## 架構概覽

單一 FastAPI process 同時 serve REST API（`/api/*`）與靜態前端（`/`）。

```
app.py            ← FastAPI 路由 + Pydantic 驗證
data_manager.py   ← CSV 讀寫（MAIN_DB / CATEGORIES_CSV），所有業務邏輯
import_export.py  ← MyAB CSV 解析（A/L 過濾、欄位對映）與分類提取
report_engine.py  ← 報表聚合（monthly/category/trend）
frontend/
  *.html          ← 各功能頁（index/list/report/categories/import/export）
  style.css
  js/             ← api.js / format.js / toast.js / navbar.js
  lib/            ← 第三方函式庫（Bootstrap、Bootstrap Icons、Chart.js）
tests/
  unit/           ← 直接測試 data_manager / import_export / report_engine 函式
                     含 test_sort_order.py（分類排序單元測試）
  api/            ← 透過 TestClient 測試 HTTP 端點
                     含 test_reorder_api.py / test_list_filtering.py 等
  integration/    ← test_import_to_report_flow.py, test_merge_consistency.py, test_step8_level2.py
```

## API 端點總覽

### 分類 API

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/categories` | 列出分類；`?type=E\|I` 篩選；`?include_count=1` 附交易數 |
| POST | `/api/categories` | 新增分類（`{類型, 主類, 次類}`） |
| DELETE | `/api/categories` | 刪除分類（body 帶 `{類型, 主類, 次類}`） |
| POST | `/api/categories/merge` | 合併分類（改名實作方式，自動刪除來源） |
| POST | `/api/categories/reorder` | 調整排序（`{類型, 主類, 次類, direction: "up"\|"down"}`） |

### 交易 API

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/transactions` | 查詢交易（見下方篩選參數） |
| GET | `/api/transactions/date_range` | 回傳 `{min, max, count}` 最早/最晚日期與總筆數 |
| GET | `/api/transactions/{id}` | 取得單筆交易 |
| POST | `/api/transactions` | 新增交易 |
| PUT | `/api/transactions/{id}` | 更新交易 |
| DELETE | `/api/transactions/{id}` | 刪除交易（HTTP 204） |

`GET /api/transactions` 篩選參數：

| 參數 | 說明 |
|------|------|
| `from` / `to` | 日期範圍（YYYY-MM-DD） |
| `type` | `E` 或 `I` |
| `category_main` / `category_sub` | 主類/次類篩選（指定次類時必須同時指定主類） |
| `keyword` | 明細或備註關鍵字（大小寫不敏感） |
| `amount_min` / `amount_max` | 金額範圍 |
| `page` / `size` | 分頁（size 上限 500，預設 100） |

回傳結構：`{items, total, page, size, pages, summary: {total_count, total_income, total_expense, net}}`

排序：日期 DESC + 建立時間 DESC。

### 報表 API

報表日期未指定時預設近 12 個月（當月第一日往前推 11 個月 ~ 今日）。

| 方法 | 路徑 | 參數 | 說明 |
|------|------|------|------|
| GET | `/api/report/monthly` | `from`, `to`, `type=E\|I\|all` | 月度收支摘要（含空月補 0） |
| GET | `/api/report/category` | `from`, `to`, `type=E\|I`, `level=main\|sub` | 分類佔比（按金額 DESC） |
| GET | `/api/report/trend` | `from`, `to`, `type=E\|I\|all`, `category_main` | 月度趨勢（可選主類篩選） |

### 匯入/匯出 API

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/api/import/preview` | 上傳 MyAB CSV（上限 10 MB）；回傳 token + 摘要 + 新分類 + 前 5 筆預覽 |
| POST | `/api/import/confirm` | 帶 `{preview_token}` 確認匯入；自動建立新分類並寫入交易 |
| GET | `/api/export` | 帶 `from` / `to` 下載 CSV（UTF-8 BOM，Excel 友善） |

## 非顯而易見的設計決策

### app.py 路由順序

兩個順序必須固定，否則 FastAPI 匹配錯誤：
1. `/api/transactions/date_range` 必須在 `/api/transactions/{id}` **之前**，否則 `date_range` 會被當作 `{id}`
2. `app.mount("/", StaticFiles(...))` 必須在所有 API 路由**最後**，否則吞掉 API 請求

### CSV 寫入原子性

`data_manager._write_csv()` 先寫 `.tmp` 再 `os.replace()` 達成原子性，`init_data_files()` 啟動時會清理殘留的 `.tmp`。

### 分類排序（sort_order）

`categories.csv` 含隱性欄位 `sort_order`（整數字串），用於維護使用者自訂的分類排列順序：
- 主類在同類型（E/I）內排序；次類在同主類內排序
- `POST /api/categories/reorder` 透過交換相鄰項目的 sort_order 實作上移/下移
- 舊版 `categories.csv` 缺少此欄時，`init_data_files()` 啟動時自動呼叫 `_migrate_sort_order()` 補齊

### 測試 fixture 標準模式

每個測試檔頂層必須 `sys.path.insert` 並用 `monkeypatch` 將 `dm.DATA_DIR / MAIN_DB / CATEGORIES_CSV` 重導到 `tmp_path`，再呼叫 `dm.init_data_files()`。TestClient 在 `patch_data` fixture 之後建立，確保 `app` 讀到的 `dm` 已被 monkeypatch：

```python
@pytest.fixture(autouse=True)
def patch_data(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DATA_DIR",       tmp_path)
    monkeypatch.setattr(dm, "MAIN_DB",        tmp_path / "main_db.csv")
    monkeypatch.setattr(dm, "CATEGORIES_CSV", tmp_path / "categories.csv")
    dm.init_data_files()

@pytest.fixture
def client():
    from app import app  # 延遲 import，確保在 monkeypatch 後
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
```

### 分類驗證

`POST /api/transactions` 與 `PUT /api/transactions/{id}` 都會先呼叫 `dm.category_exists()` 確認分類存在才寫入，所以測試前必須先建立所需分類。

### 分類 DELETE 用 request body

`DELETE /api/categories` 帶 body（類型/主類/次類），TestClient 呼叫方式：
```python
client.request("DELETE", "/api/categories", json={...})
```

### 合併（merge）= 改名實作方式

前端改名流程：若目標分類不存在先 `POST /api/categories` 建立，再呼叫 `POST /api/categories/merge`（merge 會自動刪除來源分類並更新所有相關交易）。後端 merge API 要求目標分類必須已存在。

### 匯入暫存機制

Preview token 存於記憶體 dict，TTL 10 分鐘。每次 `POST /api/import/preview` 時順帶清理過期 token 防止記憶體洩漏。確認匯入時自動呼叫 `dm.ensure_categories()` 建立新分類後再批次寫入交易。

## 資料欄位

`main_db.csv`：`id, 日期, 類型, 類別主類, 類別次類, 金額, 明細, 備註, 建立時間`
- 類型：`E`（支出）/ `I`（收入）
- 金額：正整數（正負號由類型決定）

`categories.csv`：`類型, 主類, 次類, sort_order`（平鋪格式，次類可為空字串，sort_order 為整數字串）

去重鍵（匯入用）：`日期 + 類型 + 類別主類 + 類別次類 + 金額 + 明細`
