@echo off
echo 正在關閉 Daily Ledger (port 8000)...
set FOUND=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 "') do (
    set FOUND=1
    taskkill /PID %%a /F >nul 2>&1
)
if "%FOUND%"=="1" (
    echo 服務已關閉。
) else (
    echo Daily Ledger 服務未在執行中。
)
