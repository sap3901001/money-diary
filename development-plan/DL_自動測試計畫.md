# Daily Ledger 自動測試計畫書

## 1. 文件目的

本文件定義 Daily Ledger 專案的自動測試範圍、執行方式、案例矩陣與品質門檻，目標為：

1. 在每次修改後快速發現功能回歸。
2. 優先保障核心資料流程：交易、分類、匯入、匯出、報表。
3. 確保 CSV 架構下的資料一致性與可追蹤性。
4. 降低手動測試負擔，將重複驗證機械化。

## 2. 測試範圍

### 2.1 納入自動化範圍（必要）

1. API 契約與資料驗證。
2. 資料層邏輯（CSV 讀寫、去重、分類合併）。
3. 匯入 preview/confirm 流程。
4. 匯出檔內容、編碼、排序、檔名規則。
5. 報表聚合正確性（monthly/category/trend）。

### 2.2 暫不納入自動化範圍（手動）

1. UI 視覺排版細節。
2. 圖表外觀與互動體感。
3. 跨瀏覽器 UX 細節（保留手動驗證）。

## 3. 測試分層策略

### 3.1 單元測試（Unit）

對象：純函式與資料轉換邏輯。

1. 日期格式轉換（MyAB 日期到 ISO 日期）。
2. 去重鍵生成與比對。
3. 分類平鋪資料的 group/sort 邏輯。
4. 報表聚合函式。

### 3.2 API 測試（Service/API）

對象：FastAPI 路由與驗證流程。

1. 交易 CRUD。
2. 分類管理與 merge。
3. 匯入 preview/confirm。
4. 匯出與 date_range。
5. 報表三支 API。

### 3.3 整合測試（Integration）

對象：跨模組資料流，特別是寫入一致性。

1. 匯入後列表/報表/匯出數據一致。
2. 分類合併後交易引用與分類檔同步。
3. 匯出再匯入的 round-trip 一致性。

## 4. 工具與目錄規劃

### 4.1 建議工具

1. pytest。
2. pytest-cov。
3. FastAPI TestClient（或 httpx）。
4. tempfile / tmp_path（隔離測試資料目錄）。

### 4.2 建議測試目錄

```text
note/daily_ledger/
├─ tests/
│  ├─ conftest.py
│  ├─ unit/
│  │  ├─ test_dedup.py
│  │  ├─ test_date_parse.py
│  │  └─ test_report_engine.py
│  ├─ api/
│  │  ├─ test_transactions_api.py
│  │  ├─ test_categories_api.py
│  │  ├─ test_import_api.py
│  │  ├─ test_export_api.py
│  │  └─ test_report_api.py
│  └─ integration/
│     ├─ test_import_to_report_flow.py
│     └─ test_merge_consistency.py
└─ pytest.ini
```

## 5. 測試資料策略

1. 測試資料與正式資料完全分離，使用暫存目錄。
2. 每個測試案例獨立建立初始 CSV，避免案例互相污染。
3. 建立三組標準測試資料：
   - minimal：空資料與單筆資料。
   - normal：一般月度交易資料。
   - edge：逗號、引號、空次類、重複交易、跨月資料。

## 6. 必要自動測試案例矩陣

| 編號 | 類別 | 案例 | 預期結果 |
|---|---|---|---|
| AT-001 | API | POST /api/transactions 合法新增 | 回傳 200/201，含 id 與建立時間 |
| AT-002 | API | POST /api/transactions 非法金額 | 回傳 4xx，資料不寫入 |
| AT-003 | API | GET /api/transactions 篩選+分頁 | items/total/pages/summary 正確 |
| AT-004 | API | PUT /api/transactions/{id} 全覆蓋 | 欄位更新正確且保留資料完整性 |
| AT-005 | API | DELETE /api/transactions/{id} | 刪除後不可再查到 |
| AT-006 | API | POST /api/categories 重複新增 | 回傳 409 |
| AT-007 | API | DELETE /api/categories 有引用 | 回傳 409 |
| AT-008 | API | POST /api/categories/merge | 交易引用搬移、來源分類移除 |
| AT-009 | API | POST /api/import/preview 合法檔 | 回傳摘要與 preview_token |
| AT-010 | API | POST /api/import/confirm token 過期 | 回傳 404 或定義中的錯誤碼 |
| AT-011 | API | GET /api/export 範圍匯出 | 內容排序為日期 ASC + 建立時間 ASC |
| AT-012 | API | GET /api/export 空範圍 | 仍輸出 header，筆數為 0 |
| AT-013 | Unit | 去重鍵判定 | 完全重複被辨識，非重複保留 |
| AT-014 | Unit | 報表 monthly 補空月份 | 缺月份補 0，不斷線 |
| AT-015 | Integration | 匯入後報表一致性 | 交易總額與報表總額一致 |
| AT-016 | Integration | merge 後一致性 | main_db 與 categories 引用一致 |
| AT-017 | Integration | round-trip | 匯出再匯入不發生資料毀損 |
| AT-018 | Encoding | 匯出 UTF-8 BOM | Excel 開啟中文無亂碼 |

## 7. 通過門檻（Quality Gate）

1. 所有必要案例（AT-001 至 AT-018）必須通過。
2. 新增功能需同時新增或更新對應測試案例。
3. 回歸測試失敗不得合併到主分支。
4. 單元與 API 測試總覆蓋率建議至少 80%。

## 8. 執行時機與流程

### 8.1 本機開發流程

1. 開發前先跑一次全測試確認基線。
2. 每完成一個功能點，至少跑相關測試檔。
3. 提交前必跑完整測試套件。

### 8.2 每日或里程碑流程

1. 每日收工前跑完整測試並留存結果。
2. Step 完成時執行對應回歸測試。
3. 發布前執行全量自動測試 + 手動驗收清單。

## 9. 風險與注意事項

1. CSV 寫入風險最高，任何寫入流程都要驗證原子性與一致性。
2. 匯入 token 有 TTL，測試需覆蓋過期、重送、重複確認情境。
3. 去重鍵可能誤判相似交易，需保留測試案例避免規格漂移。
4. 報表 API 的口徑必須與交易 summary 一致，避免數字不一致。
5. 匯出用途為分析時，可不含分類檔；若包含移機需求，需另定完整備份測試。

## 10. 後續擴充建議

1. 加入簡易 CI（例如 GitHub Actions）自動跑 pytest。
2. 在測試輸出中自動生成 coverage 與失敗摘要。
3. 若未來加入完整前端自動化，可再導入 Playwright 做關鍵旅程測試。
