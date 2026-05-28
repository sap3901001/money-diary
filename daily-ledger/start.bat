@echo off
cd /d %~dp0

if not exist venv-win\Scripts\python.exe (
    echo 建立虛擬環境...
    python -m venv venv-win
    if errorlevel 1 (
        echo 錯誤：找不到 Python，請先安裝 Python 3。
        pause
        exit /b 1
    )
    echo 安裝依賴套件...
    venv-win\Scripts\pip install -r requirements.txt
)

echo 啟動 Daily Ledger...
start http://localhost:8000/
venv-win\Scripts\python -m uvicorn app:app --port 8000 --reload
