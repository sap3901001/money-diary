# myab-export：.mbu 索引偏移錯誤修復記錄

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**建立日期：** 2026-05-29  
**影響檔案：** `myab-export/myab_export.py`  
**狀態：** 已修復並驗證

---

## 問題描述

執行 `python3 myab_export.py` 處理 `source/peter-20250925.mbu`（31,571 KB）後，
`target/backup_peter-20250925.csv` 只有 **72 bytes**（僅含 CSV 標頭列，0 筆交易記錄）。

```
處理：peter-20250925.mbu
  Main.abd：66884 bytes，解析 0 筆交易    ← 錯誤
  已匯出 0 筆記錄 → target/backup_peter-20250925.csv
```

---

## .mbu 檔案結構回顧

MyAB .mbu 備份封包的格式如下：

```
[文字索引區]                          ← 純 ASCII 文字
  peter              2658      Peter-2006\Accounts.abd\x019444\r\n
  Peter-2006\Accounts2.abd\x01888\r\n
  ...
  Paynum.dat\x010\r\n                 ← 最後一個條目（size=0）
[二進位資料區]                        ← 各 .abd 的原始 bytes
  [Peter-2006\Accounts.abd 9444 bytes]
  [Peter-2006\Main.abd ...]
  ...
```

索引區的第一行格式為：`帳號名[空格]索引長度[空格]第一條目路徑\x01size\r\n`，
後續每行為 `相對路徑\x01size\r\n`。索引區與二進位資料區之間無額外分隔符。

本次 .mbu（`peter-20250925.mbu`，32,272,703 bytes）共有 **81 個條目**，
橫跨 Peter-2006 到 Peter-2020 十個年度的多份資料庫。

---

## 根本原因分析

### `parse_mbu_index()` 的邏輯錯誤

`myab_export.py` 中，`parse_mbu_index()` 解析索引條目的迴圈含以下驗證：

```python
# myab_export.py（修復前）第 169-170 行
if not any(ext in fname.lower() for ext in ('.abd', '.lst', '.pwd', '\\')):
    break   # ← 問題所在
```

**副檔名白名單**刻意排除了 `.dat`，目的是偵測到「非正規條目」時停止解析。
但邏輯的問題在於：`break` 執行時，`pos` 變數**尚未前進**——它還指向
`Paynum.dat` 那一行的開頭，而非結尾。

### 偏移量推算過程

| 變數 | 期望值 | 實際值（修復前） | 差距 |
|------|--------|----------------|------|
| `index_end` | 2,688 | 2,674 | **-14 bytes** |

偏差值正好等於 `Paynum.dat\x010\r\n` 這一行的長度：

```
P  a  y  n  u  m  .  d  a  t  \x01  0  \r  \n
10 個字元 + 1 + 1 + 2 = 14 bytes
```

### 連鎖效應

`index_end` 決定了所有後續提取的起始偏移：

```python
offset = index_end      # 整個 offset 系統都從這裡開始累加
for fname, size in entries:
    files[basename] = (offset, size)   # 全部偏移偏低 14 bytes
    offset += size
```

Main.abd 的每筆記錄是 **284 bytes**。偏低 14 bytes 導致讀取到的
每筆 `rec` 都相差 14 bytes，`rtype` 欄位（`rec[0x0A]`）讀到無效字元，
被以下條件全部過濾：

```python
if rtype not in ('E', 'I', 'A', 'L'):
    continue    # 235 筆全部跳過 → 輸出 0 筆
```

---

## 修復方案

在 `break` 前加一行 `pos = end + 2`，讓 `pos` 先跨過當前行再終止迴圈，
使 `index_end` 落在正確位置（2,688）。

### 修改位置

**檔案：** `myab-export/myab_export.py`，第 169-170 行

```python
# 修復前
if not any(ext in fname.lower() for ext in ('.abd', '.lst', '.pwd', '\\')):
    break

# 修復後
if not any(ext in fname.lower() for ext in ('.abd', '.lst', '.pwd', '\\')):
    pos = end + 2  # 跳過此行，讓 index_end 落在正確位置
    break
```

### 為何不用 `continue` 而用 `break`

最初嘗試改為 `continue`，但這會造成迴圈繼續掃描二進位資料區。
因為二進位資料中可能出現 `\x01` 和 `\r\n` 的組合，`continue` 會讓
`pos` 不斷前進直到 `int(size_str)` 拋出 `ValueError` 才停止，
屆時 `index_end = pos` 已偏移至二進位資料的深處，導致更嚴重的錯誤。

正確作法是：**先跳過當前行（`pos = end + 2`），再立刻停止（`break`）**，
確保二進位資料區不被當作索引解析。

---

## 驗證結果

修復後執行輸出：

```
處理：peter-20250925.mbu
  Main.abd：66884 bytes，解析 235 筆交易    ← 正確
  Main1.abd：48044 bytes，解析 235 筆備註
  已匯出 235 筆記錄 → target/backup_peter-20250925.csv
  Accounts.abd：9720 bytes，解析 36 筆科目
  已匯出 36 筆科目 → target/backup_peter-20250925_accounts.csv
```

輸出檔案大小：`12,367 bytes`（修復前 72 bytes）。

前兩筆記錄確認格式正確：

```
日期,類型,類別主類,類別次類,帳戶,金額,明細,備註
2019/12/25,I,其他收入,,A-現金,100,,
2019/12/25,A,銀行帳戶,,Equity,0,b戶初值],請修改...
```

---

## 附記：為何此問題只出現在 peter-20250925.mbu

早期測試用的 .mbu（如 `20260401.mbu`，485 KB）只有單一帳號、條目較少，
且最後一個條目是 `.abd` 檔案，因此不會觸發白名單驗證的 `break`。

`peter-20250925.mbu` 是多年度的完整備份（81 個條目），
最後一個條目 `Paynum.dat` 才會觸發此邏輯缺陷。

---

## 相關檔案

| 檔案 | 說明 |
|------|------|
| `myab-export/myab_export.py` | 主程式（已修復） |
| `myab-export/source/peter-20250925.mbu` | 觸發問題的輸入檔（31 MB） |
| `myab-export/target/backup_peter-20250925.csv` | 修復後輸出（235 筆） |
| `development-plan/myAB_mbu解析匯出計畫.md` | .mbu 格式原始分析文件 |
