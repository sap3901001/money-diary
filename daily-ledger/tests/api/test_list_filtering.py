"""
Step 3 測試：列表篩選、分頁、摘要、編輯、刪除整合測試
"""
import sys
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
    dm.add_category("E", "交通", "")
    dm.add_category("I", "薪資", "")


@pytest.fixture
def client():
    from app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def seed(client):
    """建立 5 筆測試資料"""
    dm.add_transaction("2026-01-05", "E", "餐飲費", "早餐",  80,  "豆漿",  "")
    dm.add_transaction("2026-01-10", "E", "餐飲費", "午餐",  120, "便當",  "")
    dm.add_transaction("2026-01-15", "E", "交通",   "",      50,  "捷運",  "")
    dm.add_transaction("2026-01-20", "I", "薪資",   "",      50000, "",    "")
    dm.add_transaction("2026-02-01", "E", "餐飲費", "早餐",  90,  "稀飯",  "")


# ── 篩選 ──

def test_filter_by_date_range(client, seed):
    res = client.get("/api/transactions?from=2026-01-01&to=2026-01-31")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 4
    assert all(t["日期"].startswith("2026-01") for t in data["items"])


def test_filter_by_type(client, seed):
    res = client.get("/api/transactions?type=I")
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["類型"] == "I"


def test_filter_by_category_main(client, seed):
    res = client.get("/api/transactions?category_main=餐飲費")
    assert res.json()["total"] == 3


def test_filter_by_category_sub(client, seed):
    res = client.get("/api/transactions?category_main=餐飲費&category_sub=早餐")
    assert res.json()["total"] == 2


def test_filter_by_keyword_in_detail(client, seed):
    res = client.get("/api/transactions?keyword=便當")
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["明細"] == "便當"


def test_filter_by_amount_range(client, seed):
    res = client.get("/api/transactions?amount_min=80&amount_max=120")
    data = res.json()
    assert data["total"] == 3
    for t in data["items"]:
        assert 80 <= int(t["金額"]) <= 120


def test_combined_filters(client, seed):
    res = client.get("/api/transactions?from=2026-01-01&to=2026-01-31&type=E&category_main=餐飲費")
    assert res.json()["total"] == 2


# ── 排序 ──

def test_results_sorted_date_desc(client, seed):
    res = client.get("/api/transactions")
    items = res.json()["items"]
    dates = [t["日期"] for t in items]
    assert dates == sorted(dates, reverse=True)


# ── 摘要 ──

def test_summary_fields_present(client, seed):
    res = client.get("/api/transactions?from=2026-01-01&to=2026-01-31")
    s = res.json()["summary"]
    assert "total_count" in s
    assert "total_income" in s
    assert "total_expense" in s
    assert "net" in s


def test_summary_values(client, seed):
    res = client.get("/api/transactions?from=2026-01-01&to=2026-01-31")
    s = res.json()["summary"]
    assert s["total_income"]  == 50000
    assert s["total_expense"] == 250    # 80+120+50
    assert s["net"]           == 49750


def test_summary_empty_result(client):
    res = client.get("/api/transactions?from=2099-01-01&to=2099-12-31")
    s = res.json()["summary"]
    assert s["total_count"]   == 0
    assert s["total_income"]  == 0
    assert s["total_expense"] == 0
    assert s["net"]           == 0


# ── 分頁 ──

def test_pagination_structure(client, seed):
    res = client.get("/api/transactions?size=2&page=1")
    data = res.json()
    assert data["page"]  == 1
    assert data["size"]  == 2
    assert data["pages"] == 3   # 5筆/2 = ceil(5/2) = 3頁
    assert len(data["items"]) == 2


def test_pagination_last_page(client, seed):
    res = client.get("/api/transactions?size=2&page=3")
    data = res.json()
    assert len(data["items"]) == 1


def test_pagination_page_out_of_range(client, seed):
    # page > pages → 回傳空 items（非錯誤）
    res = client.get("/api/transactions?size=2&page=99")
    assert res.status_code == 200
    assert res.json()["items"] == []


def test_pagination_invalid_page(client):
    res = client.get("/api/transactions?page=0")
    assert res.status_code == 422


def test_pagination_invalid_size(client):
    res = client.get("/api/transactions?size=0")
    assert res.status_code == 422


def test_pagination_size_over_limit(client):
    res = client.get("/api/transactions?size=501")
    assert res.status_code == 422


# ── 編輯（PUT）──

def test_edit_transaction_changes_all_fields(client, seed):
    row = dm.add_transaction("2026-03-01", "E", "餐飲費", "早餐", 100, "原始", "")
    res = client.put(f"/api/transactions/{row['id']}", json={
        "日期": "2026-03-02", "類型": "E", "類別主類": "交通",
        "類別次類": "", "金額": 200, "明細": "修改後", "備註": "備",
    })
    assert res.status_code == 200
    updated = res.json()
    assert updated["日期"]     == "2026-03-02"
    assert updated["類別主類"] == "交通"
    assert updated["金額"]     == "200"
    assert updated["明細"]     == "修改後"


def test_edit_preserves_id_and_created_time(client, seed):
    row = dm.add_transaction("2026-03-01", "E", "餐飲費", "早餐", 100, "", "")
    res = client.put(f"/api/transactions/{row['id']}", json={
        "日期": "2026-03-01", "類型": "E", "類別主類": "餐飲費",
        "類別次類": "早餐", "金額": 150, "明細": "",
    })
    updated = res.json()
    assert updated["id"]      == row["id"]
    assert updated["建立時間"] == row["建立時間"]


def test_edit_nonexistent(client):
    res = client.put("/api/transactions/nonexistent", json={
        "日期": "2026-01-01", "類型": "E", "類別主類": "餐飲費",
        "類別次類": "早餐", "金額": 100,
    })
    assert res.status_code == 404


def test_edit_invalid_category(client, seed):
    row = dm.add_transaction("2026-03-01", "E", "餐飲費", "早餐", 100, "", "")
    res = client.put(f"/api/transactions/{row['id']}", json={
        "日期": "2026-03-01", "類型": "E", "類別主類": "不存在",
        "類別次類": "", "金額": 100,
    })
    assert res.status_code == 422


# ── 刪除（DELETE）──

def test_delete_removes_transaction(client, seed):
    row = dm.add_transaction("2026-03-01", "E", "餐飲費", "早餐", 100, "", "")
    assert client.delete(f"/api/transactions/{row['id']}").status_code == 204
    assert client.get(f"/api/transactions/{row['id']}").status_code == 404


def test_delete_nonexistent(client):
    assert client.delete("/api/transactions/nonexistent").status_code == 404


def test_delete_reduces_count(client, seed):
    before = client.get("/api/transactions").json()["total"]
    row = dm.add_transaction("2026-03-01", "E", "餐飲費", "早餐", 100, "", "")
    client.delete(f"/api/transactions/{row['id']}")
    after = client.get("/api/transactions").json()["total"]
    assert after == before
