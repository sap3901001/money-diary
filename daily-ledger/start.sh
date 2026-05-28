#!/bin/bash
cd "$(dirname "$0")"

VENV_DIR="venv"

venv_python() {
    if [ -f "$VENV_DIR/bin/python" ]; then
        echo "$VENV_DIR/bin/python"
    else
        echo ""
    fi
}

VENV_PY=$(venv_python)
if [ -z "$VENV_PY" ] || ! "$VENV_PY" --version &>/dev/null; then
    echo "venv 無效，重新建立..."
    rm -rf "$VENV_DIR"

    PYTHON_CMD=""
    for cmd in python3 python; do
        if "$cmd" -c "import sys" &>/dev/null; then
            PYTHON_CMD="$cmd"
            break
        fi
    done
    if [ -z "$PYTHON_CMD" ]; then
        echo "錯誤：找不到可用的 Python，請先安裝 Python 3。"
        exit 1
    fi

    "$PYTHON_CMD" -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "錯誤：無法建立虛擬環境。"
        exit 1
    fi

    VENV_PY=$(venv_python)
    echo "安裝依賴套件..."
    "$VENV_PY" -m pip install -r requirements.txt
fi

source "$VENV_DIR/bin/activate"

# 開啟瀏覽器（WSL 用 explorer.exe，Linux 桌面用 xdg-open）
(sleep 1 && (explorer.exe http://localhost:8000/ 2>/dev/null || xdg-open http://localhost:8000/ 2>/dev/null || true)) &

python -m uvicorn app:app --port 8000 --reload
