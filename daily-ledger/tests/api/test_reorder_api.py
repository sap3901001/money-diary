"""
R-02 API 測試：POST /api/categories/reorder 端點 + 排序結果影響 GET 回傳
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
    # 建立測試資料：E 三個主類各含次類
    dm.add_category("E", "餐飲費", "")
    dm.add_category("E", "餐飲費", "早餐")
    dm.add_category("E", "餐飲費", "午餐")
    dm.add_category("E", "餐飲費", "晚餐")
    dm.add_category("E", "生活雜支", "")
    dm.add_category("E", "書籍", "")
    dm.add_category("I", "薪資", "")
    dm.add_category("I", "其他收入", "")


@pytest.fixture
def client():
    from app import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ===========================================================================
# POST /api/categories/reorder — 正常操作
# ===========================================================================


class TestReorderApi:

    def test_reorder_main_down_200(self, client):
        res = client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "餐飲費", "次類": "", "direction": "down"},
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True

    def test_reorder_main_down_changes_order(self, client):
        client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "餐飲費", "次類": "", "direction": "down"},
        )
        cats = client.get("/api/categories?type=E").json()
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        assert mains[0] == "生活雜支"
        assert mains[1] == "餐飲費"

    def test_reorder_main_up_200(self, client):
        res = client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "書籍", "次類": "", "direction": "up"},
        )
        assert res.status_code == 200

    def test_reorder_main_up_changes_order(self, client):
        client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "書籍", "次類": "", "direction": "up"},
        )
        cats = client.get("/api/categories?type=E").json()
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        assert mains == ["餐飲費", "書籍", "生活雜支"]

    def test_reorder_sub_down_200(self, client):
        res = client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "餐飲費", "次類": "早餐", "direction": "down"},
        )
        assert res.status_code == 200

    def test_reorder_sub_changes_order(self, client):
        client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "餐飲費", "次類": "早餐", "direction": "down"},
        )
        cats = client.get("/api/categories?type=E").json()
        subs = [c["次類"] for c in cats if c["主類"] == "餐飲費" and c["次類"] != ""]
        assert subs == ["午餐", "早餐", "晚餐"]

    def test_reorder_does_not_affect_other_type(self, client):
        """E 排序不影響 I。"""
        i_before = client.get("/api/categories?type=I").json()
        client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "餐飲費", "次類": "", "direction": "down"},
        )
        i_after = client.get("/api/categories?type=I").json()
        assert [c["主類"] for c in i_before] == [c["主類"] for c in i_after]


# ===========================================================================
# POST /api/categories/reorder — 邊界與錯誤
# ===========================================================================


class TestReorderApiErrors:

    def test_already_first_422(self, client):
        res = client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "餐飲費", "次類": "", "direction": "up"},
        )
        assert res.status_code == 422
        assert "最前面" in res.json()["detail"]

    def test_already_last_422(self, client):
        res = client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "書籍", "次類": "", "direction": "down"},
        )
        assert res.status_code == 422
        assert "最後面" in res.json()["detail"]

    def test_sub_already_first_422(self, client):
        res = client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "餐飲費", "次類": "早餐", "direction": "up"},
        )
        assert res.status_code == 422

    def test_sub_already_last_422(self, client):
        res = client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "餐飲費", "次類": "晚餐", "direction": "down"},
        )
        assert res.status_code == 422

    def test_not_found_404(self, client):
        res = client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "不存在的分類", "次類": "", "direction": "up"},
        )
        assert res.status_code == 404
        assert "不存在" in res.json()["detail"]

    def test_invalid_direction_422(self, client):
        res = client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "餐飲費", "次類": "", "direction": "left"},
        )
        assert res.status_code == 422

    def test_invalid_type_422(self, client):
        res = client.post(
            "/api/categories/reorder",
            json={"類型": "X", "主類": "餐飲費", "次類": "", "direction": "up"},
        )
        assert res.status_code == 422

    def test_missing_direction_422(self, client):
        res = client.post(
            "/api/categories/reorder", json={"類型": "E", "主類": "餐飲費", "次類": ""}
        )
        assert res.status_code == 422


# ===========================================================================
# 排序後 GET /api/categories 影響下拉選單順序
# ===========================================================================


class TestSortOrderAffectsDropdown:
    """排序結果應影響所有讀取分類的 API 回傳。"""

    def test_get_categories_reflects_reorder(self, client):
        # 初始順序 E: 餐飲費, 生活雜支, 書籍
        client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "書籍", "次類": "", "direction": "up"},
        )
        # 現在 E: 餐飲費, 書籍, 生活雜支
        client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "書籍", "次類": "", "direction": "up"},
        )
        # 現在 E: 書籍, 餐飲費, 生活雜支
        cats = client.get("/api/categories?type=E").json()
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        assert mains == ["書籍", "餐飲費", "生活雜支"]

    def test_include_count_preserves_sort_order(self, client):
        """加 include_count=1 後排序仍正確。"""
        client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "餐飲費", "次類": "", "direction": "down"},
        )
        cats = client.get("/api/categories?type=E&include_count=1").json()
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        assert mains[0] == "生活雜支"
        assert all("count" in c for c in cats)

    def test_new_category_appended_last_in_api(self, client):
        """透過 API 新增分類後排在末位。"""
        client.post("/api/categories", json={"類型": "E", "主類": "新分類", "次類": ""})
        cats = client.get("/api/categories?type=E").json()
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        assert mains[-1] == "新分類"

    def test_reorder_then_add_does_not_break(self, client):
        """排序操作後新增分類，整體排序仍一致。"""
        client.post(
            "/api/categories/reorder",
            json={"類型": "E", "主類": "生活雜支", "次類": "", "direction": "up"},
        )
        # E: 生活雜支, 餐飲費, 書籍
        client.post("/api/categories", json={"類型": "E", "主類": "電腦", "次類": ""})
        cats = client.get("/api/categories?type=E").json()
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        assert mains == ["生活雜支", "餐飲費", "書籍", "電腦"]


# ===========================================================================
# sort_order 欄位不外洩
# ===========================================================================


class TestSortOrderFieldVisibility:
    """確認 API 回傳中 sort_order 欄位的處理。"""

    def test_get_categories_includes_sort_order(self, client):
        """sort_order 欄位會隨 API 回傳（目前設計如此）。"""
        cats = client.get("/api/categories").json()
        # sort_order 目前會隨 CSV 欄位回傳
        assert all("sort_order" in c for c in cats)
