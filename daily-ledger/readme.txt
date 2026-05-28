Daily Ledger — 啟動說明
========================

專案位置（Windows）：C:\money-diary\daily-ledger
專案位置（WSL）    ：/mnt/c/money-diary/daily-ledger
瀏覽器入口：http://localhost:8000/

Python 版本需求：3.10 以上
依賴套件：fastapi, uvicorn[standard], python-multipart, pytest, httpx, pytest-cov


============================
一、Windows cmd 環境
============================

【一鍵啟動器（建議）】

  在檔案總管中雙擊 start.bat，或在 cmd 執行：
    cd C:\money-diary\daily-ledger
    start.bat

  會自動：建立 venv（首次）→ 安裝依賴（首次）→ 開啟瀏覽器 → 啟動伺服器

【關閉服務】

  執行 stop.bat，或直接關閉 cmd 視窗。

【手動安裝與啟動】

  1. 開啟 cmd
  2. cd C:\money-diary\daily-ledger
  3. python -m venv venv-win
  4. venv-win\Scripts\pip install -r requirements.txt
  5. venv-win\Scripts\python -m uvicorn app:app --port 8000 --reload

【執行測試】

  cd C:\money-diary\daily-ledger
  venv-win\Scripts\pytest tests\

  # 只跑單元測試
  venv-win\Scripts\pytest tests\unit\

  # 只跑 API 測試
  venv-win\Scripts\pytest tests\api\

  # 只跑整合測試
  venv-win\Scripts\pytest tests\integration\

  # 含覆蓋率報告
  venv-win\Scripts\pytest tests\ --cov=. --cov-report=term-missing

  # 執行指定測試
  venv-win\Scripts\pytest tests\ -k "test_reorder"


============================
二、WSL（Windows Subsystem for Linux）
============================

【一鍵啟動器（建議）】

  cd /mnt/c/money-diary/daily-ledger
  bash start.sh

  會自動：建立 venv（首次）→ 安裝依賴（首次）→ 背景開啟瀏覽器 → 啟動伺服器

【關閉服務】

  bash stop.sh  或按 Ctrl+C

【手動安裝與啟動】

  1. 開啟 WSL 終端機
  2. cd /mnt/c/money-diary/daily-ledger
  3. python3 -m venv venv
  4. source venv/bin/activate
  5. pip install -r requirements.txt
  6. uvicorn app:app --port 8000 --reload

【執行測試】

  ※ 需先啟用虛擬環境：source venv/bin/activate

  pytest tests/
  pytest tests/unit/
  pytest tests/api/
  pytest tests/integration/
  pytest tests/ --cov=. --cov-report=term-missing
  pytest tests/ -k "test_reorder"

【注意】
  若使用 WSL1，localhost 可能無法直接存取，
  請改用 WSL 的 IP（執行 hostname -I 取得）存取。


============================
三、資料檔案位置
============================
  交易記錄：data/main_db.csv
  分類設定：data/categories.csv

  ※ 這兩個檔案為純文字 CSV，可用 Excel 或記事本直接檢視。
