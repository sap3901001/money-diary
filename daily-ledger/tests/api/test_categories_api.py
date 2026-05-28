"""
Step 4 測試：分類管理 API 完整測試（AT-006~AT-008, AT-016）
"""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import data_manager as dm


@pytest.fixture(autouse=True)
def patch_data(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DATA_DIR",       tmp_path)
    monkeypatch.setattr(dm, "MAIN_DB",        tmp_path / "main_db.csv")
    monkeypatch.setattr(dm, "CATEGORIES_CSV", tmp_path / "categories.csv")
    dm.init_data_files()
    dm.add_category("E", "餐飲費", "早餐")
    dm.add_category("E", "餐飲費", "午餐")
    dm.add_category("E", "生活雜支", "")
    dm.add_category("I", "薪資", "")
    dm.add_category("I", "其他收入", "")


@pytest.fixture
def client():
    from app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── GET /api/categories ──

def test_get_all_categories(client):
    res = client.get("/api/categories")
    assert res.status_code == 200
    assert len(res.json()) == 5


def test_get_categories_type_E(client):
    res = client.get("/api/categories?type=E")
    assert res.status_code == 200
    cats = res.json()
    assert len(cats) == 3
    assert all(c["類型"] == "E" for c in cats)


def test_get_categories_type_I(client):
    res = client.get("/api/categories?type=I")
    assert res.status_code == 200
    cats = res.json()
    assert len(cats) == 2
    assert all(c["類型"] == "I" for c in cats)


def test_get_categories_include_count_field(client):
    res = client.get("/api/categories?include_count=1")
    assert res.status_code == 200
    for c in res.json():
        assert "count" in c


def test_get_categories_include_count_zero_new(client):
    res = client.get("/api/categories?include_count=1")
    assert all(c["count"] == 0 for c in res.json())


def test_get_categories_include_count_accuracy(client):
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 100, "早餐", "")
    dm.add_transaction("2026-01-02", "E", "餐飲費", "早餐", 120, "早餐", "")
    dm.add_transaction("2026-01-03", "E", "餐飲費", "午餐", 90, "午餐", "")
    res = client.get("/api/categories?include_count=1&type=E")
    cats = res.json()
    zaochan = next(c for c in cats if c["主類"] == "餐飲費" and c["次類"] == "早餐")
    wuchan  = next(c for c in cats if c["主類"] == "餐飲費" and c["次類"] == "午餐")
    assert zaochan["count"] == 2
    assert wuchan["count"]  == 1


# ── POST /api/categories ──

def test_add_category_with_sub(client):
    res = client.post("/api/categories", json={"類型": "E", "主類": "交通", "次類": "捷運"})
    assert res.status_code == 201
    assert res.json()["主類"] == "交通"
    assert res.json()["次類"] == "捷運"


def test_add_category_without_sub(client):
    res = client.post("/api/categories", json={"類型": "I", "主類": "租金收入", "次類": ""})
    assert res.status_code == 201


def test_add_category_duplicate_409(client):
    """AT-006：重複新增回 409"""
    res = client.post("/api/categories", json={"類型": "E", "主類": "餐飲費", "次類": "早餐"})
    assert res.status_code == 409


def test_add_category_empty_main(client):
    res = client.post("/api/categories", json={"類型": "E", "主類": "   ", "次類": ""})
    assert res.status_code == 422


def test_add_category_invalid_type(client):
    res = client.post("/api/categories", json={"類型": "X", "主類": "測試", "次類": ""})
    assert res.status_code == 422


def test_add_category_trims_main(client):
    res = client.post("/api/categories", json={"類型": "E", "主類": "  交通  ", "次類": ""})
    assert res.status_code == 201
    assert res.json()["主類"] == "交通"


# ── DELETE /api/categories ──

def test_delete_category_no_ref(client):
    res = client.request("DELETE", "/api/categories",
                         json={"類型": "I", "主類": "其他收入", "次類": ""})
    assert res.status_code == 204
    # 確認已從列表消失
    cats = client.get("/api/categories?type=I").json()
    assert not any(c["主類"] == "其他收入" and c["次類"] == "" for c in cats)


def test_delete_category_in_use_409(client):
    """AT-007：有交易引用時拒絕刪除"""
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 100, "", "")
    res = client.request("DELETE", "/api/categories",
                         json={"類型": "E", "主類": "餐飲費", "次類": "早餐"})
    assert res.status_code == 409


def test_delete_category_not_found_404(client):
    res = client.request("DELETE", "/api/categories",
                         json={"類型": "E", "主類": "不存在", "次類": ""})
    assert res.status_code == 404


def test_delete_category_updates_list(client):
    client.request("DELETE", "/api/categories",
                   json={"類型": "E", "主類": "生活雜支", "次類": ""})
    cats = client.get("/api/categories?type=E").json()
    assert len(cats) == 2  # 原 3 筆，刪 1 筆


# ── POST /api/categories/merge ──

def test_merge_basic(client):
    """AT-008：基本合併"""
    dm.add_category("E", "餐飲", "")
    dm.add_transaction("2026-01-01", "E", "餐飲", "", 200, "外食", "")
    res = client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "餐飲",   "來源次類": "",
        "目標類型": "E", "目標主類": "餐飲費", "目標次類": "早餐",
    })
    assert res.status_code == 200
    assert res.json()["updated"] == 1


def test_merge_dst_not_found(client):
    res = client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "餐飲費", "來源次類": "早餐",
        "目標類型": "E", "目標主類": "不存在",  "目標次類": "",
    })
    assert res.status_code == 422


def test_merge_src_equals_dst(client):
    res = client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "餐飲費", "來源次類": "早餐",
        "目標類型": "E", "目標主類": "餐飲費", "目標次類": "早餐",
    })
    assert res.status_code == 422


def test_merge_updates_transactions(client):
    """AT-016：merge 後交易引用正確更新"""
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 80, "豆漿", "")
    dm.add_transaction("2026-01-02", "E", "餐飲費", "早餐", 90, "吐司", "")
    res = client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "餐飲費", "來源次類": "早餐",
        "目標類型": "E", "目標主類": "餐飲費", "目標次類": "午餐",
    })
    assert res.status_code == 200
    assert res.json()["updated"] == 2
    # 確認交易已指向目標
    txns = client.get("/api/transactions?type=E&category_main=餐飲費&category_sub=午餐").json()
    assert txns["total"] == 2  # 兩筆早餐交易 merge 為午餐


def test_merge_deletes_src_category(client):
    """merge 後來源分類被刪除"""
    dm.add_category("E", "外食", "")
    client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "外食",  "來源次類": "",
        "目標類型": "E", "目標主類": "餐飲費", "目標次類": "早餐",
    })
    cats = client.get("/api/categories?type=E").json()
    assert not any(c["主類"] == "外食" and c["次類"] == "" for c in cats)


def test_merge_zero_transactions(client):
    """merge 零交易：來源分類仍會被刪除"""
    dm.add_category("E", "暫用", "")
    res = client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "暫用",   "來源次類": "",
        "目標類型": "E", "目標主類": "餐飲費", "目標次類": "早餐",
    })
    assert res.status_code == 200
    assert res.json()["updated"] == 0
    assert res.json()["deleted"] == 1
    cats = client.get("/api/categories?type=E").json()
    assert not any(c["主類"] == "暫用" for c in cats)


def test_merge_count_after_merge(client):
    """merge 後 include_count 顯示正確"""
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 100, "", "")
    client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "餐飲費", "來源次類": "早餐",
        "目標類型": "E", "目標主類": "餐飲費", "目標次類": "午餐",
    })
    cats = client.get("/api/categories?type=E&include_count=1").json()
    wuchan = next(c for c in cats if c["主類"] == "餐飲費" and c["次類"] == "午餐")
    assert wuchan["count"] == 1
    # 來源已不存在
    assert not any(c["主類"] == "餐飲費" and c["次類"] == "早餐" for c in cats)
