"""
Step 2 API 測試：交易與分類端點
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
    # 預建測試分類
    dm.add_category("E", "餐飲費", "早餐")
    dm.add_category("E", "餐飲費", "午餐")
    dm.add_category("I", "薪資", "")


@pytest.fixture
def client():
    # patch 完畢後再 import app，確保 app 用到的 dm 已被 monkeypatch
    from app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── 分類 GET ──

def test_get_categories_all(client):
    res = client.get("/api/categories")
    assert res.status_code == 200
    assert len(res.json()) == 3


def test_get_categories_type_filter(client):
    res = client.get("/api/categories?type=E")
    assert res.status_code == 200
    assert all(c["類型"] == "E" for c in res.json())


def test_get_categories_include_count(client):
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 100, "早餐", "")
    res = client.get("/api/categories?include_count=1")
    assert res.status_code == 200
    cats = res.json()
    for c in cats:
        assert "count" in c


# ── 分類 POST / DELETE ──

def test_add_category(client):
    res = client.post("/api/categories", json={"類型": "E", "主類": "交通", "次類": ""})
    assert res.status_code == 201


def test_add_duplicate_category(client):
    res = client.post("/api/categories", json={"類型": "E", "主類": "餐飲費", "次類": "早餐"})
    assert res.status_code == 409


def test_delete_category(client):
    res = client.request("DELETE", "/api/categories",
                         json={"類型": "I", "主類": "薪資", "次類": ""})
    assert res.status_code == 204


def test_delete_category_in_use(client):
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 100, "早餐", "")
    res = client.request("DELETE", "/api/categories",
                         json={"類型": "E", "主類": "餐飲費", "次類": "早餐"})
    assert res.status_code == 409


# ── 分類 merge ──

def test_merge_categories(client):
    # 來源：餐飲（無次類）；目標：餐飲費/早餐（已在 fixture）
    dm.add_category("E", "餐飲", "")
    dm.add_transaction("2026-01-01", "E", "餐飲", "", 200, "外食", "")
    res = client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "餐飲", "來源次類": "",
        "目標類型": "E", "目標主類": "餐飲費", "目標次類": "早餐",
    })
    assert res.status_code == 200
    assert res.json()["updated"] == 1


def test_merge_categories_dst_not_found(client):
    dm.add_category("E", "餐飲", "")
    res = client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "餐飲", "來源次類": "",
        "目標類型": "E", "目標主類": "不存在的分類", "目標次類": "",
    })
    assert res.status_code == 422


def test_merge_categories_src_equals_dst(client):
    res = client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "餐飲費", "來源次類": "早餐",
        "目標類型": "E", "目標主類": "餐飲費", "目標次類": "早餐",
    })
    assert res.status_code == 422


# ── 交易 POST ──

def test_create_transaction(client):
    res = client.post("/api/transactions", json={
        "日期": "2026-01-01", "類型": "E", "類別主類": "餐飲費",
        "類別次類": "早餐", "金額": 80, "明細": "豆漿油條",
    })
    assert res.status_code == 201
    data = res.json()
    assert data["id"]
    assert data["金額"] == "80"


def test_create_transaction_invalid_date(client):
    res = client.post("/api/transactions", json={
        "日期": "2026/01/01", "類型": "E", "類別主類": "餐飲費",
        "類別次類": "早餐", "金額": 80,
    })
    assert res.status_code == 422


def test_create_transaction_invalid_type(client):
    res = client.post("/api/transactions", json={
        "日期": "2026-01-01", "類型": "X", "類別主類": "餐飲費",
        "類別次類": "早餐", "金額": 80,
    })
    assert res.status_code == 422


def test_create_transaction_zero_amount(client):
    res = client.post("/api/transactions", json={
        "日期": "2026-01-01", "類型": "E", "類別主類": "餐飲費",
        "類別次類": "早餐", "金額": 0,
    })
    assert res.status_code == 422


def test_create_transaction_nonexistent_category(client):
    res = client.post("/api/transactions", json={
        "日期": "2026-01-01", "類型": "E", "類別主類": "不存在",
        "類別次類": "", "金額": 100,
    })
    assert res.status_code == 422


# ── 交易 GET ──

def test_list_transactions(client):
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 80, "豆漿", "")
    dm.add_transaction("2026-01-02", "I", "薪資", "", 50000, "", "")
    res = client.get("/api/transactions")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert "summary" in data


def test_list_transactions_date_filter(client):
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 80, "", "")
    dm.add_transaction("2026-02-01", "E", "餐飲費", "午餐", 120, "", "")
    res = client.get("/api/transactions?from=2026-02-01&to=2026-02-28")
    assert res.json()["total"] == 1


def test_list_transactions_summary(client):
    dm.add_transaction("2026-01-01", "I", "薪資", "", 50000, "", "")
    dm.add_transaction("2026-01-05", "E", "餐飲費", "早餐", 300, "", "")
    res = client.get("/api/transactions")
    s = res.json()["summary"]
    assert s["total_income"] == 50000
    assert s["total_expense"] == 300
    assert s["net"] == 49700


# ── 交易 GET/{id} ──

def test_get_transaction(client):
    row = dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 80, "豆漿", "")
    res = client.get(f"/api/transactions/{row['id']}")
    assert res.status_code == 200


def test_get_transaction_not_found(client):
    assert client.get("/api/transactions/nonexist").status_code == 404


# ── 交易 PUT ──

def test_update_transaction(client):
    row = dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 80, "豆漿", "")
    res = client.put(f"/api/transactions/{row['id']}", json={
        "日期": "2026-01-02", "類型": "E", "類別主類": "餐飲費",
        "類別次類": "午餐", "金額": 150, "明細": "便當",
    })
    assert res.status_code == 200
    assert res.json()["金額"] == "150"


# ── 交易 DELETE ──

def test_delete_transaction(client):
    row = dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 80, "", "")
    assert client.delete(f"/api/transactions/{row['id']}").status_code == 204
    assert client.delete(f"/api/transactions/{row['id']}").status_code == 404


# ── date_range ──

def test_date_range_empty(client):
    res = client.get("/api/transactions/date_range")
    assert res.status_code == 200
    assert res.json()["count"] == 0


def test_date_range(client):
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 80, "", "")
    dm.add_transaction("2026-03-15", "I", "薪資", "", 50000, "", "")
    res = client.get("/api/transactions/date_range")
    data = res.json()
    assert data["min"] == "2026-01-01"
    assert data["max"] == "2026-03-15"
    assert data["count"] == 2
