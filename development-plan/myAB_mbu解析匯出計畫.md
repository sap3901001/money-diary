# myAB .mbu 備份檔案解析並匯出 CSV

**建立日期：** 2026-03-31
**最後驗證：** 2026-04-01（第二次深度分析）
**驗證對象：** `20260401.mbu`（krugman21 帳號備份，485,237 bytes）
**參考畫面：** `Account_List02.jpg`、`Account_List03.jpg`（程式執行截圖）

---

## 背景說明

使用者希望分析 MyAB 記帳軟體的備份檔案，評估並實作將記帳資料匯出成 CSV 的工具。
透過二進位逆向分析與實際備份檔驗證，已取得完整的檔案格式與欄位結構。

---

## 技術分析結果（已驗證）

### 一、備份檔案（.mbu）結構

- **路徑**：`C:\test_soft\MyAB\Backup\krugman21\20260331.mbu`
- **大小**：461,409 bytes
- **索引格式**（已驗證）：

```
krugman21           316      2025-01-01\Expanded.abd\x01339\r\n
2025-01-01\Note.abd\x0139\r\n
2025-01-01\Favorites.abd\x010\r\n
...
(每行格式：相對路徑 + 0x01 分隔符 + 大小 + CRLF)
```

> **⚠️ 注意**：第一個檔案條目緊接在使用者名稱行之後（同一行末尾），
> 不是獨立的新行。解析時應讀到 `\x01` 判斷是否有檔案條目開始。

- 索引結束偏移：346（0x15A）
- 索引結束後緊跟各 .abd 檔案的二進位內容（依索引順序串接）
- `krugman21` 帳號涵蓋帳冊：`2025-01-01`（1 個帳冊，共 11 個 .abd 檔案）

#### 索引中的 .abd 檔案順序與起始偏移

**20260331.mbu 實測值**（索引結束偏移：346）：

| 檔案 | 大小 | .mbu 內起始偏移 |
|------|------|----------------|
| Expanded.abd | 339 | 346 |
| Note.abd | 39 | 685 |
| Favorites.abd | 0 | 724 |
| Accounts.abd | 11,928 | 724 |
| Accounts2.abd | 888 | 12,652 |
| Main.abd | 245,520 | 13,201 |
| Main1.abd | 184,928 | 258,721 |
| Main2.abd | 16,318 | 443,649 |
| Main2a.abd | 7,253 | 459,967 |
| Main3.abd | 3,628 | ... |

**20260401.mbu 實測值**（索引結束偏移：352）：

| 檔案 | 大小 | .mbu 內起始偏移 |
|------|------|----------------|
| Main.abd | 258,584 | 13,546 |
| Main1.abd | 185,744 | 272,130 |

---

### 二、Main.abd 交易記錄結構（已驗證）

- **記錄大小**：284 bytes（固定長度）✅
- **記錄數量**：`2025-01-01` 帳冊共 906 筆（DataBase 版本）

#### DataBase 版 Main.abd 欄位結構（`C:\test_soft\MyAB\DataBase\krugman21\...` 路徑直接讀取）

| Offset | 大小 | 欄位 | 編碼 | 說明 |
|--------|------|------|------|------|
| 0x00 | 10B | 日期 | ASCII | `YYYY/MM/DD` 格式 ✅ |
| 0x0A | 1B | 類型 | ASCII | `I`=收入, `E`=支出, `A`=資產, `L`=負債 ✅ |
| 0x0B | 1B | 分隔符 | ASCII | 固定 `-`（0x2D）✅ |
| 0x0C | 28B | **類別碼** | Big5 繁體中文 | 格式：`主類.次類`（例：`加油.機車加油`）✅ |
| 0x28 | 8B | 帳戶 | Big5 繁體中文 | 帳戶名稱（例：`  A-現金`，含前置空格）✅ |
| 0x30 | 26B | （空白區域） | — | 固定空白填充（26 bytes，全記錄為 0x20）✅ |
| 0x4A | 4B | 子類型指示 | uint32 LE | `05 00 00 00`=E/I 類型, `02 00 00 00`=A/L 類型 |
| 0x4E | 2B | 固定零 | — | 固定 `00 00` |
| 0x50 | 4B | **金額（編碼值）** | IEEE 754 float LE | 詳見金額欄位說明 ⚠️ |
| 0x54 | 190B | **明細** | Big5 繁體中文 | 交易明細說明文字（常為空格填充）|
| 0x112 | 12B | 填充 | — | 固定 null 填充 |

> **⚠️ 欄位命名修正**：原計畫將 0x0C 稱為「描述」（description）是錯誤的。
> 實際上 0x0C 儲存的是**類別碼**（類別路徑），對應程式畫面「類別」欄。
> 原計畫將 0x54 後稱為「填充」也是錯誤的，實際上是**明細**欄位。

#### 金額欄位（DataBase 0x50 / .mbu 0x4A）說明 ✅ 公式已定版

**編碼原理**：MyAB 將 `TWD × 100`（分為單位）以 IEEE 754 **雙精度 double** 表示，只保留高 4 bytes（big-endian），以 little-endian 順序寫入。

```python
# 解碼（stored LE 4 bytes → TWD）
def decode_amount(stored_le_4bytes: bytes) -> int:
    b = stored_le_4bytes
    be_top4 = bytes([b[3], b[2], b[1], b[0]])
    double_bytes = be_top4 + b'\x00\x00\x00\x00'
    return round(struct.unpack('>d', double_bytes)[0] / 100)

# 編碼（TWD → stored LE 4 bytes）
def encode_amount(twd: int) -> bytes:
    be = struct.pack('>d', twd * 100)[:4]
    return bytes([be[3], be[2], be[1], be[0]])
```

**驗證結果**（2026-04-02）：DataBase 全部 973 筆 E/I 記錄，**100% 零誤差解碼**。

- ✅ float 編碼的是**絕對值**（無符號），正負由類型欄位（I/E）決定
- ✅ I/E 類型一致性：同金額 float 完全相同
- ✅ 跨類別一致性：同金額不同類別 float 完全相同
- 詳見 `myAB金額編碼分析與驗證.md`

#### 類別碼格式說明

- 程式畫面「類別」欄顯示格式：`E-加油,機車加油`
- 儲存在 binary 中：類型 `E`（0x0A）+ 類別碼 `加油.機車加油`（0x0C）
- **分隔符差異**：儲存用 `.`（0x2E），程式顯示用 `,`（逗號）

---

### 三、.mbu 版 Main.abd 記錄結構 ✅（2026-04-02 實作驗證，再次更正）

> ⚠️ **「55 bytes 前綴模型」及「6 bytes 左旋轉模型」均為錯誤結論。**
> 兩者皆源自 .mbu 索引偏移計算的微小誤差，導致記錄邊界錯位後誤判為格式差異。

**正確結論**：.mbu 內的 Main.abd **與 DataBase 版格式完全一致**，無需任何偏移轉換。

**驗證依據**（2026-04-02）：
- 將 `20260402.mbu` 中提取的 Main.abd（267,672 bytes）與 `DataBase/krugman21/2025-01-01/Main.abd` 逐位元組比對
- **100% 完全一致**（267,672 / 267,672 bytes match）
- 使用 DataBase 版解析函式直接讀取 .mbu 中的 Main.abd，成功解析 942~975 筆交易記錄

**結論**：.mbu 和 DataBase 使用相同的 Main.abd 欄位偏移（0x00 日期、0x0A 類型、0x0C 類別、0x28 帳戶、0x50 金額、0x54 明細）。

---

### 四、Main1.abd 備註欄結構（2026-04-01 新增）

Main1.abd 儲存「備註」欄位（程式畫面的「備註」Column）。

- **檔案起始**：104 bytes 標頭（Big5 文字 `修改這筆金額以設定科目初始金額` + 空白/null 填充）
- **記錄大小**：204 bytes（固定長度）
- **備註文字**：位於記錄內部偏移 104 處起（Big5 編碼）
- **記錄對應**：Main1.abd note[n] → Main.abd rec[n+1]（偏移 +1）

> ⚠️ **備註對齊修正**（2026-04-02）：原文記載 note[n] → rec[n]（1:1 對應）為誤。
> 經 VER2 測試記錄驗證（30 筆 100% 匹配），正確對應為 **note[n] → rec[n+1]**。
> 即 Main.abd rec[0] 無對應備註，rec[i]（i≥1）的備註為 note[i-1]。

> ⚠️ **標頭大小修正**（2026-04-02）：原文記載 98 bytes 為誤。
> 以 header=104 計算：`(199004-104)/204 = 975.0`（整除），header=98 則有 6 bytes 餘數。

**Python 讀取方式**：
```python
MAIN1_HEADER = 104
MAIN1_REC = 204
MAIN1_NOTE_OFFSET = 104  # 記錄內備註欄起始位置

def read_main1_note(main1_data, main_rec_idx):
    """取得 Main.abd rec[main_rec_idx] 對應的備註"""
    note_idx = main_rec_idx - 1  # note[n] → rec[n+1]
    if note_idx < 0:
        return ''
    start = MAIN1_HEADER + note_idx * MAIN1_REC
    rec = main1_data[start:start + MAIN1_REC]
    note = rec[MAIN1_NOTE_OFFSET:].rstrip(b'\x00\x20').decode('big5', 'replace')
    return note.strip('\x00').strip()
```

**驗證**（2026-04-02）：以 VER2 測試記錄（備註格式 `VER2-{E|I|CAT}-{金額}`）交叉比對，30/30 筆金額與備註完全匹配。

---

### 五、Accounts.abd 科目設定結構（已驗證，2026-04-02 完成匯出）

- **記錄大小**：276 bytes（固定長度）✅ 已更正（原計畫 284 bytes 為誤，原始分析 256 bytes 亦為誤）
- **記錄數**：44 筆（43 完整記錄 + 1 截斷記錄，截斷僅 60 bytes 但名稱欄位完整）
- **名稱欄位**：offset 0x00, 32 bytes, Big5 編碼
- **名稱格式**：`TYPE-主類` 或 `TYPE-主類.次類`（`.` 為階層分隔符）
- **類型旗標**：offset 0x20，01=A(資產), 02=L(負債), 03=I(收入), 04=E(支出), 00=Equity(權益)
- **Accounts2.abd**：僅存放「資產總和、負債總和、收入總和、支出總和」標題，不含科目定義

**匯出 CSV 欄位**：類型, 類型名稱, 階層, 主類, 次類

### 六、發票欄位來源（2026-04-01 新增）

以 DataBase `2025-01-01` 帳冊實測（Main.abd 共 910 筆）比對結果：

- `Main2.abd` 結構為：**10 bytes 標頭 + 910 筆 × 18 bytes**
- 每筆 `Main2` 記錄在 offset `16:18` 出現 2-byte 旗標：
   - `00 00`（908 筆）
   - `FF FF`（2 筆）
- `Main2a.abd` 為固定值（5 bytes 標頭 + 910 筆 × 8 bytes，內容均為 `0000002020000000`）
- `Main3.abd` 為固定值（4 bytes 標頭 + 910 筆 × 4 bytes，內容均為 `22220d0a`）

**結論（目前可確認）**：
- 程式畫面「發票」欄位最可能對應 `Main2.abd rec[n][16:18]` 的旗標值（`0000/FFFF`）。
- 目前資料中僅觀察到「是否有發票標記」旗標，尚未看到發票號碼文字欄位。

**第二階段驗證（2026-04-01）**：
- 以正則掃描 `Main/Main1/Main2/Main2a/Main3/Note/Expanded/Accounts/Accounts2`，未找到發票常見 ASCII 格式（如 `AA12345678`、`AA-12345678`）。
- 在 `Main2.abd` 910 筆中，僅第 16~17 bytes 會變化，且僅出現於 rec[64]、rec[770]（`FFFF`）；其餘 bytes 為固定樣板。
- `Main2a.abd` 與 `Main3.abd` 於全記錄均為固定值，未觀察到可變字串欄位。

**目前判定**：在現有資料集內，發票欄位僅可確認為「有/無」旗標；未發現發票號碼文字欄位。

---

## 程式畫面欄位對應

| 程式畫面欄位 | Binary 來源（DataBase 偏移）| .mbu 偏移 | 說明 |
|-------------|---------------------------|-----------|------|
| 日期 | 0x00 (ASCII) | 同 DataBase | YYYY/MM/DD |
| 類別 | 0x0A + 0x0C (Big5) | 同 DataBase | `類型-主類,次類`（`.` 顯示為 `,`）|
| 金額 | 0x50 (float) | 同 DataBase | ✅ `top4(double(TWD×100))` BE→LE，已定版 |
| 累計 | 程式動態計算 | — | 非儲存值 |
| 明細 | 0x54 (Big5) | 同 DataBase | 交易明細說明 |
| 備註 | Main1.abd note[n] → rec[n+1] | 同 DataBase | Big5，204 bytes/筆，104 bytes 標頭，偏移 +1 ✅ |
| 發票 | Main2.abd rec[n][16:18] | Main2.abd | 旗標：`0000`=無、`FFFF`=有（目前未發現發票號碼文字） |

---

## 實作方案

### 輸出 CSV 欄位

```
日期, 類型, 類別主類, 類別次類, 帳戶, 金額, 明細, 備註
```

| CSV 欄位 | 來源 | 說明 |
|---------|------|------|
| 日期 | Offset 0x00 | YYYY/MM/DD |
| 類型 | Offset 0x0A | E / I / A / L |
| 類別主類 | Offset 0x0C，`.` 前半段 | Big5 解碼後分割 |
| 類別次類 | Offset 0x0C，`.` 後半段 | Big5 解碼後分割 |
| 帳戶 | Offset 0x28 | Big5 解碼，去除前置空格 |
| 金額 | Offset 0x50 | `round(unpack('>d', LE→BE + 0x00×4) / 100)`，I=正值，E=負值 |
| 明細 | Offset 0x54 | Big5 解碼 |
| 備註 | Main1.abd note[i-1] | Big5 解碼，rec[0] 無備註 |

---

### Python 腳本設計 ✅ 已完成（2026-04-02）

**腳本位置**：`C:\test_soft\MyAB\note\myab_export\myab_export.py`

**目錄結構**：
```
note/myab_export/
├── myab_export.py       ← 主程式（零參數執行）
├── source/              ← 輸入檔案（使用者手動放入）
└── target/              ← 輸出 CSV
```

**核心邏輯**：

1. **模式偵測**：掃描 `source/` 目錄，依第一個檔案副檔名決定模式
   - `.mbu` → mbu 模式（處理所有 .mbu，各產出交易 CSV + 科目 CSV）
   - `.abd` → db 模式（讀取 Main.abd + 可選 Main1.abd + 可選 Accounts.abd）

2. **解析 .mbu 索引**（mbu 模式）
   - 讀取檔頭，解析 `相對路徑 + 0x01 + 大小 + CRLF` 格式的索引
   - 從 .mbu 中提取 Main.abd、Main1.abd、Accounts.abd 的資料

3. **解析 Main.abd**（兩種模式共用同一解析函式）
   - .mbu 內的 Main.abd 與 DataBase 版格式完全一致
   - 按 284 bytes 切割每筆記錄
   - 欄位偏移：0x00 日期，0x0A 類型，0x0C 類別，0x28 帳戶，0x50 金額，0x54 明細
   - 備註：Main1.abd note[i-1] 對應 Main.abd rec[i]

4. **解析 Accounts.abd**（科目設定）
   - 按 276 bytes 切割，最後截斷記錄（60 bytes）也處理
   - 名稱欄位 32 bytes Big5，格式 `TYPE-主類.次類`
   - 跳過空白記錄，Equity 特殊處理

5. **輸出 CSV**
   - 交易記錄：`transactions.csv` / `backup_原檔名.csv`
   - 科目設定：`accounts.csv` / `backup_原檔名_accounts.csv`
   - 使用 UTF-8-BOM 編碼（確保 Excel 開啟中文正常顯示）

### 執行方式

```bash
cd /mnt/c/test_soft/MyAB/note/myab_export

# db 模式：將 Main.abd（+ 可選 Main1.abd、Accounts.abd）放入 source/
python3 myab_export.py
# → target/transactions.csv + target/accounts.csv

# mbu 模式：將 *.mbu 放入 source/
python3 myab_export.py
# → target/backup_20260401.csv + target/backup_20260401_accounts.csv, ...
```

---

## 關鍵檔案路徑

| 檔案 | 完整路徑 |
|------|---------|
| 備份來源（最新） | `C:\test_soft\MyAB\Backup\krugman21\20260402.mbu` |
| 主交易資料 | `C:\test_soft\MyAB\DataBase\krugman21\2025-01-01\Main.abd` |
| 科目設定 | `C:\test_soft\MyAB\DataBase\krugman21\2025-01-01\Accounts.abd`（276 bytes/筆，44 筆）|
| 匯出工具目錄 | `C:\test_soft\MyAB\note\myab_export\` |
| 匯出腳本 | `C:\test_soft\MyAB\note\myab_export\myab_export.py` |
| 程式畫面截圖 | `C:\test_soft\MyAB\Account_List02.jpg` |

---

## 驗證方式

1. 將 Main.abd + Main1.abd + Accounts.abd 放入 `source/`，執行腳本
2. 以 Excel 開啟 `target/transactions.csv`，確認中文帳戶名稱、分類顯示正確
3. 確認金額欄位：I=正值，E=負值
4. 確認備註欄位與程式畫面一致（使用 VER2 測試記錄交叉驗證）
5. 抽查幾筆記錄的**日期、類別、金額**與 MyAB 程式畫面對照驗證
6. 以 Excel 開啟 `target/accounts.csv`，確認 44 筆科目（含 Equity）與科目設定畫面一致

---

## 驗證總結

### 第一次驗證（2026-04-01 初版）

| 項目 | 原計畫 | 驗證結果 |
|------|--------|---------|
| .mbu 索引格式 | 基本正確 | ✅ 正確，但第一個條目在 header 行末尾 |
| 記錄大小（Main.abd）| 284 bytes | ✅ 確認 |
| 記錄大小（Accounts.abd）| 256 bytes | ❌ 實為 276 bytes |
| Accounts.abd 記錄數 | 約 38 筆 | ❌ 實為 44 筆（276 bytes/筆，43 完整 + 1 截斷）|
| 日期欄位（DataBase）| 0x00 | ✅ 確認 |
| 類型欄位（DataBase）| 0x0A | ✅ 確認 |
| 類別碼欄位（DataBase）| 0x0C（原稱「描述」）| ✅ 確認（但應稱「類別碼」非「描述」）|
| 帳戶欄位（DataBase）| 0x28 | ✅ 確認 |
| 分類欄位（0x30）| Big5 分類代碼 | ⚠️ 實為空格填充，類別已在 0x0C |
| .mbu 記錄前綴 | 未提及 | ❌ 每筆記錄含 55 bytes 前綴，需偏移 +55 |
| .mbu 初始記錄 | 未提及 | ❌ 第 1 筆為後設資料，跳過才是交易記錄 |
| 金額（0x50）| IEEE 754 float = TWD | ✅ **已解碼**：`top4(double(TWD×100))` BE→LE，973 筆零誤差 |
| 0x54 以後 | 填充（無資料）| ❌ 實為「明細」欄位（Big5 文字）|
| 類別分隔符 | 未提及 | ⚠️ 儲存用 `.`，程式顯示用 `,` |

### 第二次驗證（2026-04-01 深度分析，使用 20260401.mbu）

| 項目 | 第一次結論 | 第二次驗證結果 |
|------|-----------|--------------|
| .mbu 記錄偏移模型 | +55 前綴模型 | ❌❌ **再次更正（2026-04-02）**：.mbu 與 DataBase 格式完全一致，無需偏移轉換（6 bytes 旋轉亦為誤） |
| .mbu 日期讀取 | `rec[55:65]` | ❌ **更正**：直接用 DataBase 偏移 `rec[0:10]` |
| .mbu 初始記錄 | 後設資料，跳過 | ❌ **更正**：rec[0] 即為有效記錄，1:1 對應 DataBase |
| Main1.abd 結構 | 未分析 | ✅ **新增**：104 bytes 標頭 + 204 bytes/筆，備註位於記錄內偏移 104 |
| Main1.abd 備註對齊 | note[n]→rec[n] | ❌ **更正（2026-04-02）**：note[n] → rec[n+1]（偏移 +1）|
| 金額符號 | 未知 | ✅ **確認**：float 為絕對值，I/E 類型欄決定正負 |
| 金額公式 | 線性近似 | ✅ **已定版**：`top4(double(TWD×100))` BE→LE，973 筆零誤差 |
| rec[906] 金額 | — | ✅ **已確認**：飲料，2026/03/31，float=5.354492，金額 35 |

---

## 問題解決歷程

### 2026-04-01 第一～四階段（探索期）

1. **第一階段**：以 6 個已知資料點嘗試線性、指數、冪次等模型，全部失敗
2. **第三階段**：以 31 筆樣本擬合指數近似式，RMSE~4.08、最大誤差~11，不足以定版
3. **第四階段**：以 TST-20260401 測試批次 30 筆，發現 Main/Main1 配對偏移 +1 問題，3 筆爭議樣本（001/I01/I02）未能收斂

### 2026-04-02 第五階段（突破與定版）✅

1. **VER2 測試設計**：33 筆，備註格式 `VER2-{E|I|CAT}-{金額}`，消除配對歧義
2. **位元模式分析**：發現 TWD 翻倍時 int_rep 恰好增加 2^20
3. **突破**：`BASE=0x40590000` = `top32(double(100.0))`，推導出 `stored = top4(double(TWD×100))`
4. **全量驗證**：DataBase 973 筆 E/I 記錄，**100% 零誤差**
5. **已確認**：I/E 一致性 ✓、跨類別一致性 ✓、全域通用 ✓

### 🟢 已完成的分析

- ✅ .mbu 索引解析（含第一個條目邊界問題）
- ✅ Main.abd 記錄結構（.mbu 與 DataBase 格式完全一致，已驗證）
- ✅ Main1.abd 備註欄結構（header=104，note[n]→rec[n+1]）
- ✅ 所有欄位的正確偏移
- ✅ 金額符號機制（絕對值 + I/E 類型欄）
- ✅ **金額編碼公式**（`top4(double(TWD×100))` BE→LE，已定版）
- ✅ **CSV 匯出工具**（`note/myab_export/myab_export.py`，已完成）
- ✅ **科目設定匯出**（Accounts.abd → accounts.csv，44 筆科目含階層）

---

## 未處理議題與優先級

| 優先級 | 議題 | 現況 |
|------|------|------|
| ~~P1~~ | ~~金額公式定版~~ | **已完成 ✓**（2026-04-02） |
| ~~P2~~ | ~~CSV 匯出腳本實作~~ | **已完成 ✓**（2026-04-02） |
| ~~P3~~ | ~~MyAB.exe 逆向分析~~ | **不再需要** |

---

## 進度紀錄

### 2026-04-01
1. 完成兩份文件內容對齊。
2. 完成 TST-20260401 測試批次分析，發現配對偏移問題。
3. 暫行近似公式誤差 2.61~11 TWD，不足定版。

### 2026-04-02
1. 完成 VER2 測試設計與輸入（33 筆）。
2. 從 int_rep 位元模式發現突破：`stored = top4(double(TWD×100))`。
3. 全量驗證 973 筆 100% 零誤差，**金額公式正式定版**。
4. 實作 CSV 匯出工具 `note/myab_export/myab_export.py`。
5. 發現並修正：.mbu 內 Main.abd 與 DataBase 格式完全一致（6 bytes 旋轉模型為誤）。
6. 發現並修正：Main1.abd header 為 104 bytes（非 98），備註對齊為 note[n]→rec[n+1]。
7. 驗證通過：db 模式 975 筆、mbu 模式 942 筆，VER2 備註對齊 30/30 筆匹配。
8. 更新所有分析文件。
9. 新增科目設定匯出功能：解析 Accounts.abd（276 bytes/筆，44 筆科目含 Equity）。
10. 科目 CSV 欄位：類型、類型名稱、階層、主類、次類。db 模式及 mbu 模式均驗證通過。

## 專案狀態

**所有工作已完成。** 逆向分析與 CSV 匯出工具均已驗證通過。

---

## 可行性結論

| 項目 | 評估 |
|------|------|
| 格式複雜度 | 中等（專有二進位，但結構固定規律）|
| 編碼處理 | 需 Big5 解碼，Python 原生支援 |
| 日期 / 類別 / 帳戶 / 明細 CSV 匯出 | ✅ **可行** |
| 金額 CSV 匯出 | ✅ **可行**（公式已定版，零誤差）|
| DataBase 直接讀取 | ✅ 推薦（比 .mbu 解析更簡單）|
| 實作工具 | Python 3（標準函式庫即可，無需第三方套件）|
