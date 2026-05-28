"""
Step 1 驗收測試：data_manager.py 核心邏輯
"""
import os
import sys
import pytest
from pathlib import Path

# 讓測試找到 daily_ledger 的模組
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import data_manager as dm


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    """每個測試使用獨立暫存目錄，不汙染真實資料。"""
    monkeypatch.setattr(dm, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dm, "MAIN_DB", tmp_path / "main_db.csv")
    monkeypatch.setattr(dm, "CATEGORIES_CSV", tmp_path / "categories.csv")
    dm.init_data_files()


# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------

def test_init_creates_files():
    assert dm.MAIN_DB.exists()
    assert dm.CATEGORIES_CSV.exists()


# ---------------------------------------------------------------------------
# 分類
# ---------------------------------------------------------------------------

def test_add_and_get_category():
    dm.add_category("E", "餐飲費", "早餐")
    cats = dm.get_categories()
    assert len(cats) == 1
    assert cats[0]["主類"] == "餐飲費"


def test_add_duplicate_category_raises():
    dm.add_category("E", "餐飲費", "早餐")
    with pytest.raises(ValueError, match="duplicate"):
        dm.add_category("E", "餐飲費", "早餐")


def test_delete_category():
    dm.add_category("E", "餐飲費", "早餐")
    dm.delete_category("E", "餐飲費", "早餐")
    assert dm.get_categories() == []


def test_delete_category_in_use_raises():
    dm.add_category("E", "餐飲費", "早餐")
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 100, "豆漿", "")
    with pytest.raises(ValueError, match="in_use"):
        dm.delete_category("E", "餐飲費", "早餐")


def test_get_categories_type_filter():
    dm.add_category("E", "餐飲費", "早餐")
    dm.add_category("I", "薪資", "")
    assert len(dm.get_categories(type_filter="E")) == 1
    assert len(dm.get_categories(type_filter="I")) == 1


def test_get_categories_include_count():
    dm.add_category("E", "餐飲費", "早餐")
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 50, "早餐", "")
    dm.add_transaction("2026-01-02", "E", "餐飲費", "早餐", 60, "早餐", "")
    cats = dm.get_categories(include_count=True)
    assert cats[0]["count"] == 2


def test_merge_categories():
    dm.add_category("E", "餐飲", "")
    dm.add_category("E", "餐飲費", "")
    dm.add_transaction("2026-01-01", "E", "餐飲", "", 100, "早餐", "")
    dm.add_transaction("2026-01-02", "E", "餐飲", "", 200, "午餐", "")
    result = dm.merge_categories("E", "餐飲", "", "E", "餐飲費", "")
    assert result["updated"] == 2
    assert result["deleted"] == 1
    # 舊分類應被刪除
    cats = dm.get_categories()
    assert not any(c["主類"] == "餐飲" and c["次類"] == "" for c in cats)
    # 交易應改為新分類
    txns = dm.query_transactions(cat_main="餐飲費")
    assert txns["total"] == 2


# ---------------------------------------------------------------------------
# 交易 CRUD
# ---------------------------------------------------------------------------

def test_add_and_get_transaction():
    row = dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 100, "豆漿", "")
    assert row["id"]
    assert row["金額"] == "100"
    fetched = dm.get_transaction(row["id"])
    assert fetched["明細"] == "豆漿"


def test_update_transaction():
    row = dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 100, "豆漿", "")
    dm.update_transaction(row["id"], "2026-01-02", "E", "餐飲費", "午餐", 150, "便當", "")
    updated = dm.get_transaction(row["id"])
    assert updated["金額"] == "150"
    assert updated["明細"] == "便當"


def test_delete_transaction():
    row = dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 100, "豆漿", "")
    assert dm.delete_transaction(row["id"]) is True
    assert dm.get_transaction(row["id"]) is None
    assert dm.delete_transaction(row["id"]) is False


def test_query_filter_date():
    dm.add_transaction("2026-01-01", "E", "餐飲費", "", 100, "", "")
    dm.add_transaction("2026-02-01", "E", "餐飲費", "", 200, "", "")
    result = dm.query_transactions(from_date="2026-02-01")
    assert result["total"] == 1


def test_query_filter_keyword():
    dm.add_transaction("2026-01-01", "E", "餐飲費", "", 100, "豆漿", "")
    dm.add_transaction("2026-01-02", "E", "餐飲費", "", 200, "便當", "")
    result = dm.query_transactions(keyword="豆漿")
    assert result["total"] == 1


def test_query_summary():
    dm.add_transaction("2026-01-01", "I", "薪資", "", 50000, "", "")
    dm.add_transaction("2026-01-05", "E", "餐飲費", "", 300, "", "")
    result = dm.query_transactions()
    assert result["summary"]["total_income"] == 50000
    assert result["summary"]["total_expense"] == 300
    assert result["summary"]["net"] == 49700


def test_query_pagination():
    for i in range(5):
        dm.add_transaction(f"2026-01-{i+1:02d}", "E", "餐飲費", "", 100, f"t{i}", "")
    r = dm.query_transactions(page=1, size=3)
    assert len(r["items"]) == 3
    assert r["pages"] == 2
    r2 = dm.query_transactions(page=2, size=3)
    assert len(r2["items"]) == 2


# ---------------------------------------------------------------------------
# 去重
# ---------------------------------------------------------------------------

def test_bulk_import_dedup():
    rows = [
        {"id": "aaa", "日期": "2026-01-01", "類型": "E", "類別主類": "餐飲費",
         "類別次類": "", "金額": "100", "明細": "早餐", "備註": "", "建立時間": "2026-01-01T00:00:00Z"},
    ]
    result1 = dm.bulk_import(rows)
    assert result1["added"] == 1
    result2 = dm.bulk_import(rows)
    assert result2["added"] == 0
    assert result2["skipped"] == 1


def test_check_duplicates():
    dm.add_transaction("2026-01-01", "E", "餐飲費", "", 100, "早餐", "")
    new_rows = [
        {"日期": "2026-01-01", "類型": "E", "類別主類": "餐飲費", "類別次類": "",
         "金額": "100", "明細": "早餐", "備註": "", "id": "x", "建立時間": "t"},
        {"日期": "2026-01-02", "類型": "E", "類別主類": "餐飲費", "類別次類": "",
         "金額": "200", "明細": "午餐", "備註": "", "id": "y", "建立時間": "t"},
    ]
    new, dup = dm.check_duplicates(new_rows)
    assert len(new) == 1
    assert dup == 1


def test_ensure_categories():
    new_cats = [
        {"類型": "E", "主類": "餐飲費", "次類": "早餐"},
        {"類型": "E", "主類": "餐飲費", "次類": "早餐"},  # 重複
        {"類型": "I", "主類": "薪資", "次類": ""},
    ]
    added = dm.ensure_categories(new_cats)
    assert added == 2
    assert len(dm.get_categories()) == 2
    # 第二次不應再新增
    assert dm.ensure_categories(new_cats) == 0


# ---------------------------------------------------------------------------
# 修正項目驗證
# ---------------------------------------------------------------------------

def test_merge_categories_src_equals_dst_raises():
    """merge src==dst 應拋出例外，不應刪除分類。"""
    dm.add_category("E", "餐飲費", "早餐")
    with pytest.raises(ValueError, match="src_equals_dst"):
        dm.merge_categories("E", "餐飲費", "早餐", "E", "餐飲費", "早餐")
    # 分類不應被刪除
    assert len(dm.get_categories()) == 1


def test_check_duplicates_self_dedup():
    """批次內重複筆數應只計一次 new，與 bulk_import 結果一致。"""
    rows = [
        {"日期": "2026-01-01", "類型": "E", "類別主類": "餐飲費", "類別次類": "",
         "金額": "100", "明細": "早餐", "備註": "", "id": "a", "建立時間": "t"},
        # 完全相同的第二筆
        {"日期": "2026-01-01", "類型": "E", "類別主類": "餐飲費", "類別次類": "",
         "金額": "100", "明細": "早餐", "備註": "", "id": "b", "建立時間": "t"},
    ]
    new_rows, dup = dm.check_duplicates(rows)
    # preview 應顯示 1 新 + 1 重複
    assert len(new_rows) == 1
    assert dup == 1
    # bulk_import 也只寫入 1 筆，與 preview 一致
    result = dm.bulk_import(rows)
    assert result["added"] == 1
    assert result["skipped"] == 1


def test_query_transactions_invalid_page():
    with pytest.raises(ValueError, match="page"):
        dm.query_transactions(page=0)


def test_query_transactions_invalid_size():
    with pytest.raises(ValueError, match="size"):
        dm.query_transactions(size=0)


def test_init_cleans_stale_tmp(tmp_path, monkeypatch):
    """init_data_files 應清理殘留的 .tmp 檔。"""
    monkeypatch.setattr(dm, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dm, "MAIN_DB", tmp_path / "main_db.csv")
    monkeypatch.setattr(dm, "CATEGORIES_CSV", tmp_path / "categories.csv")
    # 預先建立殘留暫存檔
    stale = tmp_path / "main_db.tmp"
    stale.write_text("stale")
    dm.init_data_files()
    assert not stale.exists()


# ---------------------------------------------------------------------------
# export_transactions
# ---------------------------------------------------------------------------

def test_export_transactions_basic():
    """回傳指定日期範圍內的交易。"""
    dm.add_transaction("2026-01-10", "E", "餐飲費", "", 80, "早餐", "")
    dm.add_transaction("2026-03-05", "I", "薪資", "", 50000, "薪水", "")
    dm.add_transaction("2026-07-20", "E", "餐飲費", "", 120, "午餐", "")

    rows = dm.export_transactions("2026-02-01", "2026-06-30")
    assert len(rows) == 1
    assert rows[0]["明細"] == "薪水"


def test_export_transactions_boundary_inclusive():
    """from 與 to 當天都應包含（閉區間）。"""
    dm.add_transaction("2026-01-01", "E", "餐飲費", "", 80, "首日", "")
    dm.add_transaction("2026-01-31", "E", "餐飲費", "", 120, "末日", "")
    dm.add_transaction("2025-12-31", "E", "餐飲費", "", 50, "前日", "")

    rows = dm.export_transactions("2026-01-01", "2026-01-31")
    assert len(rows) == 2
    details = {r["明細"] for r in rows}
    assert details == {"首日", "末日"}


def test_export_transactions_sort_asc():
    """排序應為日期 ASC + 建立時間 ASC（與 query_transactions 的 DESC 相反）。"""
    dm.add_transaction("2026-01-03", "E", "餐飲費", "", 80, "第三", "")
    dm.add_transaction("2026-01-01", "E", "餐飲費", "", 80, "第一", "")
    dm.add_transaction("2026-01-02", "E", "餐飲費", "", 80, "第二", "")

    rows = dm.export_transactions("2026-01-01", "2026-01-31")
    assert [r["明細"] for r in rows] == ["第一", "第二", "第三"]


def test_export_transactions_empty():
    """範圍內無資料時應回傳空 list。"""
    dm.add_transaction("2025-12-31", "E", "餐飲費", "", 80, "去年", "")
    rows = dm.export_transactions("2026-01-01", "2026-12-31")
    assert rows == []


def test_export_transactions_same_day():
    """from == to 時應只回傳當天資料。"""
    dm.add_transaction("2026-03-15", "E", "餐飲費", "", 80, "目標日", "")
    dm.add_transaction("2026-03-16", "E", "餐飲費", "", 80, "次日", "")

    rows = dm.export_transactions("2026-03-15", "2026-03-15")
    assert len(rows) == 1
    assert rows[0]["明細"] == "目標日"


# ---------------------------------------------------------------------------
# get_date_range
# ---------------------------------------------------------------------------

def test_get_date_range_empty_db():
    """空資料庫應回傳 {min: None, max: None, count: 0}。"""
    dr = dm.get_date_range()
    assert dr == {"min": None, "max": None, "count": 0}


def test_get_date_range_single():
    """只有一筆時 min == max。"""
    dm.add_transaction("2026-03-15", "E", "餐飲費", "", 80, "", "")
    dr = dm.get_date_range()
    assert dr["min"] == "2026-03-15"
    assert dr["max"] == "2026-03-15"
    assert dr["count"] == 1


def test_get_date_range_multiple():
    """多筆時正確回傳最早/最晚日期與總筆數。"""
    dm.add_transaction("2026-01-05", "E", "餐飲費", "", 80, "", "")
    dm.add_transaction("2025-06-10", "E", "餐飲費", "", 80, "", "")
    dm.add_transaction("2026-12-25", "E", "餐飲費", "", 80, "", "")

    dr = dm.get_date_range()
    assert dr["min"] == "2025-06-10"
    assert dr["max"] == "2026-12-25"
    assert dr["count"] == 3
