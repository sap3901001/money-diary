# myAB 記帳軟體資料存放位置分析報告

**分析日期：** 2026-04-01
**應用程式：** MyAB 我的記帳簿 v4.04
**主程式路徑：** `C:\test_soft\MyAB\MyAB.exe`（原位於 `D:\MyAB\`，已複製至 C 槽供 WSL 存取）

---

## 一、資料目錄總覽

myAB 記帳軟體的資料分存於兩個目錄：

| 目錄 | 用途 |
|------|------|
| `C:\test_soft\MyAB\DataBase\` | 主要記帳資料 |
| `C:\test_soft\MyAB\Backup\` | 完整備份檔案 |

---

## 二、主要資料目錄：`C:\test_soft\MyAB\DataBase\`

### 目錄結構

```
C:\test_soft\MyAB\DataBase\
├── krugman21\                              ← 主要使用者帳號資料夾
│   ├── DataBase.lst                        ← 帳冊清單設定檔（文字格式，12 bytes）
│   ├── DataBase.pwd                        ← 密碼設定檔（文字格式，38 bytes）
│   └── 2025-01-01\                         ← 帳冊資料夾（以啟用日期命名）
│       ├── Main.abd      (257,448 bytes)   ← 主交易記錄（最重要）
│       ├── Main1.abd     (184,928 bytes)   ← 備註欄位（204 bytes/筆，104 bytes 標頭）
│       ├── Main2.abd      (16,318 bytes)   ← 交易記錄副本 2
│       ├── Main2a.abd      (7,253 bytes)   ← 交易記錄副本 2a
│       ├── Main3.abd       (3,628 bytes)   ← 交易記錄副本 3
│       ├── Accounts.abd   (11,928 bytes)   ← 科目設定（276 bytes/筆，44 筆）
│       ├── Accounts2.abd     (888 bytes)   ← 四大類型總和標題
│       ├── Expanded.abd      (339 bytes)   ← 展開顯示設定（文字格式）
│       ├── Favorites.abd       (0 bytes)   ← 收藏夾（空）
│       └── Note.abd           (39 bytes)   ← 備註資料
│
└── Test\                                   ← 測試/範例帳號資料夾（內建範例）
    ├── DataBase.lst                         ← 帳冊清單設定檔（文字格式，8 bytes）
    ├── DataBase.pwd                         ← 密碼設定檔（文字格式，14 bytes）
    ├── Paynum.dat                           ← 支付編號暫存（空檔）
    └── Sample\                             ← 範例帳冊（2016-2017 年舊資料）
        ├── Main.abd       (4,120 bytes)
        ├── Main1.abd      (2,960 bytes)
        ├── Main2.abd        (262 bytes)
        ├── Accounts.abd   (3,148 bytes)
        ├── Accounts2.abd    (888 bytes)
        ├── Expanded.abd     (115 bytes)
        ├── Favorites.abd    (109 bytes)
        └── Note.abd          (87 bytes)
```

### 各帳冊標準檔案

每個帳冊資料夾內包含以下標準檔案：

| 檔案名稱 | 格式 | 說明 |
|---------|------|------|
| `Main.abd` | 二進位專有格式 | **主要交易記錄**（最核心的資料檔） |
| `Main1.abd` | 二進位專有格式 | 備註欄位（204 bytes/筆，104 bytes 標頭） |
| `Main2.abd` | 二進位專有格式 | 交易記錄副本 |
| `Main2a.abd` | 二進位專有格式 | 交易記錄副本 2a（部分帳冊才有） |
| `Main3.abd` | 二進位專有格式 | 交易記錄副本 |
| `Accounts.abd` | 二進位專有格式 | 科目設定（276 bytes/筆，44 筆含階層） |
| `Accounts2.abd` | 二進位專有格式 | 四大類型總和標題 |
| `Expanded.abd` | 純文字 | 帳目展開顯示設定 |
| `Favorites.abd` | 二進位專有格式 | 常用項目收藏夾 |
| `Note.abd` | 二進位專有格式 | 備註資料 |

---

## 三、備份目錄：`C:\test_soft\MyAB\Backup\`

```
C:\test_soft\MyAB\Backup\
└── krugman21\
    ├── 20260223.mbu    (437,581 bytes)  ← 2026-02-23 備份
    ├── 20260309.mbu    (451,567 bytes)  ← 2026-03-09 備份
    ├── 20260311.mbu    (453,639 bytes)  ← 2026-03-11 備份
    ├── 20260315.mbu    (459,855 bytes)  ← 2026-03-15 備份
    ├── 20260324.mbu    (459,337 bytes)  ← 2026-03-24 備份
    ├── 20260331.mbu    (461,409 bytes)  ← 2026-03-31 備份
    └── 20260401.mbu    (483,165 bytes)  ← 2026-04-01 備份（最新）
```

| 檔案名稱 | 大小 | 說明 |
|---------|------|------|
| `20260223.mbu` | 437 KB | 最舊備份 |
| `20260309.mbu` | 441 KB | |
| `20260311.mbu` | 443 KB | |
| `20260315.mbu` | 449 KB | |
| `20260324.mbu` | 449 KB | |
| `20260331.mbu` | 451 KB | |
| `20260401.mbu` | 472 KB | **最新備份**（分析作業建議以此為準） |

備份檔命名規則為 `YYYYMMDD.mbu`，內含所有帳冊資料的完整快照。

---

## 四、設定檔說明

| 路徑 | 格式 | 說明 |
|------|------|------|
| `C:\test_soft\MyAB\DataBase\krugman21\DataBase.lst` | 純文字 (CRLF) | 帳冊名稱與路徑索引清單 |
| `C:\test_soft\MyAB\DataBase\krugman21\DataBase.pwd` | 純文字 (CRLF) | 登入密碼（Hex 編碼儲存） |

---

## 五、檔案格式說明

### `.abd` 檔案（Account Book Data）
- myAB 專有二進位格式
- 無法以一般文字編輯器直接閱讀
- 為應用程式核心資料格式

#### Main.abd 記錄結構（284 bytes/筆，固定長度）

| Offset | 大小 | 欄位 | 說明 |
|--------|------|------|------|
| 0x00 | 10B | 日期 | ASCII `YYYY/MM/DD` |
| 0x0A | 1B | 類型 | `E`=支出, `I`=收入, `A`=資產, `L`=負債 |
| 0x0B | 1B | 分隔符 | 固定 `-`（0x2D）|
| 0x0C | 28B | 類別碼 | Big5，格式 `主類.次類`（程式顯示時 `.` 換成 `,`）|
| 0x28 | 8B | 帳戶 | Big5，含前置空格 |
| 0x30 | 26B | 填充區 | 固定 0x20（空格）|
| 0x4A | 4B | 子類型 | `05000000`=E/I，`02000000`=A/L |
| 0x50 | 4B | 金額 | 編碼值（見下方金額編碼說明）|
| 0x54 | ~190B | 明細 | Big5，可為空格填充 |

#### Main1.abd 備註結構（204 bytes/筆）

- 104 bytes 標頭（Big5 文字「修改這筆金額以設定科目初始金額」+ 填充）
- 每筆 204 bytes，備註文字位於記錄內偏移 104
- 備註對齊：note[n] 對應 Main.abd rec[n+1]（rec[0] 無備註）

#### Accounts.abd 科目設定結構（276 bytes/筆）

儲存科目（帳戶分類）定義，對應程式「科目設定」視窗。

| Offset | 大小 | 欄位 | 說明 |
|--------|------|------|------|
| 0x00 | 32B | 科目名稱 | Big5，格式 `TYPE-主類` 或 `TYPE-主類.次類` |
| 0x20 | 1B | 類型旗標 | 01=A(資產), 02=L(負債), 03=I(收入), 04=E(支出), 00=Equity(權益) |
| 0x21 | 243B | 其他資料 | 內部使用 |

- **記錄大小**：276 bytes（固定長度）
- **記錄數**：44 筆（krugman21 帳冊，43 完整記錄 + 1 截斷記錄僅 60 bytes，名稱欄位仍完整）
- **名稱格式**：`TYPE-主類.次類`，其中 `.` 為階層分隔符（與 Main.abd 類別碼格式一致）
- **特殊條目**：Equity（無 `-` 分隔符，為系統內部權益科目）
- **Accounts2.abd**：僅存放「資產總和、負債總和、收入總和、支出總和」四個標題，不含科目定義

**科目類型分布**：

| 類型 | 名稱 | 筆數 |
|------|------|------|
| A | 資產 | 3 |
| L | 負債 | 6 |
| I | 收入 | 2 |
| Equity | 權益 | 1 |
| E | 支出 | 32 |
| **合計** | | **44** |

#### 金額欄位編碼方式 ✅（2026-04-02 定版）

MyAB 的金額欄位**不是直接儲存新台幣金額**，而是經過以下編碼：

1. 將金額乘以 100（轉換為「分」，例如 35 TWD → 3500）
2. 以 IEEE 754 **雙精度浮點數（double，8 bytes）** 表示此值
3. 只取 double 的 **big-endian 高 4 bytes**（含符號位、指數、尾數高位）
4. 以 **little-endian** 順序寫入 Main.abd 的 0x50 偏移處

金額欄位僅儲存**絕對值**，正負號由類型欄位（0x0A）決定：`I`=正（收入），`E`=負（支出）。

**解碼公式（Python）**：

```python
import struct

def decode_amount(stored_le_4bytes: bytes) -> int:
    """將 Main.abd offset 0x50 的 4 bytes (LE) 解碼為 TWD 整數金額"""
    b = stored_le_4bytes
    be_top4 = bytes([b[3], b[2], b[1], b[0]])       # LE → BE
    double_bytes = be_top4 + b'\x00\x00\x00\x00'     # 補零還原為 8-byte double
    val = struct.unpack('>d', double_bytes)[0]        # 解讀為 big-endian double
    return round(val / 100)                           # 除以 100 還原為 TWD
```

**編碼公式（Python）**：

```python
def encode_amount(twd: int) -> bytes:
    """將 TWD 整數金額編碼為 4 bytes (LE)"""
    double_bytes = struct.pack('>d', twd * 100)       # TWD×100 → big-endian double
    be_top4 = double_bytes[:4]                        # 取高 4 bytes
    return bytes([be_top4[3], be_top4[2], be_top4[1], be_top4[0]])  # BE → LE
```

**範例對照**：

| TWD 金額 | ×100 值 | float 讀值 | hex (LE) |
|---:|---:|---:|---|
| 1 | 100 | 3.390625 | 00005940 |
| 35 | 3500 | 5.354492 | 0058AB40 |
| 100 | 10000 | 6.110352 | 0088C340 |
| 1000 | 100000 | 7.762939 | 006AF840 |
| 10000 | 1000000 | 10.907349 | 80842E41 |
| 50000 | 5000000 | 13.192093 | D0125341 |

**驗證結果**：DataBase 全部 973 筆 E/I 記錄，100% 零誤差解碼。

### `.mbu` 檔案（MyAB Backup Unit）
- myAB 專有備份封裝格式
- 內含明文索引 + 二進位資料內容
- 儲存所有帳冊的完整快照

---

## 六、資料統計

| 項目 | 數量/大小 |
|------|----------|
| 使用者帳號數 | 2 個（`krugman21`、`Test`） |
| 帳冊數（krugman21） | 1 個（`2025-01-01`，目前使用中） |
| 帳冊數（Test） | 1 個（`Sample`，範例資料） |
| `.abd` 資料檔總數 | 18 個 |
| 最大單一資料檔 | `krugman21/2025-01-01/Main.abd`（257,448 bytes） |
| 備份檔數量 | 7 個（2026-02-23 ~ 2026-04-01） |
| 最新備份檔 | `20260401.mbu`（483,165 bytes） |

---

## 七、結論

- **最重要的資料檔**：`C:\test_soft\MyAB\DataBase\krugman21\2025-01-01\Main.abd`（主交易記錄）
- **資料組織方式**：使用者帳號 → 帳冊（以啟用日期命名）→ 多個 `.abd` 功能性資料檔
- **備份機制**：程式內建整合備份，產生單一 `.mbu` 完整備份包，留存 7 份歷史備份
- **若需資料保護**：優先備份 `C:\test_soft\MyAB\DataBase\krugman21\` 整個資料夾
- **WSL 存取路徑**：`/mnt/c/test_soft/MyAB/`
