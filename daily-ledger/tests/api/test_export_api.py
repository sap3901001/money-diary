"""
Step 6 測試：CSV 匯出 API（GET /api/export）
"""
import sys
import csv
import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import data_manager as dm


@pytest.fixture(autouse=True)
def patch_data(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dm, "MAIN_DB", tmp_path / "main_db.csv")
    monkeypatch.setattr(dm, "CATEGORIES_CSV", tmp_path / "categories.csv")
    dm.init_data_files()
    dm.add_category("E", "餐飲費", "早餐")
    dm.add_category("E", "餐飲費", "午餐")
    dm.add_category("I", "薪資", "")


@pytest.fixture
def client():
    from app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _parse_csv(content: bytes) -> list[dict]:
    """解析 UTF-8 BOM CSV，回傳 list[dict]。"""
    text = content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


# ---------------------------------------------------------------------------
# 正常匯出
# ---------------------------------------------------------------------------

def test_export_basic(client):
    """基本匯出：正確回傳 CSV 內容與 header。"""
    dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "豆漿", "")
    dm.add_transaction("2026-02-05", "I", "薪資", "", 50000, "薪水", "")

    res = client.get("/api/export?from=2026-01-01&to=2026-12-31")
    assert res.status_code == 200
    rows = _parse_csv(res.content)
    assert len(rows) == 2


def test_export_date_filter(client):
    """只回傳指定日期範圍內的資料。"""
    dm.add_transaction("2026-01-05", "E", "餐飲費", "早餐", 80, "早餐", "")
    dm.add_transaction("2026-03-10", "E", "餐飲費", "午餐", 120, "便當", "")
    dm.add_transaction("2026-06-20", "I", "薪資", "", 50000, "薪水", "")

    res = client.get("/api/export?from=2026-02-01&to=2026-05-31")
    assert res.status_code == 200
    rows = _parse_csv(res.content)
    assert len(rows) == 1
    assert rows[0]["明細"] == "便當"


def test_export_boundary_dates_included(client):
    """from 與 to 當天的資料應包含（閉區間）。"""
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 80, "首日", "")
    dm.add_transaction("2026-01-31", "E", "餐飲費", "午餐", 120, "末日", "")
    dm.add_transaction("2026-02-01", "E", "餐飲費", "早餐", 50, "次月", "")

    res = client.get("/api/export?from=2026-01-01&to=2026-01-31")
    rows = _parse_csv(res.content)
    assert len(rows) == 2


def test_export_empty_range(client):
    """範圍內無資料時，回傳只有 header 的 CSV。"""
    dm.add_transaction("2025-12-31", "E", "餐飲費", "早餐", 80, "去年", "")

    res = client.get("/api/export?from=2026-01-01&to=2026-12-31")
    assert res.status_code == 200
    rows = _parse_csv(res.content)
    assert len(rows) == 0


def test_export_sort_order(client):
    """匯出資料應依日期 ASC + 建立時間 ASC 排序。"""
    dm.add_transaction("2026-01-03", "E", "餐飲費", "早餐", 80, "第三天", "")
    dm.add_transaction("2026-01-01", "E", "餐飲費", "午餐", 50, "第一天", "")
    dm.add_transaction("2026-01-02", "E", "餐飲費", "早餐", 70, "第二天", "")

    res = client.get("/api/export?from=2026-01-01&to=2026-01-31")
    rows = _parse_csv(res.content)
    dates = [r["日期"] for r in rows]
    assert dates == sorted(dates), "匯出應依日期 ASC 排序"


def test_export_all_fields_present(client):
    """匯出欄位應包含所有 9 個欄位。"""
    dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "豆漿", "備註內容")

    res = client.get("/api/export?from=2026-01-01&to=2026-12-31")
    rows = _parse_csv(res.content)
    assert len(rows) == 1
    expected_fields = {"id", "日期", "類型", "類別主類", "類別次類", "金額", "明細", "備註", "建立時間"}
    assert expected_fields == set(rows[0].keys())


# ---------------------------------------------------------------------------
# HTTP 回應格式
# ---------------------------------------------------------------------------

def test_export_content_type(client):
    """Content-Type 應為 text/csv; charset=utf-8。"""
    dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "豆漿", "")

    res = client.get("/api/export?from=2026-01-01&to=2026-12-31")
    assert "text/csv" in res.headers["content-type"]
    assert "utf-8" in res.headers["content-type"]


def test_export_utf8_bom(client):
    """匯出檔案應包含 UTF-8 BOM（Excel 友善）。"""
    dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "豆漿", "")

    res = client.get("/api/export?from=2026-01-01&to=2026-12-31")
    assert res.content[:3] == b"\xef\xbb\xbf", "應以 UTF-8 BOM 開頭"


def test_export_content_disposition_filename(client):
    """Content-Disposition 應含正確的下載檔名。"""
    dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "豆漿", "")

    res = client.get("/api/export?from=2026-01-15&to=2026-03-20")
    cd = res.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "daily_ledger_20260115_20260320.csv" in cd


# ---------------------------------------------------------------------------
# 輸入驗證
# ---------------------------------------------------------------------------

def test_export_missing_from(client):
    """缺少 from 參數應回傳 422。"""
    res = client.get("/api/export?to=2026-12-31")
    assert res.status_code == 422


def test_export_missing_to(client):
    """缺少 to 參數應回傳 422。"""
    res = client.get("/api/export?from=2026-01-01")
    assert res.status_code == 422


def test_export_invalid_date_format_from(client):
    """from 格式錯誤（非 YYYY-MM-DD）應回傳 422。"""
    res = client.get("/api/export?from=20260101&to=2026-12-31")
    assert res.status_code == 422
    assert "from" in res.json()["detail"]


def test_export_invalid_date_format_to(client):
    """to 格式錯誤（非 YYYY-MM-DD）應回傳 422。"""
    res = client.get("/api/export?from=2026-01-01&to=2026/12/31")
    assert res.status_code == 422
    assert "to" in res.json()["detail"]


def test_export_invalid_date_value_from(client):
    """from 為格式正確但無效日期（如月份 13）應回傳 422。"""
    res = client.get("/api/export?from=2026-13-01&to=2026-12-31")
    assert res.status_code == 422
    assert "from" in res.json()["detail"]


def test_export_invalid_date_value_to(client):
    """to 為格式正確但無效日期（如 2 月 30 日）應回傳 422。"""
    res = client.get("/api/export?from=2026-01-01&to=2026-02-30")
    assert res.status_code == 422
    assert "to" in res.json()["detail"]


def test_export_from_after_to(client):
    """from 晚於 to 應回傳 422。"""
    res = client.get("/api/export?from=2026-12-31&to=2026-01-01")
    assert res.status_code == 422
    assert "開始日期" in res.json()["detail"]


def test_export_same_day(client):
    """from == to（單日）應正常匯出當天資料。"""
    dm.add_transaction("2026-03-15", "E", "餐飲費", "早餐", 80, "早餐", "")
    dm.add_transaction("2026-03-16", "E", "餐飲費", "午餐", 100, "次日", "")

    res = client.get("/api/export?from=2026-03-15&to=2026-03-15")
    assert res.status_code == 200
    rows = _parse_csv(res.content)
    assert len(rows) == 1
    assert rows[0]["明細"] == "早餐"


def test_export_chinese_content(client):
    """含中文的明細與備註應正確編碼。"""
    dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "豆漿油條", "早餐備註")

    res = client.get("/api/export?from=2026-01-01&to=2026-12-31")
    rows = _parse_csv(res.content)
    assert rows[0]["明細"] == "豆漿油條"
    assert rows[0]["備註"] == "早餐備註"
