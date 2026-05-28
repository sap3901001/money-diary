MyAB 記帳資料匯出工具
=====================

功能說明
--------
本工具可將 MyAB 我的記帳簿的記帳資料及科目設定匯出為 CSV 檔案，
支援直接讀取 DataBase 檔案或從 .mbu 備份檔匯出。

交易記錄 CSV 欄位：日期、類型、類別主類、類別次類、帳戶、金額、明細、備註
- 金額：收入(I)為正值，支出(E)為負值

科目設定 CSV 欄位：類型、類型名稱、階層、主類、次類
- 類型：A(資產)、L(負債)、I(收入)、E(支出)、Equity(權益)
- 階層：主類或次類（以名稱中的 . 分隔符判斷）

編碼：UTF-8-BOM（可直接用 Excel 開啟，中文不會亂碼）


目錄結構
--------
myab-export/
  myab_export.py   主程式
  start.bat        啟動器（Windows cmd）
  start.sh         啟動器（WSL/Linux）
  source/          輸入檔案放這裡
  target/          匯出的 CSV 會產生在這裡
  readme.txt       本說明檔


使用方式
--------

步驟一：將輸入檔案放入 source/ 目錄

  模式 A - 從 DataBase 匯出：
    將 Main.abd 複製到 source/
    若需要備註欄，一併複製 Main1.abd（非必要）
    若需要科目設定，一併複製 Accounts.abd（非必要）

  模式 B - 從備份檔匯出：
    將 .mbu 檔案複製到 source/（可放多個）
    科目設定會自動從 .mbu 中提取，無需額外檔案

  注意：請勿同時放入 .mbu 和 .abd 檔案，程式會以先偵測到的副檔名決定模式。

步驟二：執行程式

  Windows cmd：
    cd C:\money-diary\myab-export
    start.bat

  WSL/Linux：
    cd /mnt/c/money-diary/myab-export
    bash start.sh

  不需要任何參數，程式會自動偵測 source/ 的內容決定模式。

步驟三：取得結果

  模式 A 輸出：
    target/transactions.csv          交易記錄
    target/accounts.csv              科目設定（需有 Accounts.abd）

  模式 B 輸出（每個 .mbu 各產生一組）：
    target/backup_原檔名.csv              交易記錄
    target/backup_原檔名_accounts.csv     科目設定
    例如 20260401.mbu 會產生：
      target/backup_20260401.csv
      target/backup_20260401_accounts.csv


檔案來源路徑參考
----------------
DataBase 檔案位置：
  C:\test_soft\MyAB\DataBase\krugman21\2025-01-01\Main.abd
  C:\test_soft\MyAB\DataBase\krugman21\2025-01-01\Main1.abd
  C:\test_soft\MyAB\DataBase\krugman21\2025-01-01\Accounts.abd

備份檔位置：
  C:\test_soft\MyAB\Backup\krugman21\


執行環境需求
------------
Python 3（僅使用標準函式庫，無需安裝額外套件）


精簡對照表
----------

一、資料流（source -> parser -> target）

| 輸入檔案 | 解析函式 | 輸出檔案 |
|---------|----------|---------|
| Main.abd（DataBase） | parse_main_db | target/transactions.csv |
| Main1.abd（DataBase，可選） | parse_main1_notes | 合併到 transactions.csv 的「備註」欄 |
| Accounts.abd（DataBase，可選） | parse_accounts | target/accounts.csv |
| *.mbu（Backup） | parse_mbu_index -> parse_main_db / parse_main1_notes / parse_accounts | target/backup_原檔名.csv、target/backup_原檔名_accounts.csv |

二、Main.abd 交易欄位對照（每筆 284 bytes）

| CSV 欄位 | Main.abd 偏移 | 長度 | 說明 |
|---------|--------------|------|------|
| 日期 | 0x00 | 10B | ASCII，格式 YYYY/MM/DD |
| 類型 | 0x0A | 1B | E=支出、I=收入、A=資產、L=負債 |
| 類別主類 / 類別次類 | 0x0C | 28B | Big5，原始格式為 主類.次類，程式分割為兩欄 |
| 帳戶 | 0x28 | 8B | Big5 |
| 金額 | 0x50 | 4B | 自訂編碼，decode_amount 解碼為 TWD 整數；E 轉負值 |
| 明細 | 0x54 | 約190B | Big5 |
| 備註 | 來自 Main1.abd | 依 Main1 結構 | 由 parse_main1_notes 解析後依索引對齊 |

三、Main1.abd 備註對照

| 項目 | 值 |
|------|----|
| 檔頭大小 | 104 bytes |
| 每筆大小 | 204 bytes |
| 備註起始位移（記錄內） | 104 |
| 對齊規則 | note[n] 對應 Main.abd 的第 n+1 筆記錄 |

四、Accounts.abd 科目輸出對照

| CSV 欄位 | 來源規則 |
|---------|----------|
| 類型 | 名稱中「-」前字串，如 A/L/I/E；無「-」時整串視為類型（如 Equity） |
| 類型名稱 | TYPE_MAP 映射：A資產、L負債、I收入、E支出、Equity權益 |
| 階層 | 有「.」視為次類，否則主類 |
| 主類 | 「主類.次類」的主類部分 |
| 次類 | 「主類.次類」的次類部分（無則空白） |
