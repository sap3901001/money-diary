# MyAB CSV 匯出腳本實作計畫

**狀態：已完成** ✅（2026-04-02）

## Context

MyAB 記帳軟體的逆向分析已全部完成（金額公式定版、所有欄位偏移已驗證）。
匯出腳本 `myab_export.py` 已實作並驗證通過。

## 專案目錄結構

```
/mnt/c/test_soft/MyAB/note/myab_export/
├── myab_export.py       ← 主程式（零參數執行）
├── source/              ← 輸入檔案（使用者手動放入）
│   ├── （db 模式）Main.abd + Main1.abd（可選）+ Accounts.abd（可選）
│   └── （mbu 模式）*.mbu（可多個）
└── target/              ← 輸出 CSV
    ├── （db 模式）transactions.csv + accounts.csv
    └── （mbu 模式）backup_原檔名.csv + backup_原檔名_accounts.csv
```

## 執行方式

```bash
cd /mnt/c/test_soft/MyAB/note/myab_export
python3 myab_export.py
```

零參數，程式自動偵測 `source/` 目錄內容決定模式。

## 模式偵測邏輯

1. 掃描 `source/` 目錄，依讀取到的**第一個檔案副檔名**決定模式：
   - 發現 `.mbu` 檔 → mbu 模式
   - 發現 `.abd` 檔 → db 模式
   - 兩者皆無 → 顯示錯誤訊息並結束

### db 模式

- 讀取 `source/Main.abd`（必要）
- 尋找 `source/Main1.abd`（可選，無則備註欄留空）
- 尋找 `source/Accounts.abd`（可選，有則匯出科目設定）
- 輸出：`target/transactions.csv` + `target/accounts.csv`

### mbu 模式

- 讀取 `source/` 下**所有** `.mbu` 檔案
- 每個 `.mbu` 各產生交易 CSV 和科目 CSV
- 輸出命名：`target/backup_原檔名.csv` + `target/backup_原檔名_accounts.csv`
- 例：`20260401.mbu` → `backup_20260401.csv` + `backup_20260401_accounts.csv`

## 核心模組

1. **`decode_amount(b4)`** — 金額解碼：LE 4 bytes → BE top4 + 0x00×4 → double / 100 → round
2. **`parse_mbu_index(data)`** — 解析 .mbu 索引，回傳 `{filename: (offset, size)}` dict
3. **`parse_main_db(data)`** — Main.abd 解析（284 bytes/筆，DataBase 與 .mbu 共用同一函式）
4. **`parse_main1_notes(data)`** — Main1.abd 備註解析（104 bytes header + 204 bytes/筆，偏移 104）
5. **`parse_accounts(data)`** — Accounts.abd 科目解析（276 bytes/筆，含截斷記錄處理）
6. **`write_csv(records, indices, notes, output_path)`** — 交易記錄 UTF-8-BOM 輸出
7. **`write_accounts_csv(accounts, output_path)`** — 科目設定 UTF-8-BOM 輸出

## CSV 輸出欄位

### 交易記錄（transactions.csv / backup_*.csv）

```
日期, 類型, 類別主類, 類別次類, 帳戶, 金額, 明細, 備註
```

- 金額帶符號：I=正值，E=負值，A/L=正值
- 類別碼以 `.` 分割為主類/次類
- 帳戶去除前置空格
- 備註欄：有 Main1.abd 時填入，否則留空
- 備註對齊：note[n] → rec[n+1]（rec[0] 無備註）

### 科目設定（accounts.csv / backup_*_accounts.csv）

```
類型, 類型名稱, 階層, 主類, 次類
```

- 類型：A / L / I / E / Equity（原始代碼）
- 類型名稱：資產 / 負債 / 收入 / 支出 / 權益
- 階層：主類 / 次類（由名稱中是否含 `.` 判斷）
- 次類欄：主類項目留空

## 關鍵偏移

**Main.abd**（DataBase 與 .mbu 使用相同偏移，經驗證 100% 逐位元組一致）：

日期 0x00, 類型 0x0A, 類別 0x0C, 帳戶 0x28, 金額 0x50, 明細 0x54

**Accounts.abd**（276 bytes/筆，43 完整 + 1 截斷 = 44 筆）：

科目名稱 0x00（32 bytes, Big5, 格式 `TYPE-主類.次類`）, 類型旗標 0x20（01=A, 02=L, 03=I, 04=E, 00=Equity）

## 實作中發現的修正

| 項目 | 原文記載 | 實際驗證結果 |
|------|---------|-------------|
| .mbu 記錄格式 | 6 bytes 左旋轉 | ❌ 與 DataBase 格式完全一致，無需轉換 |
| Main1.abd header | 98 bytes | ❌ 104 bytes（整除驗證）|
| 備註對齊 | note[n] → rec[n] | ❌ note[n] → rec[n+1]（VER2 驗證 30/30 筆匹配）|

## 驗證結果

| 測試 | 結果 |
|------|------|
| db 模式（Main.abd + Main1.abd）| ✅ 975 筆交易匯出 |
| mbu 模式（20260402.mbu）| ✅ 975 筆交易匯出 |
| mbu 模式（20260401.mbu + 20260331.mbu）| ✅ 942 + 864 筆匯出 |
| VER2 備註對齊驗證 | ✅ 30/30 筆匹配 |
| TST 備註對齊驗證 | ✅ 匹配 |
| db 模式科目匯出（Accounts.abd）| ✅ 44 筆科目匯出 |
| mbu 模式科目匯出（20260402.mbu）| ✅ 44 筆科目匯出 |
