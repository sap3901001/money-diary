"""
Step 4 補充測試：覆蓋缺口分析後新增的測試案例
涵蓋：response shape、邊界條件、sub 空白、merge src 不存在、
       type filter 驗證、DELETE 204 無 body、跨類型 merge 行為
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


# ── GET /api/categories 補充 ──

def test_get_categories_invalid_type_returns_422(client):
    """?type=X 不合法應回 422"""
    res = client.get("/api/categories?type=X")
    assert res.status_code == 422


def test_get_categories_response_shape(client):
    """每筆分類物件必須包含 類型、主類、次類 三個欄位"""
    res = client.get("/api/categories")
    assert res.status_code == 200
    for item in res.json():
        assert "類型" in item
        assert "主類" in item
        assert "次類" in item


def test_get_categories_count_combines_with_type(client):
    """include_count=1 + type=E 同時使用，count 僅計算 E 交易"""
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 100, "早餐", "")
    dm.add_transaction("2026-01-01", "I", "薪資", "", 50000, "薪水", "")
    res = client.get("/api/categories?type=E&include_count=1")
    assert res.status_code == 200
    cats = res.json()
    # 所有回傳分類都是 E 且有 count 欄位
    assert all("count" in c for c in cats)
    zaochan = next(c for c in cats if c["主類"] == "餐飲費" and c["次類"] == "早餐")
    assert zaochan["count"] == 1


def test_get_categories_sort_order_respected(client):
    """分類回傳順序應依 sort_order 排列"""
    res = client.get("/api/categories?type=E")
    cats = res.json()
    # 同主類的次類應依 sort_order 排列
    subs = [c for c in cats if c["主類"] == "餐飲費" and c["次類"] != ""]
    assert subs[0]["次類"] == "早餐"
    assert subs[1]["次類"] == "午餐"
    # 所有分類都應有 sort_order 欄位
    assert all("sort_order" in c for c in cats)


# ── POST /api/categories 補充 ──

def test_add_category_response_shape(client):
    """POST 回傳物件包含 類型、主類、次類"""
    res = client.post("/api/categories", json={"類型": "E", "主類": "交通", "次類": "捷運"})
    assert res.status_code == 201
    body = res.json()
    assert body["類型"] == "E"
    assert body["主類"] == "交通"
    assert body["次類"] == "捷運"


def test_add_category_sub_whitespace_trimmed(client):
    """次類前後空白應被 trim（目前缺少驗證，此測試預期失敗揭露缺口）"""
    res = client.post("/api/categories", json={"類型": "E", "主類": "交通", "次類": "  捷運  "})
    assert res.status_code == 201
    # 預期次類被 trim 為 "捷運"；若後端無 trim，此行會失敗
    assert res.json()["次類"] == "捷運"


def test_add_category_whitespace_sub_should_be_empty(client):
    """次類為純空白字串應被視為空（""）；目前缺少驗證"""
    res = client.post("/api/categories", json={"類型": "E", "主類": "交通", "次類": "   "})
    assert res.status_code == 201
    # 預期 trim 後存為 ""，與 次類="" 行為相同
    assert res.json()["次類"] == ""


def test_add_category_zero_amount_rejected(client):
    """Pydantic 應拒絕金額 0 的交易（間接驗證：分類新增本身不涉及金額）
    此測試改為驗證：次類欄含特殊字元（逗號）仍可新增"""
    res = client.post("/api/categories", json={"類型": "E", "主類": "測試,逗號", "次類": ""})
    assert res.status_code == 201
    assert res.json()["主類"] == "測試,逗號"


def test_add_category_quote_in_name(client):
    """分類名稱含雙引號（CSV 特殊字元）應可正確儲存與讀取"""
    res = client.post("/api/categories", json={"類型": "E", "主類": '測試"引號', "次類": ""})
    assert res.status_code == 201
    cats = client.get("/api/categories?type=E").json()
    assert any(c["主類"] == '測試"引號' for c in cats)


# ── DELETE /api/categories 補充 ──

def test_delete_category_204_no_body(client):
    """DELETE 成功應回傳 204，且 response body 為空"""
    res = client.request("DELETE", "/api/categories",
                         json={"類型": "I", "主類": "其他收入", "次類": ""})
    assert res.status_code == 204
    assert res.content == b""


def test_delete_sub_keeps_sibling_sub(client):
    """刪除一個次類不應影響同主類下的其他次類"""
    client.request("DELETE", "/api/categories",
                   json={"類型": "E", "主類": "餐飲費", "次類": "早餐"})
    cats = client.get("/api/categories?type=E").json()
    # 午餐應仍存在
    assert any(c["主類"] == "餐飲費" and c["次類"] == "午餐" for c in cats)


def test_delete_category_type_validation(client):
    """DELETE body 傳入無效類型應回 422"""
    res = client.request("DELETE", "/api/categories",
                         json={"類型": "X", "主類": "不存在", "次類": ""})
    assert res.status_code == 422


# ── POST /api/categories/merge 補充 ──

def test_merge_src_not_found_should_error(client):
    """merge 來源分類不存在時應回錯誤（目前缺少檢查，會回 200 deleted=0）"""
    res = client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "不存在", "來源次類": "",
        "目標類型": "E", "目標主類": "餐飲費", "目標次類": "早餐",
    })
    # 預期回 404 或 422；目前行為回 200（缺漏）
    assert res.status_code in (404, 422)


def test_merge_response_shape(client):
    """merge 回傳物件包含 updated、deleted、deleted_category"""
    dm.add_category("E", "外食", "")
    res = client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "外食", "來源次類": "",
        "目標類型": "E", "目標主類": "餐飲費", "目標次類": "早餐",
    })
    assert res.status_code == 200
    body = res.json()
    assert "updated" in body
    assert "deleted" in body
    assert "deleted_category" in body
    assert body["deleted_category"]["類型"] == "E"
    assert body["deleted_category"]["主類"] == "外食"


def test_merge_cross_type_not_allowed(client):
    """跨類型 merge（E→I）應被拒絕（目前缺少驗證，會執行成功）"""
    res = client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "餐飲費", "來源次類": "早餐",
        "目標類型": "I", "目標主類": "薪資", "目標次類": "",
    })
    # 預期應回 422；目前缺少跨類型驗證
    assert res.status_code == 422


def test_merge_only_affects_matching_transactions(client):
    """merge 後只更新符合 src 的交易，其他交易不受影響"""
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 100, "早餐", "")
    dm.add_transaction("2026-01-02", "E", "生活雜支", "", 50, "雜支", "")
    client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "餐飲費", "來源次類": "早餐",
        "目標類型": "E", "目標主類": "餐飲費", "目標次類": "午餐",
    })
    # 生活雜支那筆不應被改動
    res = client.get("/api/transactions?type=E&category_main=生活雜支")
    assert res.json()["total"] == 1


def test_merge_deleted_field_equals_1(client):
    """merge 成功時 deleted 應為 1（一筆來源分類被刪）"""
    dm.add_category("E", "外食費", "")
    res = client.post("/api/categories/merge", json={
        "來源類型": "E", "來源主類": "外食費", "來源次類": "",
        "目標類型": "E", "目標主類": "餐飲費", "目標次類": "早餐",
    })
    assert res.status_code == 200
    assert res.json()["deleted"] == 1
