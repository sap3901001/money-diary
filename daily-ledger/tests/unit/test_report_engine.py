"""
tests/unit/test_report_engine.py — report_engine 單元測試

測試函式：
  monthly_report  — 月度收支聚合、空月補 0、type 篩選
  category_report — 分類佔比、level=main/sub、百分比計算
  trend_report    — 月度趨勢、category_main 篩選
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import data_manager as dm
import report_engine as re_


# ---------------------------------------------------------------------------
# Fixture
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


# ---------------------------------------------------------------------------
# _month_range helper
# ---------------------------------------------------------------------------

def test_month_range_single():
    assert re_._month_range("2025-03-01", "2025-03-31") == ["2025-03"]


def test_month_range_cross_year():
    months = re_._month_range("2024-11-01", "2025-02-28")
    assert months == ["2024-11", "2024-12", "2025-01", "2025-02"]


def test_month_range_same_month():
    assert re_._month_range("2025-06-01", "2025-06-30") == ["2025-06"]


# ---------------------------------------------------------------------------
# monthly_report
# ---------------------------------------------------------------------------

def test_monthly_empty_range_returns_zeroes():
    """範圍內無資料，每月 income/expense/net 均為 0。"""
    result = re_.monthly_report("2025-01-01", "2025-03-31")
    assert len(result) == 3
    for row in result:
        assert row["income"] == 0
        assert row["expense"] == 0
        assert row["net"] == 0


def test_monthly_fills_empty_months():
    """2025-01 和 2025-03 有資料，2025-02 應補 0。"""
    dm.add_transaction("2025-01-05", "I", "薪資", "", 30000, "", "")
    dm.add_transaction("2025-03-10", "E", "餐飲費", "早餐", 200, "", "")
    result = re_.monthly_report("2025-01-01", "2025-03-31")
    assert len(result) == 3
    assert result[0]["month"] == "2025-01"
    assert result[0]["income"] == 30000
    assert result[1]["month"] == "2025-02"
    assert result[1]["income"] == 0
    assert result[1]["expense"] == 0
    assert result[2]["month"] == "2025-03"
    assert result[2]["expense"] == 200


def test_monthly_net_calculation():
    dm.add_transaction("2025-05-01", "I", "薪資", "", 50000, "", "")
    dm.add_transaction("2025-05-15", "E", "餐飲費", "早餐", 3000, "", "")
    result = re_.monthly_report("2025-05-01", "2025-05-31")
    assert len(result) == 1
    r = result[0]
    assert r["income"] == 50000
    assert r["expense"] == 3000
    assert r["net"] == 47000


def test_monthly_type_filter_expense_only():
    """type_=E 時，income 欄應為 0。"""
    dm.add_transaction("2025-06-01", "I", "薪資", "", 50000, "", "")
    dm.add_transaction("2025-06-05", "E", "餐飲費", "早餐", 1000, "", "")
    result = re_.monthly_report("2025-06-01", "2025-06-30", type_="E")
    assert result[0]["income"] == 0
    assert result[0]["expense"] == 1000


def test_monthly_type_filter_income_only():
    """type_=I 時，expense 欄應為 0。"""
    dm.add_transaction("2025-07-01", "I", "薪資", "", 45000, "", "")
    dm.add_transaction("2025-07-05", "E", "交通費", "", 500, "", "")
    result = re_.monthly_report("2025-07-01", "2025-07-31", type_="I")
    assert result[0]["income"] == 45000
    assert result[0]["expense"] == 0


def test_monthly_multiple_transactions_same_month():
    """同月多筆正確加總。"""
    dm.add_transaction("2025-08-01", "E", "餐飲費", "早餐", 100, "", "")
    dm.add_transaction("2025-08-05", "E", "交通費", "", 300, "", "")
    dm.add_transaction("2025-08-10", "E", "餐飲費", "早餐", 200, "", "")
    result = re_.monthly_report("2025-08-01", "2025-08-31")
    assert result[0]["expense"] == 600


def test_monthly_cross_year():
    """跨年度月份正確生成。"""
    dm.add_transaction("2024-12-01", "I", "薪資", "", 40000, "", "")
    dm.add_transaction("2025-01-01", "E", "餐飲費", "早餐", 500, "", "")
    result = re_.monthly_report("2024-12-01", "2025-01-31")
    assert len(result) == 2
    assert result[0]["month"] == "2024-12"
    assert result[1]["month"] == "2025-01"


# ---------------------------------------------------------------------------
# category_report
# ---------------------------------------------------------------------------

def test_category_empty_returns_empty_items():
    result = re_.category_report("2025-01-01", "2025-12-31", type_="E")
    assert result["items"] == []
    assert result["total"] == 0


def test_category_main_level():
    dm.add_transaction("2025-01-01", "E", "餐飲費", "早餐", 3000, "", "")
    dm.add_transaction("2025-01-02", "E", "交通費", "", 1000, "", "")
    result = re_.category_report("2025-01-01", "2025-01-31", type_="E", level="main")
    assert result["total"] == 4000
    names = [i["name"] for i in result["items"]]
    assert "餐飲費" in names
    assert "交通費" in names


def test_category_sorted_by_amount_desc():
    dm.add_transaction("2025-02-01", "E", "交通費", "", 500, "", "")
    dm.add_transaction("2025-02-02", "E", "餐飲費", "早餐", 3000, "", "")
    result = re_.category_report("2025-02-01", "2025-02-28", type_="E")
    assert result["items"][0]["name"] == "餐飲費"
    assert result["items"][1]["name"] == "交通費"


def test_category_percent_sum_100():
    dm.add_transaction("2025-03-01", "E", "餐飲費", "早餐", 3000, "", "")
    dm.add_transaction("2025-03-02", "E", "交通費", "", 1000, "", "")
    result = re_.category_report("2025-03-01", "2025-03-31", type_="E")
    total_pct = sum(i["percent"] for i in result["items"])
    assert abs(total_pct - 100.0) < 0.2  # 浮點誤差容忍


def test_category_sub_level():
    """level=sub 時，有次類顯示 主類/次類，無次類顯示 主類。"""
    dm.add_category("E", "餐飲費", "午餐")
    dm.add_transaction("2025-04-01", "E", "餐飲費", "早餐", 1000, "", "")
    dm.add_transaction("2025-04-02", "E", "餐飲費", "午餐", 1500, "", "")
    dm.add_transaction("2025-04-03", "E", "交通費", "", 500, "", "")
    result = re_.category_report("2025-04-01", "2025-04-30", type_="E", level="sub")
    names = [i["name"] for i in result["items"]]
    assert "餐飲費/早餐" in names
    assert "餐飲費/午餐" in names
    assert "交通費" in names  # 無次類，只顯示主類


def test_category_income_type():
    dm.add_transaction("2025-05-01", "I", "薪資", "", 45000, "", "")
    dm.add_transaction("2025-05-01", "I", "其他收入", "", 5000, "", "")
    result = re_.category_report("2025-05-01", "2025-05-31", type_="I")
    assert result["total"] == 50000
    assert result["items"][0]["name"] == "薪資"


def test_category_excludes_other_type():
    """type_=E 時不含收入。"""
    dm.add_transaction("2025-06-01", "I", "薪資", "", 50000, "", "")
    dm.add_transaction("2025-06-02", "E", "餐飲費", "早餐", 1000, "", "")
    result = re_.category_report("2025-06-01", "2025-06-30", type_="E")
    assert result["total"] == 1000


# ---------------------------------------------------------------------------
# trend_report
# ---------------------------------------------------------------------------

def test_trend_empty_fills_zeroes():
    result = re_.trend_report("2025-01-01", "2025-02-28")
    assert len(result) == 2
    for r in result:
        assert r["income"] == 0
        assert r["expense"] == 0


def test_trend_basic():
    dm.add_transaction("2025-01-15", "I", "薪資", "", 40000, "", "")
    dm.add_transaction("2025-02-10", "E", "餐飲費", "早餐", 1500, "", "")
    result = re_.trend_report("2025-01-01", "2025-02-28")
    assert result[0]["income"] == 40000
    assert result[1]["expense"] == 1500


def test_trend_category_main_filter():
    """category_main 篩選只計算指定主類。"""
    dm.add_transaction("2025-03-01", "E", "餐飲費", "早餐", 1000, "", "")
    dm.add_transaction("2025-03-05", "E", "交通費", "", 500, "", "")
    result = re_.trend_report("2025-03-01", "2025-03-31", category_main="餐飲費")
    assert result[0]["expense"] == 1000


def test_trend_category_main_excludes_others():
    dm.add_transaction("2025-04-01", "E", "餐飲費", "早餐", 2000, "", "")
    dm.add_transaction("2025-04-02", "E", "交通費", "", 300, "", "")
    result = re_.trend_report("2025-04-01", "2025-04-30", category_main="交通費")
    assert result[0]["expense"] == 300


def test_trend_type_filter():
    dm.add_transaction("2025-05-01", "I", "薪資", "", 50000, "", "")
    dm.add_transaction("2025-05-05", "E", "餐飲費", "早餐", 1000, "", "")
    result = re_.trend_report("2025-05-01", "2025-05-31", type_="E")
    assert result[0]["expense"] == 1000
    assert result[0]["income"] == 0
