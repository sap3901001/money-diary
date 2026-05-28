"""
Step 7 功能需求測試 — 統計報表
對應 AT-014 / AT-015

FR-RPT-1  月度收支摘要（monthly_report）
FR-RPT-2  分類佔比報表（category_report）
FR-RPT-3  月度趨勢折線（trend_report）
FR-RPT-4  輸入驗證（日期格式、先後順序、type/level 合法值、預設值）
FR-RPT-5  跨年邊界（月份生成、大範圍資料）
FR-RPT-6  AT-015 報表一致性（與交易 summary 比對）
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
    dm.add_category("E", "餐飲費", "午餐")
    dm.add_category("E", "交通費", "")
    dm.add_category("E", "娛樂費", "")
    dm.add_category("I", "薪資", "")
    dm.add_category("I", "其他收入", "")


@pytest.fixture
def client():
    from app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# FR-RPT-1  月度收支摘要
# ---------------------------------------------------------------------------

class TestFRRPT1_MonthlyReport:

    def test_AT014_empty_month_between_data_months(self, client):
        """AT-014: 有資料月份之間的空月份補 0。"""
        dm.add_transaction("2025-01-10", "I", "薪資", "", 40000, "", "")
        # 2025-02 無資料
        dm.add_transaction("2025-03-05", "E", "餐飲費", "早餐", 300, "", "")
        r = client.get("/api/report/monthly?from=2025-01-01&to=2025-03-31")
        data = r.json()
        feb = next(m for m in data if m["month"] == "2025-02")
        assert feb["income"] == 0
        assert feb["expense"] == 0
        assert feb["net"] == 0

    def test_month_label_format_YYYY_MM(self, client):
        """month 欄位格式為 YYYY-MM。"""
        r = client.get("/api/report/monthly?from=2025-06-01&to=2025-08-31")
        months = [d["month"] for d in r.json()]
        assert months == ["2025-06", "2025-07", "2025-08"]

    def test_income_expense_net_correct_values(self, client):
        """收入、支出、淨額數值正確。"""
        dm.add_transaction("2025-04-01", "I", "薪資", "", 50000, "", "")
        dm.add_transaction("2025-04-10", "E", "餐飲費", "早餐", 2000, "", "")
        dm.add_transaction("2025-04-15", "E", "交通費", "", 500, "", "")
        r = client.get("/api/report/monthly?from=2025-04-01&to=2025-04-30")
        d = r.json()[0]
        assert d["income"] == 50000
        assert d["expense"] == 2500
        assert d["net"] == 47500

    def test_multiple_transactions_same_month_aggregated(self, client):
        """同月多筆交易正確加總（不會分開列出）。"""
        dm.add_transaction("2025-05-01", "E", "餐飲費", "早餐", 100, "", "")
        dm.add_transaction("2025-05-05", "E", "餐飲費", "午餐", 200, "", "")
        dm.add_transaction("2025-05-10", "E", "交通費", "", 300, "", "")
        r = client.get("/api/report/monthly?from=2025-05-01&to=2025-05-31")
        data = r.json()
        assert len(data) == 1  # 只有一個月份條目
        assert data[0]["expense"] == 600

    def test_type_E_income_always_zero(self, client):
        """type=E 時，收入欄恆為 0。"""
        dm.add_transaction("2025-06-01", "I", "薪資", "", 50000, "", "")
        dm.add_transaction("2025-06-05", "E", "餐飲費", "早餐", 1000, "", "")
        r = client.get("/api/report/monthly?from=2025-06-01&to=2025-06-30&type=E")
        d = r.json()[0]
        assert d["income"] == 0
        assert d["expense"] == 1000

    def test_type_I_expense_always_zero(self, client):
        """type=I 時，支出欄恆為 0。"""
        dm.add_transaction("2025-07-01", "I", "薪資", "", 45000, "", "")
        dm.add_transaction("2025-07-05", "E", "交通費", "", 500, "", "")
        r = client.get("/api/report/monthly?from=2025-07-01&to=2025-07-31&type=I")
        d = r.json()[0]
        assert d["income"] == 45000
        assert d["expense"] == 0

    def test_type_all_contains_both(self, client):
        """type=all（預設）時，收入與支出均計入。"""
        dm.add_transaction("2025-08-01", "I", "薪資", "", 30000, "", "")
        dm.add_transaction("2025-08-02", "E", "餐飲費", "早餐", 1000, "", "")
        r = client.get("/api/report/monthly?from=2025-08-01&to=2025-08-31&type=all")
        d = r.json()[0]
        assert d["income"] == 30000
        assert d["expense"] == 1000

    def test_net_positive_when_income_exceeds_expense(self, client):
        dm.add_transaction("2025-09-01", "I", "薪資", "", 60000, "", "")
        dm.add_transaction("2025-09-05", "E", "餐飲費", "早餐", 5000, "", "")
        r = client.get("/api/report/monthly?from=2025-09-01&to=2025-09-30")
        assert r.json()[0]["net"] == 55000

    def test_net_negative_when_expense_exceeds_income(self, client):
        dm.add_transaction("2025-10-01", "I", "其他收入", "", 1000, "", "")
        dm.add_transaction("2025-10-05", "E", "餐飲費", "早餐", 3000, "", "")
        r = client.get("/api/report/monthly?from=2025-10-01&to=2025-10-31")
        assert r.json()[0]["net"] == -2000

    def test_all_months_present_even_zero_data(self, client):
        """整個範圍內無任何資料，仍回傳正確月份數量，全為 0。"""
        r = client.get("/api/report/monthly?from=2025-01-01&to=2025-06-30")
        data = r.json()
        assert len(data) == 6
        assert all(d["income"] == 0 and d["expense"] == 0 for d in data)


# ---------------------------------------------------------------------------
# FR-RPT-2  分類佔比報表
# ---------------------------------------------------------------------------

class TestFRRPT2_CategoryReport:

    def test_default_type_is_expense(self, client):
        """不傳 type 時預設為支出（E）。"""
        dm.add_transaction("2025-01-01", "I", "薪資", "", 50000, "", "")
        dm.add_transaction("2025-01-02", "E", "餐飲費", "早餐", 1000, "", "")
        r = client.get("/api/report/category?from=2025-01-01&to=2025-01-31")
        assert r.json()["total"] == 1000  # 只算支出

    def test_default_level_is_main(self, client):
        """不傳 level 時預設為主類（main）。"""
        dm.add_transaction("2025-02-01", "E", "餐飲費", "早餐", 500, "", "")
        dm.add_transaction("2025-02-02", "E", "餐飲費", "午餐", 800, "", "")
        r = client.get("/api/report/category?from=2025-02-01&to=2025-02-28")
        names = [i["name"] for i in r.json()["items"]]
        # level=main 應只有「餐飲費」而非「餐飲費/早餐」
        assert "餐飲費" in names
        assert "餐飲費/早餐" not in names
        assert "餐飲費/午餐" not in names

    def test_same_main_category_aggregated(self, client):
        """同主類下多筆次類交易在 level=main 時正確加總。"""
        dm.add_transaction("2025-03-01", "E", "餐飲費", "早餐", 300, "", "")
        dm.add_transaction("2025-03-02", "E", "餐飲費", "午餐", 700, "", "")
        r = client.get("/api/report/category?from=2025-03-01&to=2025-03-31&level=main")
        items = r.json()["items"]
        fan_items = [i for i in items if i["name"] == "餐飲費"]
        assert len(fan_items) == 1
        assert fan_items[0]["amount"] == 1000

    def test_sorted_by_amount_desc(self, client):
        """分類按金額由大到小排列。"""
        dm.add_transaction("2025-04-01", "E", "娛樂費", "", 5000, "", "")
        dm.add_transaction("2025-04-02", "E", "交通費", "", 800, "", "")
        dm.add_transaction("2025-04-03", "E", "餐飲費", "早餐", 1200, "", "")
        r = client.get("/api/report/category?from=2025-04-01&to=2025-04-30")
        amounts = [i["amount"] for i in r.json()["items"]]
        assert amounts == sorted(amounts, reverse=True)

    def test_percent_sum_approximately_100(self, client):
        """所有分類百分比總和應接近 100%（浮點誤差容忍 ±0.5）。"""
        dm.add_transaction("2025-05-01", "E", "餐飲費", "早餐", 3000, "", "")
        dm.add_transaction("2025-05-02", "E", "交通費", "", 1000, "", "")
        dm.add_transaction("2025-05-03", "E", "娛樂費", "", 1000, "", "")
        r = client.get("/api/report/category?from=2025-05-01&to=2025-05-31")
        total_pct = sum(i["percent"] for i in r.json()["items"])
        assert abs(total_pct - 100.0) < 0.5

    def test_level_sub_shows_main_slash_sub(self, client):
        """level=sub 時，有次類顯示「主類/次類」格式。"""
        dm.add_transaction("2025-06-01", "E", "餐飲費", "早餐", 400, "", "")
        dm.add_transaction("2025-06-02", "E", "餐飲費", "午餐", 600, "", "")
        r = client.get("/api/report/category?from=2025-06-01&to=2025-06-30&level=sub")
        names = [i["name"] for i in r.json()["items"]]
        assert "餐飲費/早餐" in names
        assert "餐飲費/午餐" in names

    def test_level_sub_no_sub_shows_main_only(self, client):
        """level=sub 時，無次類的分類只顯示主類名稱（不加 /）。"""
        dm.add_transaction("2025-07-01", "E", "交通費", "", 500, "", "")
        r = client.get("/api/report/category?from=2025-07-01&to=2025-07-31&level=sub")
        names = [i["name"] for i in r.json()["items"]]
        assert "交通費" in names
        assert "交通費/" not in names

    def test_sub_level_separate_items_for_each_sub(self, client):
        """level=sub 時同一主類的不同次類各自獨立列出。"""
        dm.add_transaction("2025-08-01", "E", "餐飲費", "早餐", 300, "", "")
        dm.add_transaction("2025-08-02", "E", "餐飲費", "午餐", 700, "", "")
        r = client.get("/api/report/category?from=2025-08-01&to=2025-08-31&level=sub")
        names = [i["name"] for i in r.json()["items"]]
        assert names.count("餐飲費/早餐") == 1
        assert names.count("餐飲費/午餐") == 1

    def test_income_type_excludes_expense(self, client):
        """type=I 時，只計算收入，不含支出。"""
        dm.add_transaction("2025-09-01", "I", "薪資", "", 45000, "", "")
        dm.add_transaction("2025-09-02", "I", "其他收入", "", 5000, "", "")
        dm.add_transaction("2025-09-03", "E", "餐飲費", "早餐", 9999, "", "")
        r = client.get("/api/report/category?from=2025-09-01&to=2025-09-30&type=I")
        data = r.json()
        assert data["total"] == 50000
        names = [i["name"] for i in data["items"]]
        assert "餐飲費" not in names

    def test_empty_range_returns_empty(self, client):
        """指定區間無資料時，items 為空，total 為 0。"""
        r = client.get("/api/report/category?from=2020-01-01&to=2020-12-31")
        assert r.json()["items"] == []
        assert r.json()["total"] == 0

    def test_percent_largest_category_correct(self, client):
        """最大分類百分比數值正確（75%）。"""
        dm.add_transaction("2025-10-01", "E", "餐飲費", "早餐", 3000, "", "")
        dm.add_transaction("2025-10-02", "E", "交通費", "", 1000, "", "")
        r = client.get("/api/report/category?from=2025-10-01&to=2025-10-31")
        first = r.json()["items"][0]
        assert first["name"] == "餐飲費"
        assert first["percent"] == 75.0


# ---------------------------------------------------------------------------
# FR-RPT-3  月度趨勢折線
# ---------------------------------------------------------------------------

class TestFRRPT3_TrendReport:

    def test_AT014_empty_months_filled_zero(self, client):
        """AT-014: 趨勢圖空月份補 0。"""
        dm.add_transaction("2025-01-01", "I", "薪資", "", 40000, "", "")
        # 2025-02 空月
        dm.add_transaction("2025-03-10", "E", "交通費", "", 500, "", "")
        r = client.get("/api/report/trend?from=2025-01-01&to=2025-03-31")
        data = r.json()
        feb = next(m for m in data if m["month"] == "2025-02")
        assert feb["income"] == 0
        assert feb["expense"] == 0

    def test_category_main_filter_isolates_category(self, client):
        """category_main 篩選只計算指定主類的金額。"""
        dm.add_transaction("2025-04-01", "E", "餐飲費", "早餐", 1000, "", "")
        dm.add_transaction("2025-04-05", "E", "交通費", "", 400, "", "")
        dm.add_transaction("2025-04-10", "E", "娛樂費", "", 2000, "", "")
        r = client.get("/api/report/trend?from=2025-04-01&to=2025-04-30&category_main=餐飲費")
        assert r.json()[0]["expense"] == 1000

    def test_category_main_filter_excludes_others(self, client):
        """category_main 篩選後，其他主類金額不計入。"""
        dm.add_transaction("2025-05-01", "E", "餐飲費", "早餐", 1000, "", "")
        dm.add_transaction("2025-05-05", "E", "交通費", "", 999, "", "")
        r = client.get("/api/report/trend?from=2025-05-01&to=2025-05-31&category_main=餐飲費")
        assert r.json()[0]["expense"] == 1000  # 不含 999

    def test_no_category_filter_includes_all(self, client):
        """不傳 category_main 時，所有分類均計入。"""
        dm.add_transaction("2025-06-01", "E", "餐飲費", "早餐", 1000, "", "")
        dm.add_transaction("2025-06-02", "E", "交通費", "", 400, "", "")
        r = client.get("/api/report/trend?from=2025-06-01&to=2025-06-30")
        assert r.json()[0]["expense"] == 1400

    def test_type_E_filter(self, client):
        """type=E 時，income 恆為 0。"""
        dm.add_transaction("2025-07-01", "I", "薪資", "", 50000, "", "")
        dm.add_transaction("2025-07-05", "E", "餐飲費", "早餐", 1000, "", "")
        r = client.get("/api/report/trend?from=2025-07-01&to=2025-07-31&type=E")
        d = r.json()[0]
        assert d["income"] == 0
        assert d["expense"] == 1000

    def test_type_I_filter(self, client):
        """type=I 時，expense 恆為 0。"""
        dm.add_transaction("2025-08-01", "I", "薪資", "", 50000, "", "")
        dm.add_transaction("2025-08-05", "E", "交通費", "", 300, "", "")
        r = client.get("/api/report/trend?from=2025-08-01&to=2025-08-31&type=I")
        d = r.json()[0]
        assert d["income"] == 50000
        assert d["expense"] == 0

    def test_matches_monthly_when_no_filter(self, client):
        """無額外篩選時，trend 與 monthly 相同參數結果完全一致。"""
        dm.add_transaction("2025-09-01", "I", "薪資", "", 40000, "", "")
        dm.add_transaction("2025-09-05", "E", "餐飲費", "早餐", 2000, "", "")
        dm.add_transaction("2025-10-01", "E", "交通費", "", 800, "", "")
        trend_r  = client.get("/api/report/trend?from=2025-09-01&to=2025-10-31")
        monthly_r = client.get("/api/report/monthly?from=2025-09-01&to=2025-10-31")
        assert trend_r.json() == monthly_r.json()

    def test_category_filter_with_income_category(self, client):
        """category_main 篩選到收入分類，只顯示該分類收入。"""
        dm.add_transaction("2025-11-01", "I", "薪資", "", 45000, "", "")
        dm.add_transaction("2025-11-02", "I", "其他收入", "", 5000, "", "")
        r = client.get("/api/report/trend?from=2025-11-01&to=2025-11-30&category_main=薪資")
        d = r.json()[0]
        assert d["income"] == 45000
        assert d["expense"] == 0


# ---------------------------------------------------------------------------
# FR-RPT-4  輸入驗證
# ---------------------------------------------------------------------------

class TestFRRPT4_InputValidation:

    # ── from/to 預設值 ──
    def test_monthly_no_params_defaults_12_months(self, client):
        """不傳 from/to，回傳近 12 個月（12 筆）。"""
        r = client.get("/api/report/monthly")
        assert r.status_code == 200
        assert len(r.json()) == 12

    def test_category_no_params_defaults_12_months(self, client):
        """category 不傳 from/to 應正常回傳（無 422）。"""
        r = client.get("/api/report/category")
        assert r.status_code == 200

    def test_trend_no_params_defaults_12_months(self, client):
        r = client.get("/api/report/trend")
        assert r.status_code == 200
        assert len(r.json()) == 12

    # ── 日期格式錯誤 ──
    def test_monthly_invalid_from_format_returns_422(self, client):
        r = client.get("/api/report/monthly?from=2025-1-1&to=2025-12-31")
        assert r.status_code == 422

    def test_monthly_invalid_to_format_returns_422(self, client):
        r = client.get("/api/report/monthly?from=2025-01-01&to=25-12-31")
        assert r.status_code == 422

    def test_category_invalid_from_format_returns_422(self, client):
        r = client.get("/api/report/category?from=20250101&to=2025-12-31")
        assert r.status_code == 422

    def test_trend_invalid_date_format_returns_422(self, client):
        r = client.get("/api/report/trend?from=2025/01/01&to=2025-12-31")
        assert r.status_code == 422

    # ── 無效日期值（格式正確但日期不合法）──
    def test_monthly_invalid_date_value_month13_returns_422(self, client):
        r = client.get("/api/report/monthly?from=2025-13-01&to=2025-12-31")
        assert r.status_code == 422

    def test_monthly_invalid_date_value_feb30_returns_422(self, client):
        r = client.get("/api/report/monthly?from=2025-01-01&to=2025-02-30")
        assert r.status_code == 422

    # ── from > to ──
    def test_monthly_from_after_to_returns_422(self, client):
        r = client.get("/api/report/monthly?from=2025-12-01&to=2025-01-31")
        assert r.status_code == 422

    def test_category_from_after_to_returns_422(self, client):
        r = client.get("/api/report/category?from=2025-06-01&to=2025-01-31")
        assert r.status_code == 422

    def test_trend_from_after_to_returns_422(self, client):
        r = client.get("/api/report/trend?from=2025-12-01&to=2025-06-30")
        assert r.status_code == 422

    # ── from == to（合法，單日）──
    def test_monthly_from_equals_to_valid(self, client):
        r = client.get("/api/report/monthly?from=2025-06-15&to=2025-06-15")
        assert r.status_code == 200
        assert len(r.json()) == 1

    # ── type 無效值 ──
    def test_monthly_invalid_type_returns_422(self, client):
        r = client.get("/api/report/monthly?from=2025-01-01&to=2025-12-31&type=X")
        assert r.status_code == 422

    def test_category_invalid_type_all_returns_422(self, client):
        """category 的 type 不接受 'all'，只接受 E/I。"""
        r = client.get("/api/report/category?from=2025-01-01&to=2025-12-31&type=all")
        assert r.status_code == 422

    def test_category_invalid_type_returns_422(self, client):
        r = client.get("/api/report/category?from=2025-01-01&to=2025-12-31&type=Z")
        assert r.status_code == 422

    def test_trend_invalid_type_returns_422(self, client):
        r = client.get("/api/report/trend?from=2025-01-01&to=2025-12-31&type=EI")
        assert r.status_code == 422

    # ── level 無效值 ──
    def test_category_invalid_level_returns_422(self, client):
        r = client.get("/api/report/category?from=2025-01-01&to=2025-12-31&level=detail")
        assert r.status_code == 422

    def test_category_invalid_level_number_returns_422(self, client):
        r = client.get("/api/report/category?from=2025-01-01&to=2025-12-31&level=1")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# FR-RPT-5  跨年邊界與大範圍
# ---------------------------------------------------------------------------

class TestFRRPT5_CrossYearBoundary:

    def test_AT014_cross_year_months_generated(self, client):
        """AT-014: 跨年度月份正確生成，無遺漏。"""
        r = client.get("/api/report/monthly?from=2024-11-01&to=2025-02-28")
        months = [d["month"] for d in r.json()]
        assert months == ["2024-11", "2024-12", "2025-01", "2025-02"]

    def test_cross_year_data_in_correct_month(self, client):
        """跨年資料歸屬到正確月份。"""
        dm.add_transaction("2024-12-31", "I", "薪資", "", 30000, "", "")
        dm.add_transaction("2025-01-01", "E", "餐飲費", "早餐", 100, "", "")
        r = client.get("/api/report/monthly?from=2024-12-01&to=2025-01-31")
        data = r.json()
        dec = next(m for m in data if m["month"] == "2024-12")
        jan = next(m for m in data if m["month"] == "2025-01")
        assert dec["income"] == 30000
        assert jan["expense"] == 100

    def test_single_month_range(self, client):
        """from 和 to 在同一個月，只回傳 1 筆月份。"""
        dm.add_transaction("2025-03-15", "E", "交通費", "", 200, "", "")
        r = client.get("/api/report/monthly?from=2025-03-01&to=2025-03-31")
        assert len(r.json()) == 1
        assert r.json()[0]["month"] == "2025-03"

    def test_three_year_span_month_count(self, client):
        """三年範圍（2023-01 ~ 2025-12）應產生 36 個月。"""
        r = client.get("/api/report/monthly?from=2023-01-01&to=2025-12-31")
        assert len(r.json()) == 36

    def test_category_cross_year_aggregates_correctly(self, client):
        """跨年分類報表只計算指定範圍的資料。"""
        dm.add_transaction("2024-06-01", "E", "餐飲費", "早餐", 9999, "", "")  # 範圍外
        dm.add_transaction("2025-01-01", "E", "餐飲費", "早餐", 1000, "", "")  # 範圍內
        r = client.get("/api/report/category?from=2025-01-01&to=2025-12-31")
        assert r.json()["total"] == 1000

    def test_trend_cross_year_empty_months_filled(self, client):
        """趨勢圖跨年空月補 0。"""
        dm.add_transaction("2024-12-01", "I", "薪資", "", 40000, "", "")
        dm.add_transaction("2025-02-01", "I", "薪資", "", 40000, "", "")
        r = client.get("/api/report/trend?from=2024-12-01&to=2025-02-28")
        data = r.json()
        jan = next(m for m in data if m["month"] == "2025-01")
        assert jan["income"] == 0
        assert jan["expense"] == 0


# ---------------------------------------------------------------------------
# FR-RPT-6  AT-015 報表一致性
# ---------------------------------------------------------------------------

class TestFRRPT6_AT015_Consistency:

    def test_AT015_monthly_income_matches_transaction_summary(self, client):
        """AT-015: monthly income 加總 == transactions summary total_income。"""
        dm.add_transaction("2025-01-01", "I", "薪資", "", 40000, "", "")
        dm.add_transaction("2025-02-01", "I", "薪資", "", 42000, "", "")
        dm.add_transaction("2025-01-05", "E", "餐飲費", "早餐", 1000, "", "")

        monthly = client.get("/api/report/monthly?from=2025-01-01&to=2025-02-28").json()
        txn = client.get("/api/transactions?from=2025-01-01&to=2025-02-28&size=500").json()

        report_income = sum(m["income"] for m in monthly)
        assert report_income == txn["summary"]["total_income"]

    def test_AT015_monthly_expense_matches_transaction_summary(self, client):
        """AT-015: monthly expense 加總 == transactions summary total_expense。"""
        dm.add_transaction("2025-03-01", "E", "餐飲費", "早餐", 800, "", "")
        dm.add_transaction("2025-03-05", "E", "交通費", "", 300, "", "")
        dm.add_transaction("2025-04-01", "E", "娛樂費", "", 1500, "", "")

        monthly = client.get("/api/report/monthly?from=2025-03-01&to=2025-04-30").json()
        txn = client.get("/api/transactions?from=2025-03-01&to=2025-04-30&size=500").json()

        report_expense = sum(m["expense"] for m in monthly)
        assert report_expense == txn["summary"]["total_expense"]

    def test_AT015_monthly_net_matches_transaction_summary(self, client):
        """AT-015: monthly net 加總 == transactions summary net。"""
        dm.add_transaction("2025-05-01", "I", "薪資", "", 50000, "", "")
        dm.add_transaction("2025-05-10", "E", "餐飲費", "早餐", 3000, "", "")
        dm.add_transaction("2025-06-01", "I", "其他收入", "", 10000, "", "")
        dm.add_transaction("2025-06-05", "E", "交通費", "", 500, "", "")

        monthly = client.get("/api/report/monthly?from=2025-05-01&to=2025-06-30").json()
        txn = client.get("/api/transactions?from=2025-05-01&to=2025-06-30&size=500").json()

        report_net = sum(m["net"] for m in monthly)
        assert report_net == txn["summary"]["net"]

    def test_AT015_category_total_E_matches_summary_expense(self, client):
        """AT-015: category(type=E).total == transactions summary total_expense。"""
        dm.add_transaction("2025-07-01", "E", "餐飲費", "早餐", 1200, "", "")
        dm.add_transaction("2025-07-05", "E", "交通費", "", 600, "", "")
        dm.add_transaction("2025-07-10", "I", "薪資", "", 45000, "", "")

        cat = client.get("/api/report/category?from=2025-07-01&to=2025-07-31&type=E").json()
        txn = client.get("/api/transactions?from=2025-07-01&to=2025-07-31&size=500").json()

        assert cat["total"] == txn["summary"]["total_expense"]

    def test_AT015_category_total_I_matches_summary_income(self, client):
        """AT-015: category(type=I).total == transactions summary total_income。"""
        dm.add_transaction("2025-08-01", "I", "薪資", "", 45000, "", "")
        dm.add_transaction("2025-08-02", "I", "其他收入", "", 5000, "", "")
        dm.add_transaction("2025-08-03", "E", "餐飲費", "早餐", 999, "", "")

        cat = client.get("/api/report/category?from=2025-08-01&to=2025-08-31&type=I").json()
        txn = client.get("/api/transactions?from=2025-08-01&to=2025-08-31&size=500").json()

        assert cat["total"] == txn["summary"]["total_income"]

    def test_AT015_trend_equals_monthly_without_filter(self, client):
        """AT-015: trend（無 category_main）== monthly，相同日期範圍結果完全一致。"""
        dm.add_transaction("2025-09-01", "I", "薪資", "", 40000, "", "")
        dm.add_transaction("2025-09-05", "E", "餐飲費", "早餐", 2000, "", "")
        dm.add_transaction("2025-10-01", "E", "交通費", "", 300, "", "")
        dm.add_transaction("2025-10-15", "I", "其他收入", "", 8000, "", "")

        trend  = client.get("/api/report/trend?from=2025-09-01&to=2025-10-31").json()
        monthly = client.get("/api/report/monthly?from=2025-09-01&to=2025-10-31").json()
        assert trend == monthly

    def test_AT015_category_sub_total_equals_main_total(self, client):
        """AT-015: level=sub 的 total 等於 level=main 的 total（同類型同範圍）。"""
        dm.add_transaction("2025-11-01", "E", "餐飲費", "早餐", 500, "", "")
        dm.add_transaction("2025-11-02", "E", "餐飲費", "午餐", 700, "", "")
        dm.add_transaction("2025-11-03", "E", "交通費", "", 400, "", "")

        main_r = client.get("/api/report/category?from=2025-11-01&to=2025-11-30&level=main").json()
        sub_r  = client.get("/api/report/category?from=2025-11-01&to=2025-11-30&level=sub").json()
        assert main_r["total"] == sub_r["total"]
