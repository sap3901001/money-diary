@echo off
cd /d %~dp0
echo 執行 MyAB 資料匯出...
python myab_export.py
if errorlevel 1 (
    echo 執行失敗，請確認 Python 已安裝並將原始檔放入 source\ 目錄。
)
echo.
echo 完成。結果存放於 target\ 目錄。
pause
