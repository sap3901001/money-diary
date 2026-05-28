"""
tests/api/test_report_api.py — 報表 API 測試

涵蓋：
  GET /api/report/monthly  — 月度收支
  GET /api/report/category — 分類佔比
  GET /api/report/trend    — 月度趨勢

AT-014 空月補 0
AT-015 報表與交易摘要一致
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import data_manager as dm


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_data(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DATA_DIR",       tmp_path)
    monkeypatch.setattr(dm, "MAIN_DB",        tmp_path / "main_db.csv")
    monkeypatch.setattr(dm, "CATEGORIES_CSV", tmp_path / "categories.csv")
    dm.init_data_files()
    dm.add_category("E", "餐飲費", "早餐")
    dm.add_category("E", "交通費", "")
    dm.add_category("I", "薪資", "")
    dm.add_category("I", "其他收入", "")


@pytest.fixture
def client():
    from app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# /api/report/monthly
# ---------------------------------------------------------------------------

class TestMonthlyReport:

    def test_returns_list(self, client):
        r = client.get("/api/report/monthly?from=2025-01-01&to=2025-03-31")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 3

    def test_AT014_empty_month_filled_zero(self, client):
        """AT-014: 範圍內空月份補 0。"""
        dm.add_transaction("2025-01-10", "I", "薪資", "", 30000, "", "")
        dm.add_transaction("2025-03-10", "E", "餐飲費", "早餐", 500, "", "")
        r = client.get("/api/report/monthly?from=2025-01-01&to=2025-03-31")
        data = r.json()
        feb = next(m for m in data if m["month"] == "2025-02")
        assert feb["income"] == 0
        assert feb["expense"] == 0
        assert feb["net"] == 0

    def test_month_field_format(self, client):
        r = client.get("/api/report/monthly?from=2025-06-01&to=2025-06-30")
        data = r.json()
        assert data[0]["month"] == "2025-06"

    def test_income_expense_net_correct(self, client):
        dm.add_transaction("2025-04-01", "I", "薪資", "", 50000, "", "")
        dm.add_transaction("2025-04-05", "E", "餐飲費", "早餐", 3000, "", "")
        r = client.get("/api/report/monthly?from=2025-04-01&to=2025-04-30")
        data = r.json()
        assert data[0]["income"] == 50000
        assert data[0]["expense"] == 3000
        assert data[0]["net"] == 47000

    def test_type_filter_expense(self, client):
        dm.add_transaction("2025-05-01", "I", "薪資", "", 50000, "", "")
        dm.add_transaction("2025-05-05", "E", "交通費", "", 1000, "", "")
        r = client.get("/api/report/monthly?from=2025-05-01&to=2025-05-31&type=E")
        data = r.json()
        assert data[0]["income"] == 0
        assert data[0]["expense"] == 1000

    def test_type_filter_income(self, client):
        dm.add_transaction("2025-05-01", "I", "薪資", "", 50000, "", "")
        dm.add_transaction("2025-05-05", "E", "交通費", "", 1000, "", "")
        r = client.get("/api/report/monthly?from=2025-05-01&to=2025-05-31&type=I")
        data = r.json()
        assert data[0]["income"] == 50000
        assert data[0]["expense"] == 0

    def test_invalid_type_returns_422(self, client):
        r = client.get("/api/report/monthly?from=2025-01-01&to=2025-01-31&type=X")
        assert r.status_code == 422

    def test_invalid_date_format_returns_422(self, client):
        r = client.get("/api/report/monthly?from=2025-1-1&to=2025-01-31")
        assert r.status_code == 422

    def test_from_after_to_returns_422(self, client):
        r = client.get("/api/report/monthly?from=2025-06-01&to=2025-01-31")
        assert r.status_code == 422

    def test_default_params_returns_12_months(self, client):
        """不傳 from/to 應回傳 12 個月（近 12 個月預設）。"""
        r = client.get("/api/report/monthly")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 12

    def test_AT015_monthly_matches_transaction_summary(self, client):
        """AT-015: 月度報表加總與交易 summary 一致。"""
        dm.add_transaction("2025-07-01", "I", "薪資", "", 40000, "", "")
        dm.add_transaction("2025-07-05", "E", "餐飲費", "早餐", 2000, "", "")
        dm.add_transaction("2025-07-10", "E", "交通費", "", 500, "", "")

        report_r = client.get("/api/report/monthly?from=2025-07-01&to=2025-07-31")
        report = report_r.json()[0]

        txn_r = client.get("/api/transactions?from=2025-07-01&to=2025-07-31&size=500")
        summary = txn_r.json()["summary"]

        assert report["income"]  == summary["total_income"]
        assert report["expense"] == summary["total_expense"]
        assert report["net"]     == summary["net"]


# ---------------------------------------------------------------------------
# /api/report/category
# ---------------------------------------------------------------------------

class TestCategoryReport:

    def test_returns_items_and_total(self, client):
        dm.add_transaction("2025-01-01", "E", "餐飲費", "早餐", 1000, "", "")
        r = client.get("/api/report/category?from=2025-01-01&to=2025-01-31")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data

    def test_empty_returns_empty_items(self, client):
        r = client.get("/api/report/category?from=2025-01-01&to=2025-01-31")
        data = r.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_default_type_is_expense(self, client):
        """不傳 type 預設為 E（支出）。"""
        dm.add_transaction("2025-02-01", "I", "薪資", "", 50000, "", "")
        dm.add_transaction("2025-02-05", "E", "餐飲費", "早餐", 1000, "", "")
        r = client.get("/api/report/category?from=2025-02-01&to=2025-02-28")
        data = r.json()
        assert data["total"] == 1000

    def test_sorted_by_amount_desc(self, client):
        dm.add_transaction("2025-03-01", "E", "交通費", "", 500, "", "")
        dm.add_transaction("2025-03-02", "E", "餐飲費", "早餐", 3000, "", "")
        r = client.get("/api/report/category?from=2025-03-01&to=2025-03-31")
        items = r.json()["items"]
        assert items[0]["name"] == "餐飲費"
        assert items[0]["amount"] == 3000

    def test_percent_present(self, client):
        dm.add_transaction("2025-04-01", "E", "餐飲費", "早餐", 3000, "", "")
        dm.add_transaction("2025-04-02", "E", "交通費", "", 1000, "", "")
        r = client.get("/api/report/category?from=2025-04-01&to=2025-04-30")
        items = r.json()["items"]
        for item in items:
            assert "percent" in item
            assert item["percent"] >= 0

    def test_level_sub(self, client):
        dm.add_category("E", "餐飲費", "午餐")
        dm.add_transaction("2025-05-01", "E", "餐飲費", "早餐", 1000, "", "")
        dm.add_transaction("2025-05-02", "E", "餐飲費", "午餐", 1500, "", "")
        r = client.get("/api/report/category?from=2025-05-01&to=2025-05-31&level=sub")
        names = [i["name"] for i in r.json()["items"]]
        assert "餐飲費/午餐" in names
        assert "餐飲費/早餐" in names

    def test_income_type(self, client):
        dm.add_transaction("2025-06-01", "I", "薪資", "", 45000, "", "")
        dm.add_transaction("2025-06-02", "I", "其他收入", "", 5000, "", "")
        r = client.get("/api/report/category?from=2025-06-01&to=2025-06-30&type=I")
        data = r.json()
        assert data["total"] == 50000
        assert data["items"][0]["name"] == "薪資"

    def test_invalid_type_returns_422(self, client):
        r = client.get("/api/report/category?from=2025-01-01&to=2025-01-31&type=all")
        assert r.status_code == 422

    def test_invalid_level_returns_422(self, client):
        r = client.get("/api/report/category?from=2025-01-01&to=2025-01-31&level=detail")
        assert r.status_code == 422

    def test_AT015_category_total_matches_summary(self, client):
        """AT-015: 分類報表 total 與交易 summary 一致。"""
        dm.add_transaction("2025-07-01", "E", "餐飲費", "早餐", 2000, "", "")
        dm.add_transaction("2025-07-05", "E", "交通費", "", 800, "", "")
        cat_r = client.get("/api/report/category?from=2025-07-01&to=2025-07-31&type=E")
        txn_r = client.get("/api/transactions?from=2025-07-01&to=2025-07-31&type=E&size=500")
        assert cat_r.json()["total"] == txn_r.json()["summary"]["total_expense"]


# ---------------------------------------------------------------------------
# /api/report/trend
# ---------------------------------------------------------------------------

class TestTrendReport:

    def test_returns_list(self, client):
        r = client.get("/api/report/trend?from=2025-01-01&to=2025-03-31")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        assert len(r.json()) == 3

    def test_AT014_empty_month_filled_zero(self, client):
        """AT-014: trend 空月補 0。"""
        dm.add_transaction("2025-01-01", "I", "薪資", "", 40000, "", "")
        # 2025-02 空月
        dm.add_transaction("2025-03-10", "E", "交通費", "", 300, "", "")
        r = client.get("/api/report/trend?from=2025-01-01&to=2025-03-31")
        data = r.json()
        feb = next(m for m in data if m["month"] == "2025-02")
        assert feb["income"] == 0
        assert feb["expense"] == 0

    def test_category_main_filter(self, client):
        dm.add_transaction("2025-04-01", "E", "餐飲費", "早餐", 1000, "", "")
        dm.add_transaction("2025-04-05", "E", "交通費", "", 400, "", "")
        r = client.get("/api/report/trend?from=2025-04-01&to=2025-04-30&category_main=餐飲費")
        data = r.json()
        assert data[0]["expense"] == 1000

    def test_type_all(self, client):
        dm.add_transaction("2025-05-01", "I", "薪資", "", 50000, "", "")
        dm.add_transaction("2025-05-05", "E", "餐飲費", "早餐", 1500, "", "")
        r = client.get("/api/report/trend?from=2025-05-01&to=2025-05-31&type=all")
        data = r.json()
        assert data[0]["income"] == 50000
        assert data[0]["expense"] == 1500

    def test_invalid_type_returns_422(self, client):
        r = client.get("/api/report/trend?from=2025-01-01&to=2025-01-31&type=X")
        assert r.status_code == 422

    def test_default_params_returns_12_months(self, client):
        r = client.get("/api/report/trend")
        assert r.status_code == 200
        assert len(r.json()) == 12

    def test_AT015_trend_matches_monthly(self, client):
        """AT-015: trend 與 monthly 在相同參數下結果一致。"""
        dm.add_transaction("2025-08-01", "I", "薪資", "", 30000, "", "")
        dm.add_transaction("2025-08-05", "E", "交通費", "", 700, "", "")
        trend_r = client.get("/api/report/trend?from=2025-08-01&to=2025-08-31")
        monthly_r = client.get("/api/report/monthly?from=2025-08-01&to=2025-08-31")
        assert trend_r.json() == monthly_r.json()
