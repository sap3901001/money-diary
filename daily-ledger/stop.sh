#!/bin/bash

PIDS=$(pgrep -f "uvicorn app:app")

if [ -z "$PIDS" ]; then
    echo "Daily Ledger 服務未在執行中。"
else
    echo "正在關閉 Daily Ledger 服務（PID: $PIDS）..."
    pkill -f "uvicorn app:app"
    sleep 1
    if pgrep -f "uvicorn app:app" &>/dev/null; then
        echo "強制終止..."
        pkill -9 -f "uvicorn app:app"
    fi
    echo "服務已關閉。"
fi
