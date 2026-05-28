"""
整合測試：分類合併後 main_db.csv 與 categories.csv 引用一致性

涵蓋 Level 2 整合測試項目：
  - 合併功能：合併後所有交易引用正確更新（AT-016 整合版）
  - 來源分類從 categories.csv 移除
  - 合併後報表金額不變（分類名稱改變，金額不變）
  - 合併後匯出 CSV 引用正確
  - 改名（前端實作為 merge）後 include_count 正確
"""
import csv
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import data_manager as dm
import app as _app_module

# ── Fixtures ──

@pytest.fixture(autouse=True)
def patch_data(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DATA_DIR",       tmp_path)
    monkeypatch.setattr(dm, "MAIN_DB",        tmp_path / "main_db.csv")
    monkeypatch.setattr(dm, "CATEGORIES_CSV", tmp_path / "categories.csv")
    dm.init_data_files()
    _app_module._preview_store.clear()


@pytest.fixture
def client():
    from app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── 工具函式 ──

def _add_cat(client, type_: str, main: str, sub: str = "") -> None:
    r = client.post("/api/categories", json={"類型": type_, "主類": main, "次類": sub})
    assert r.status_code in (200, 201), r.text


def _add_txn(client, date: str, type_: str, main: str, sub: str,
             amount: int, detail: str = "", note: str = "") -> str:
    r = client.post("/api/transactions", json={
        "日期": date, "類型": type_, "類別主類": main, "類別次類": sub,
        "金額": amount, "明細": detail, "備註": note,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _merge(client, src_type, src_main, src_sub, dst_type, dst_main, dst_sub) -> dict:
    r = client.post("/api/categories/merge", json={
        "來源類型": src_type, "來源主類": src_main, "來源次類": src_sub,
        "目標類型": dst_type, "目標主類": dst_main, "目標次類": dst_sub,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _get_cats(client, type_: str | None = None) -> list[dict]:
    url = "/api/categories?include_count=1"
    if type_:
        url += f"&type={type_}"
    return client.get(url).json()


def _get_txns(client) -> list[dict]:
    return client.get("/api/transactions?size=500").json()["items"]


# ── 1. 基本合併一致性 ──────────────────────────────────────────────────────────

class TestBasicMergeConsistency:

    def test_merged_transactions_reference_dst(self, client):
        """合併後，原屬於 src 的交易應改為引用 dst。"""
        _add_cat(client, "E", "餐飲費", "早餐")
        _add_cat(client, "E", "餐飲費", "午餐")

        _add_txn(client, "2026-01-10", "E", "餐飲費", "早餐", 100, "豆漿")
        _add_txn(client, "2026-01-11", "E", "餐飲費", "早餐", 120, "饅頭")

        _merge(client, "E", "餐飲費", "早餐", "E", "餐飲費", "午餐")

        txns = _get_txns(client)
        for t in txns:
            assert not (t["類別主類"] == "餐飲費" and t["類別次類"] == "早餐"), \
                "src 分類引用應已被移除"
            assert t["類別主類"] == "餐飲費"
            assert t["類別次類"] == "午餐"

    def test_src_category_removed(self, client):
        """合併後，src 分類應從 categories.csv 移除。"""
        _add_cat(client, "E", "餐飲費", "早餐")
        _add_cat(client, "E", "餐飲費", "午餐")
        _add_txn(client, "2026-01-10", "E", "餐飲費", "早餐", 100)

        _merge(client, "E", "餐飲費", "早餐", "E", "餐飲費", "午餐")

        cats = _get_cats(client, "E")
        names = [(c["主類"], c["次類"]) for c in cats]
        assert ("餐飲費", "早餐")  not in names
        assert ("餐飲費", "午餐") in names

    def test_dst_count_increases(self, client):
        """合併後，dst 分類的 include_count 應增加。"""
        _add_cat(client, "E", "餐飲費", "早餐")
        _add_cat(client, "E", "餐飲費", "午餐")

        _add_txn(client, "2026-01-10", "E", "餐飲費", "早餐", 100)
        _add_txn(client, "2026-01-10", "E", "餐飲費", "午餐", 200)

        # 合併前：早餐 count=1, 午餐 count=1
        _merge(client, "E", "餐飲費", "早餐", "E", "餐飲費", "午餐")

        cats = _get_cats(client, "E")
        dst = next(c for c in cats if c["主類"] == "餐飲費" and c["次類"] == "午餐")
        assert dst["count"] == 2   # 早餐的 1 筆轉移 + 原 1 筆

    def test_merge_returns_correct_counts(self, client):
        """merge API 回傳的 updated / deleted 數值正確。"""
        _add_cat(client, "E", "餐飲費", "早餐")
        _add_cat(client, "E", "餐飲費", "午餐")

        _add_txn(client, "2026-01-10", "E", "餐飲費", "早餐", 100)
        _add_txn(client, "2026-01-11", "E", "餐飲費", "早餐", 150)

        result = _merge(client, "E", "餐飲費", "早餐", "E", "餐飲費", "午餐")
        assert result["updated"] == 2
        assert result["deleted"] == 1


# ── 2. 合併後報表一致性 ────────────────────────────────────────────────────────

class TestMergeReportConsistency:

    def _setup(self, client):
        _add_cat(client, "E", "餐飲費", "早餐")
        _add_cat(client, "E", "餐飲費", "午餐")
        _add_cat(client, "I", "薪資",   "")

        _add_txn(client, "2026-01-10", "E", "餐飲費", "早餐", 100)
        _add_txn(client, "2026-01-15", "E", "餐飲費", "午餐", 200)
        _add_txn(client, "2026-01-20", "I", "薪資",   "",    50000)

    def test_total_amounts_unchanged_after_merge(self, client):
        """合併後，收入/支出總金額應與合併前完全一致。"""
        self._setup(client)

        r_before = client.get("/api/transactions?size=500")
        before = r_before.json()["summary"]

        _merge(client, "E", "餐飲費", "早餐", "E", "餐飲費", "午餐")

        r_after = client.get("/api/transactions?size=500")
        after = r_after.json()["summary"]

        assert before["total_income"]  == after["total_income"]
        assert before["total_expense"] == after["total_expense"]
        assert before["total_count"]   == after["total_count"]

    def test_monthly_report_consistent_after_merge(self, client):
        """合併後，月報加總應與 transaction summary 一致。"""
        self._setup(client)
        _merge(client, "E", "餐飲費", "早餐", "E", "餐飲費", "午餐")

        r = client.get("/api/transactions?size=500")
        summary = r.json()["summary"]

        r2 = client.get("/api/report/monthly?from=2026-01-01&to=2026-01-31&type=all")
        monthly = r2.json()
        total_income  = sum(m["income"]  for m in monthly)
        total_expense = sum(m["expense"] for m in monthly)

        assert total_income  == summary["total_income"]
        assert total_expense == summary["total_expense"]

    def test_category_report_only_dst_after_merge(self, client):
        """合併後，分類報表中只應出現 dst 分類，src 不應存在。"""
        self._setup(client)
        _merge(client, "E", "餐飲費", "早餐", "E", "餐飲費", "午餐")

        r = client.get("/api/report/category?from=2026-01-01&to=2026-01-31&type=E&level=sub")
        data = r.json()
        names = [i["name"] for i in data["items"]]
        # level=sub 格式為 "主類/次類"
        assert not any("早餐" in n for n in names)
        assert any("午餐" in n for n in names)
        # 午餐應含早餐的金額
        dst_item = next(i for i in data["items"] if "午餐" in i["name"])
        assert dst_item["amount"] == 300   # 100 + 200


# ── 3. 合併後匯出一致性 ────────────────────────────────────────────────────────

class TestMergeExportConsistency:

    def test_export_reflects_merged_categories(self, client):
        """合併後匯出的 CSV 中，所有交易應引用 dst 分類。"""
        _add_cat(client, "E", "餐飲費", "早餐")
        _add_cat(client, "E", "餐飲費", "午餐")
        _add_txn(client, "2026-01-10", "E", "餐飲費", "早餐", 100, "豆漿")
        _add_txn(client, "2026-01-11", "E", "餐飲費", "早餐", 150, "饅頭")

        _merge(client, "E", "餐飲費", "早餐", "E", "餐飲費", "午餐")

        r = client.get("/api/export?from=2026-01-01&to=2026-01-31")
        assert r.status_code == 200
        text = r.content.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))

        assert len(rows) == 2
        for row in rows:
            assert row["類別次類"] == "午餐"

    def test_export_amounts_unchanged_after_merge(self, client):
        """合併後匯出，金額加總應與合併前一致。"""
        _add_cat(client, "E", "餐飲費", "早餐")
        _add_cat(client, "E", "餐飲費", "午餐")
        _add_txn(client, "2026-01-10", "E", "餐飲費", "早餐", 300)
        _add_txn(client, "2026-01-11", "E", "餐飲費", "午餐", 400)

        # 合併前匯出
        r1 = client.get("/api/export?from=2026-01-01&to=2026-01-31")
        rows1 = list(csv.DictReader(io.StringIO(r1.content.decode("utf-8-sig"))))
        total_before = sum(int(r["金額"]) for r in rows1)

        _merge(client, "E", "餐飲費", "早餐", "E", "餐飲費", "午餐")

        # 合併後匯出
        r2 = client.get("/api/export?from=2026-01-01&to=2026-01-31")
        rows2 = list(csv.DictReader(io.StringIO(r2.content.decode("utf-8-sig"))))
        total_after = sum(int(r["金額"]) for r in rows2)

        assert total_before == total_after == 700


# ── 4. 邊界：主類合併（含所有次類）─────────────────────────────────────────────

class TestMainCategoryMerge:

    def test_merge_main_category_leaf(self, client):
        """合併主類層（次類為空）的分類。"""
        _add_cat(client, "E", "雜費",   "")
        _add_cat(client, "E", "其他費", "")
        _add_txn(client, "2026-01-10", "E", "雜費", "", 50, "買文具")
        _add_txn(client, "2026-01-11", "E", "雜費", "", 80, "買清潔用品")

        result = _merge(client, "E", "雜費", "", "E", "其他費", "")
        assert result["updated"] == 2

        txns = _get_txns(client)
        for t in txns:
            assert t["類別主類"] == "其他費"

    def test_merge_no_transactions(self, client):
        """合併無交易引用的分類：updated=0, deleted=1。"""
        _add_cat(client, "E", "閒置分類", "")
        _add_cat(client, "E", "其他費",   "")

        result = _merge(client, "E", "閒置分類", "", "E", "其他費", "")
        assert result["updated"] == 0
        assert result["deleted"] == 1

        cats = _get_cats(client, "E")
        names = [c["主類"] for c in cats]
        assert "閒置分類" not in names
        assert "其他費"   in names
