# Daily Ledger — Step 3 自動測試計畫

> 獨立於現有 `test_list_filtering.py`（24 tests），針對交易列表頁（list.html）與相關 API 的補充測試。

## Step 3 作業目標

**交付物：**
- `frontend/list.html` — 交易列表頁
- API 端點：`GET /api/transactions`（含 summary）、`GET /api/transactions/{id}`、`PUT /api/transactions/{id}`、`DELETE /api/transactions/{id}`、`GET /api/transactions/date_range`

**功能要求：**
- 可收合篩選區（日期區間預設本月、類型、主類/次類連動、金額區間、關鍵字）
- 摘要列（總筆數 / 總收入 / 總支出 / 淨額，為篩選範圍全部統計，非僅當頁）
- 表格金額紅/綠色區分
- 編輯採 Modal（不離開列表，PUT 全欄位覆蓋）
- 刪除二次確認（硬刪除）
- 固定排序（日期 DESC + 建立時間 DESC，不開放自訂）
- 分頁 100 筆，底部上一頁/下一頁

---

## 測試案例

### 一、Response Shape 與資料合約（6 tests）

驗證 API 回傳結構完整性，確保前端可安全取用所有欄位。

| # | 案例 | 驗證重點 |
|---|------|----------|
| S-01 | `GET /api/transactions` response 頂層欄位完整 | 必含 `items`, `total`, `page`, `size`, `pages`, `summary` 六個 key |
| S-02 | `items[]` 每筆交易欄位完整 | 每筆含 `id`, `日期`, `類型`, `類別主類`, `類別次類`, `金額`, `明細`, `備註`, `建立時間` 共 9 欄 |
| S-03 | `金額` 欄位型別為字串 | CSV 讀出為字串，驗證 API 回傳 `type(金額) == str` |
| S-04 | `GET /api/transactions/{id}` 回傳完整單筆 | 9 欄皆存在，值與建立時一致 |
| S-05 | `GET /api/transactions/{id}` 不存在回 404 | status 404 + detail 訊息 |
| S-06 | `DELETE` 回 204 且無 body | `response.content == b""` 或長度 0 |

### 二、篩選缺口（8 tests）

補充現有測試未涵蓋的篩選邊界情境。

| # | 案例 | 驗證重點 |
|---|------|----------|
| F-01 | `keyword` 搜尋「備註」欄位 | 明細無匹配但備註有匹配 → 應找到 |
| F-02 | `keyword` 大小寫不敏感（中英混合） | keyword=`abc` 能匹配明細 `XYZ ABC` |
| F-03 | `from` = `to`（同一天） | 僅回傳該日交易 |
| F-04 | `from` > `to`（反向區間） | 預期回 0 筆（非報錯） |
| F-05 | `amount_min` = `amount_max`（精確金額） | 僅回傳金額剛好等於該值的交易 |
| F-06 | 僅指定 `category_sub` 不指定 `category_main` | 有 `category_sub` 但無 `category_main` 時回 **422** |
| F-07 | `type` 傳無效值（如 `X`） | 回 **422**，與分類 API 一致 |
| F-08 | 無篩選條件（僅預設值） | 回傳全部資料，摘要涵蓋所有交易 |

### 三、排序深度驗證（3 tests）

現有測試只驗日期 DESC，未驗同日排序與建立時間。

| # | 案例 | 驗證重點 |
|---|------|----------|
| O-01 | 同日期多筆全部回傳 | 插入 3 筆同日交易，驗證全部回傳且日期正確（不強制建立時間排序，因 `_now_iso()` 精度為秒，同秒排序不確定） |
| O-02 | 跨月、跨年排序正確 | 2025-12-31 排在 2026-01-01 之後 |
| O-03 | 排序不受篩選影響 | 加篩選條件後結果仍維持 DESC |

### 四、摘要 summary 跨頁一致性（3 tests）

現有測試只驗單頁場景，未驗跨頁摘要行為。

| # | 案例 | 驗證重點 |
|---|------|----------|
| M-01 | summary 統計涵蓋**全部篩選結果**而非僅當頁 | 10 筆資料 size=3 page=1，summary.total_count 應為 10 |
| M-02 | summary 在不同 page 間數值一致 | page=1 與 page=2 的 summary 完全相同 |
| M-03 | 純支出場景 net 為負 | 全部 E 類型，net = -total_expense（確認為預期行為，前端已正確處理正負顯示） |

### 五、PUT 驗證邊界（6 tests）

補充 Pydantic 驗證拒絕情況的測試。

| # | 案例 | 驗證重點 |
|---|------|----------|
| P-01 | 日期格式錯誤（`2026/01/01`） | 422 + 錯誤訊息 |
| P-02 | 類型非 E/I（如 `A`） | 422 |
| P-03 | 金額 = 0 | 422（正整數驗證） |
| P-04 | 金額 = -100 | 422 |
| P-05 | 缺少必填欄位（無 `日期`） | 422 |
| P-06 | PUT 將類型從 E 改為 I，分類需匹配 | 若 I 類無該分類 → 422；有 → 200 且類型更新 |

### 六、特殊字元與 CSV 安全（4 tests）

驗證 CSV 儲存邊界，確保特殊字元不會導致資料損壞。

| # | 案例 | 驗證重點 |
|---|------|----------|
| C-01 | 明細含逗號 `"早餐,午餐"` | POST → GET 來回不丟失 |
| C-02 | 明細含雙引號 `"他說""你好"""` | 正確 CSV escape 與還原 |
| C-03 | 備註含換行符 `"line1\nline2"` | POST → GET round-trip 正確，不 strip（Power BI 可正確處理 RFC 4180 CSV） |
| C-04 | 空字串 vs 空白字串 | `明細=""` 和 `備註=""` 存取一致 |

### 七、GET /api/transactions/date_range（3 tests）

此端點在 Step 3 實作但現有測試完全未覆蓋。

| # | 案例 | 驗證重點 |
|---|------|----------|
| D-01 | 空資料庫 | `{min: null, max: null, count: 0}` |
| D-02 | 單筆資料 | `min == max == 該筆日期`，`count == 1` |
| D-03 | 多筆跨月資料 | `min`/`max` 正確，`count` = 總筆數 |

### 八、資料完整性（3 tests）

驗證操作順序與資料一致性。

| # | 案例 | 驗證重點 |
|---|------|----------|
| I-01 | POST → PUT → GET 資料一致 | 最終 GET 拿到的是 PUT 後的值 |
| I-02 | POST → DELETE → list 確認消失 | 刪除後 list 不含該筆，total 減 1 |
| I-03 | 批次 POST 5 筆 → list 順序與 summary 正確 | 一次驗證多筆寫入的完整性 |

---

## 統計

| 分類 | 數量 |
|------|------|
| Response Shape 與資料合約 | 6 |
| 篩選缺口 | 8 |
| 排序深度驗證 | 3 |
| 摘要跨頁一致性 | 3 |
| PUT 驗證邊界 | 6 |
| 特殊字元與 CSV 安全 | 4 |
| date_range 端點 | 3 |
| 資料完整性 | 3 |
| **合計** | **36 tests** |

---

## 測試執行結果（2026-04-09）

**環境：** Python 3.13.2 / pytest 9.0.3 / Windows  
**結果：** 36 passed（耗時 2.10s）
**本次更新時間戳：** 2026-04-09 15:45:53 +08:00  
**測試命令：** `c:\test_soft\MyAB\.venv\Scripts\python.exe -m pytest tests/api/test_step3_extra.py -v`

### 逐案結果

| # | 案例 | 結果 | 備註 |
|---|------|------|------|
| S-01 | response 頂層欄位完整 | ✅ PASS | |
| S-02 | items[] 欄位完整 | ✅ PASS | |
| S-03 | 金額型別為字串 | ✅ PASS | |
| S-04 | GET 單筆完整回傳 | ✅ PASS | |
| S-05 | GET 不存在 404 | ✅ PASS | |
| S-06 | DELETE 204 無 body | ✅ PASS | |
| F-01 | keyword 搜尋備註 | ✅ PASS | |
| F-02 | keyword 大小寫不敏感 | ✅ PASS | |
| F-03 | from = to 同一天 | ✅ PASS | |
| F-04 | from > to 反向區間 | ✅ PASS | |
| F-05 | 精確金額 | ✅ PASS | |
| F-06 | sub 無 main → 422 | ✅ PASS | 已加入參數驗證 |
| F-07 | type 無效值 → 422 | ✅ PASS | 已加入參數驗證 |
| F-08 | 無篩選回全部 | ✅ PASS | |
| O-01 | 同日期多筆全部回傳 | ✅ PASS（調整後） | 決議 D：不強制同秒排序 |
| O-02 | 跨年排序 | ✅ PASS | |
| O-03 | 篩選後排序不變 | ✅ PASS | |
| M-01 | summary 涵蓋全部篩選結果 | ✅ PASS | |
| M-02 | summary 跨頁一致 | ✅ PASS | |
| M-03 | net 為負 | ✅ PASS | |
| P-01 | 日期格式錯誤 | ✅ PASS | |
| P-02 | 類型非 E/I | ✅ PASS | |
| P-03 | 金額 = 0 | ✅ PASS | |
| P-04 | 金額 = -100 | ✅ PASS | |
| P-05 | 缺必填欄位 | ✅ PASS | |
| P-06 | 類型切換分類驗證 | ✅ PASS | |
| C-01 | 明細含逗號 | ✅ PASS | |
| C-02 | 明細含雙引號 | ✅ PASS | |
| C-03 | 備註含換行符 | ✅ PASS | |
| C-04 | 空字串保留 | ✅ PASS | |
| D-01 | 空資料庫 date_range | ✅ PASS | |
| D-02 | 單筆 date_range | ✅ PASS | |
| D-03 | 多筆跨月 date_range | ✅ PASS | |
| I-01 | POST→PUT→GET 一致 | ✅ PASS | |
| I-02 | POST→DELETE 消失 | ✅ PASS | |
| I-03 | 批次 POST 順序與摘要 | ✅ PASS | |

### 補充說明

#### ✅ O-01：同日期多筆全部回傳（已調整測試預期）

- **原問題：** `_now_iso()` 精度為秒，同秒交易建立時間相同，排序退化為不確定順序
- **決議：** 選項 D — 手動記帳不可能同秒建立兩筆，接受同秒排序不確定，測試改為只驗證「3 筆全部回傳、日期正確、明細集合正確」
- **測試已修改：** 移除 `time.sleep` 與順序斷言

---

## 討論決議紀錄

| # | 議題 | 決議 | 實作影響 |
|---|------|------|----------|
| F-06 | 僅指定 `category_sub` 不指定 `category_main` | **C. 回 422**，要求 `category_sub` 必須搭配 `category_main` | 已完成：`list_transactions` 已加入驗證 |
| F-07 | `type` 傳無效值 | **A. 回 422**，與分類 API（BUG-5 修正）一致 | 已完成：`list_transactions` 已加入 `type` 驗證 |
| M-03 | `net` 為負數 | **A. 維持現狀**，`net = income - expense` 可為負 | 無需修改，前端 `list.html` 已正確處理正負顯示（≥0 藍色帶 `+`、<0 紅色帶 `-`） |
| C-03 | 換行符處理 | **A. 納入測試**，驗證 CSV round-trip 正確，不 strip | 無需修改程式碼，Power BI 可正確處理 RFC 4180 CSV |
| O-01 | 同秒建立時間排序問題 | **D. 接受現狀**，同秒排序不確定，調整測試只驗全部回傳 | 修改測試程式碼，不改產品程式碼 |
