# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 工具概覽

單一腳本工具，將 MyAB 我的記帳簿的專有二進位格式（`.abd` / `.mbu`）逆向匯出為 UTF-8-BOM CSV。

- 輸入：`source/`；輸出：`target/`
- 無需安裝第三方套件（只用標準函式庫 `csv`、`os`、`struct`、`sys`）

## 執行方式

```bash
cd /mnt/c/test_soft/MyAB/note/myab_export

# db 模式：將 Main.abd（+ 可選 Main1.abd / Accounts.abd）放入 source/
# mbu 模式：將 *.mbu 放入 source/（可多個）
python3 myab_export.py
```

**模式自動偵測**：`detect_mode()` 對 `source/` 的檔名 `sorted()` 後逐一檢查副檔名，第一個遇到 `.mbu` 則進入 mbu 模式，第一個遇到 `.abd` 則進入 db 模式。因此兩種副檔名混放時結果取決於排序後的第一個符合項。

## 輸出檔案命名規則

| 模式 | 輸出檔案 | 說明 |
|------|----------|------|
| db | `target/transactions.csv` | 交易記錄 |
| db（選用） | `target/accounts.csv` | 科目設定（需有 Accounts.abd） |
| mbu | `target/backup_{stem}.csv` | 每個 .mbu 各一份交易記錄 |
| mbu（選用） | `target/backup_{stem}_accounts.csv` | 每個 .mbu 各一份科目設定 |

`{stem}` 為 `.mbu` 的主檔名（例如 `20260402.mbu` → `stem = 20260402`）。

## 程式架構

`myab_export.py` 為單一檔案，資料流：

```
source/ 二進位
  → detect_mode()              偵測輸入模式
  → parse_mbu_index()          （mbu 模式）解包索引
  → parse_main_db()            解析交易記錄（含 decode_amount / decode_big5 / split_category）
  → parse_main1_notes()        解析備註
  → parse_accounts()           解析科目設定
  → write_csv()                輸出交易 CSV（合併備註）
  → write_accounts_csv()       輸出科目 CSV
→ target/ CSV
```

### 常數

| 常數 | 值 | 說明 |
|------|----|------|
| `REC_SIZE` | 284 | Main.abd 每筆記錄大小（bytes） |
| `MAIN1_HEADER` | 104 | Main1.abd 標頭大小 |
| `MAIN1_REC` | 204 | Main1.abd 每筆記錄大小 |
| `MAIN1_NOTE_OFFSET` | 104 | Main1.abd 記錄內備註起始位置 |
| `ACCT_REC_SIZE` | 276 | Accounts.abd 每筆記錄大小 |
| `ACCT_NAME_LEN` | 32 | Accounts.abd 名稱欄位長度 |

### 函式說明

| 函式 | 輸入 | 回傳 | 說明 |
|------|------|------|------|
| `decode_amount(b4)` | 4 bytes LE | `int` TWD | LE top4 of double → TWD 整數（見下方） |
| `decode_big5(data)` | bytes | `str` | rstrip `\x00\x20` 後 Big5 解碼 |
| `split_category(cat_str)` | `str` | `(主類, 次類)` | 以 `.` 分割，無 `.` 時次類為空字串 |
| `parse_main_db(data)` | Main.abd bytes | `(records, indices)` | records 每筆 7 欄（不含備註），indices 為對應原始 0-based 位置 |
| `parse_main1_notes(data)` | Main1.abd bytes | `list[str]` | `notes[n]` 對應 Main.abd 第 `n+1` 筆（0-based） |
| `parse_accounts(data)` | Accounts.abd bytes | `list[list]` | 科目設定列表，每筆 5 欄 |
| `parse_mbu_index(data)` | .mbu bytes | `dict[str, (int,int)]` | `{basename: (offset, size)}`，去除路徑只保留檔名 |
| `write_csv(records, indices, notes, path)` | — | — | 合併備註後寫出交易 CSV（UTF-8-BOM） |
| `write_accounts_csv(accounts, path)` | — | — | 寫出科目 CSV（UTF-8-BOM） |
| `detect_mode()` | — | `(mode, mbu_files)` | 掃描 source/，回傳 `('db', None)` 或 `('mbu', [...])`|

## 關鍵二進位格式細節

### Main.abd（284 bytes/筆）

交易記錄含 E/I/A/L 四種類型（全部保留輸出，不過濾 A/L）。

| Offset | 長度 | 欄位 | 說明 |
|--------|------|------|------|
| 0x00 | 10B | 日期 | ASCII `YYYY/MM/DD` |
| 0x0A | 1B | 類型 | `E`=支出 / `I`=收入 / `A`=資產 / `L`=負債 |
| 0x0C | 28B | 類別碼 | Big5，格式 `主類.次類`，由 `split_category` 分割為兩欄 |
| 0x28 | 8B | 帳戶 | Big5 |
| 0x50 | 4B | 金額 | 自訂編碼（見 `decode_amount`）；E 類型轉負值 |
| 0x54 | 190B | 明細 | Big5（`0x54:0x112`） |

0x30–0x4F 共 32 bytes 為未使用欄位，程式跳過不讀。

空白記錄（全 `\x00` 或全 `\x20`）及類型不在 E/I/A/L 的記錄會跳過。

### 金額解碼（`decode_amount`）

MyAB 將 `TWD × 100` 以 IEEE 754 double 表示，只保留高 4 bytes，以 LE 寫入：

```python
be_top4 = bytes([b4[3], b4[2], b4[1], b4[0]])
value = struct.unpack('>d', be_top4 + b'\x00\x00\x00\x00')[0] / 100
return round(value)
```

E 類型在 `parse_main_db` 中轉為負值後寫入 CSV；I/A/L 維持正值。

### Main1.abd 備註對齊

`notes[n]` 對應 Main.abd **原始索引** `n+1` 的記錄（0-based）。`write_csv` 中透過 `indices`（各記錄在 Main.abd 的原始位置）計算：

```python
note_idx = orig_idx - 1   # orig_idx 為 parse_main_db 回傳的原始 0-based 索引
note = notes[note_idx] if 0 <= note_idx < len(notes) else ''
```

索引 0 的記錄（`orig_idx == 0`）`note_idx` 為 -1，備註欄為空。

### Accounts.abd 名稱解析規則

名稱欄位 Big5，格式有兩種：
- 含 `-`：`TYPE-主類.次類`，`-` 前為類型，後以 `.` 分割主次類
- 無 `-`：整串視為類型（如 `Equity`），主類同類型，次類空

TYPE_MAP：`A`→資產、`L`→負債、`I`→收入、`E`→支出、`Equity`→權益。

### .mbu 封包索引

索引格式（全在檔頭的同一個文字區塊）：
```
username[spaces][version]filepath\x01size\r\n
filepath\x01size\r\n
...（索引結束後緊接二進位資料）
```

第一個檔案條目緊接在 header 行末尾（同一行），`parse_mbu_index` 從第一個 `\x01` 向前反向搜尋路徑起始，再從該位置逐行解析。路徑合理性驗證：必須含 `.abd`、`.lst`、`.pwd` 或 `\`，否則停止解析（判斷索引區結束）。

## 已知限制與注意事項

- `source/` 中的 `Accounts2.abd` 為未使用的額外科目檔，程式不處理（db 模式只讀 `Accounts.abd`，mbu 模式從封包內提取）
- Accounts.abd 最後一筆可能不足 276 bytes，`parse_accounts` 以 `min(i + ACCT_REC_SIZE, total)` 容錯
- .mbu 模式下若封包索引中無 `Main.abd`，該 .mbu 檔案會跳過並印出警告
- 輸出編碼統一為 UTF-8-BOM（`utf-8-sig`），可直接在 Excel 開啟中文不亂碼
