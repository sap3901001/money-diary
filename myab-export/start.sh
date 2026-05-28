#!/bin/bash
cd "$(dirname "$0")"
echo "執行 MyAB 資料匯出..."
python3 myab_export.py
echo "完成。結果存放於 target/ 目錄。"
