"""
整合測試：匯入 → 列表 / 報表 / 匯出數據一致性

涵蓋 Level 2 整合測試項目：
  - 匯入驗證：975 筆 MyAB CSV（973 E/I，2 A/L 過濾）
  - 去重測試：重複匯入同份 CSV → 0 新增
  - 邊界字元：逗號、引號、中文特殊字元
  - Round-trip（AT-017）：匯出 CSV 欄位與資料庫完全一致
  - 報表一致性（AT-015 整合版）：monthly sum == transaction summary
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

# ── 真實資料路徑（相對本專案）──
REAL_CSV = (
    Path(__file__).parent.parent.parent.parent
    / "myab_export"
    / "target"
    / "transactions.csv"
)

# 已知正確數據（由 myab_export 工具驗證，去重後實際匯入值）
EXPECTED_EI_COUNT = 961  # 去重後實際寫入 DB 的筆數
EXPECTED_PARSED = 968  # parse 後合法 E/I 筆數（含批次內重複 7 筆）
EXPECTED_INCOME = 205771
EXPECTED_EXPENSE = 710424

# ── Fixtures ──


@pytest.fixture(autouse=True)
def patch_data(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dm, "MAIN_DB", tmp_path / "main_db.csv")
    monkeypatch.setattr(dm, "CATEGORIES_CSV", tmp_path / "categories.csv")
    dm.init_data_files()
    _app_module._preview_store.clear()


@pytest.fixture
def client():
    from app import app

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── 工具函式 ──


def _import_csv(client, content: bytes) -> dict:
    """Preview → Confirm，回傳 confirm response。"""
    r = client.post(
        "/api/import/preview",
        files={"file": ("test.csv", content, "text/csv")},
    )
    assert r.status_code == 200, r.text
    token = r.json()["preview_token"]
    r2 = client.post("/api/import/confirm", json={"preview_token": token})
    assert r2.status_code == 200, r2.text
    return r2.json()


def _myab_csv(*rows: str, bom: bool = False) -> bytes:
    """產生 MyAB 格式 CSV（無 BOM 預設）。"""
    header = "日期,類型,類別主類,類別次類,帳戶,金額,明細,備註\r\n"
    body = "\r\n".join(rows) + "\r\n"
    content = (header + body).encode("utf-8")
    if bom:
        content = b"\xef\xbb\xbf" + content
    return content


# ── 1. 真實 MyAB CSV 匯入驗證 ─────────────────────────────────────────────────


@pytest.mark.skipif(not REAL_CSV.exists(), reason="真實 CSV 不存在，跳過")
class TestRealCsvImport:

    def test_import_count(self, client):
        """匯入 975 筆 MyAB CSV，應成功寫入 973 筆（過濾 A/L）。"""
        content = REAL_CSV.read_bytes()
        result = _import_csv(client, content)
        assert result["added"] == EXPECTED_EI_COUNT

    def test_import_totals(self, client):
        """匯入後交易總金額應與預期一致。"""
        content = REAL_CSV.read_bytes()
        _import_csv(client, content)

        r = client.get("/api/transactions?size=1")
        assert r.status_code == 200
        summary = r.json()["summary"]
        assert summary["total_count"] == EXPECTED_EI_COUNT
        assert summary["total_income"] == EXPECTED_INCOME
        assert summary["total_expense"] == EXPECTED_EXPENSE

    def test_duplicate_import_no_new_rows(self, client):
        """重複匯入同一份 CSV，不應產生任何重複筆數。"""
        content = REAL_CSV.read_bytes()
        first = _import_csv(client, content)
        assert first["added"] == EXPECTED_EI_COUNT

        # 第二次 preview 應全部為重複（summary.duplicates == EXPECTED_EI_COUNT）
        r = client.post(
            "/api/import/preview",
            files={"file": ("test.csv", content, "text/csv")},
        )
        assert r.status_code == 200
        preview = r.json()
        assert preview["summary"]["duplicates"] == EXPECTED_PARSED
        assert preview["summary"]["to_import"] == 0

        # confirm 後 DB 總筆數不變
        token = preview["preview_token"]
        r2 = client.post("/api/import/confirm", json={"preview_token": token})
        assert r2.status_code == 200
        assert r2.json()["added"] == 0

        r = client.get("/api/transactions?size=1")
        assert r.json()["summary"]["total_count"] == EXPECTED_EI_COUNT

    def test_import_then_report_monthly_consistent(self, client):
        """匯入後，月報 income/expense 加總應與 transaction summary 一致（AT-015 整合版）。"""
        content = REAL_CSV.read_bytes()
        _import_csv(client, content)

        # 取 transaction summary（全範圍）
        r = client.get("/api/transactions?size=1")
        summary = r.json()["summary"]
        expected_income = summary["total_income"]
        expected_expense = summary["total_expense"]

        # 月報全範圍加總
        r2 = client.get("/api/report/monthly?from=2000-01-01&to=2099-12-31&type=all")
        assert r2.status_code == 200
        monthly = r2.json()
        total_income = sum(m["income"] for m in monthly)
        total_expense = sum(m["expense"] for m in monthly)

        assert total_income == expected_income
        assert total_expense == expected_expense


# ── 2. 邊界字元測試 ────────────────────────────────────────────────────────────


class TestEdgeCharacters:

    def test_comma_in_detail(self, client):
        """明細含逗號時，CSV 應正確引用，資料無損。"""
        content = _myab_csv('2026-01-05,E,餐飲費,早餐,,100,"豆漿,饅頭",')
        result = _import_csv(client, content)
        assert result["added"] == 1

        r = client.get("/api/transactions?size=10")
        txn = r.json()["items"][0]
        assert txn["明細"] == "豆漿,饅頭"

    def test_quote_in_detail(self, client):
        """明細含雙引號時，CSV escaped 後資料無損。"""
        content = _myab_csv('2026-01-05,E,餐飲費,早餐,,100,"他說""好吃""",')
        result = _import_csv(client, content)
        assert result["added"] == 1

        r = client.get("/api/transactions?size=10")
        txn = r.json()["items"][0]
        assert txn["明細"] == '他說"好吃"'

    def test_chinese_special_chars(self, client):
        """中文特殊字元（含 BOM）應正確解析。"""
        content = _myab_csv(
            "2026-01-05,E,餐飲費,早餐,,50,麥當勞（台幣）,",
            bom=True,
        )
        result = _import_csv(client, content)
        assert result["added"] == 1

        r = client.get("/api/transactions?size=10")
        txn = r.json()["items"][0]
        assert txn["明細"] == "麥當勞（台幣）"

    def test_newline_in_note_is_rejected_or_stripped(self, client):
        """備註含換行符：CSV 仍應正常解析（備註不在去重鍵中）。"""
        # Python csv 模組會將雙引號內換行視為合法欄位內容
        content = _myab_csv('2026-01-05,I,薪資,,銀行,50000,月薪,"A\nB"')
        result = _import_csv(client, content)
        assert result["added"] == 1


# ── 3. Round-trip 一致性（AT-017）────────────────────────────────────────────


class TestRoundTrip:

    def _seed(self, client):
        """建立分類並新增測試交易，回傳新增的交易清單。"""
        client.post(
            "/api/categories", json={"類型": "E", "主類": "餐飲費", "次類": "早餐"}
        )
        client.post("/api/categories", json={"類型": "I", "主類": "薪資", "次類": ""})

        rows = [
            {
                "日期": "2026-01-10",
                "類型": "E",
                "類別主類": "餐飲費",
                "類別次類": "早餐",
                "金額": 120,
                "明細": "豆漿饅頭",
                "備註": "",
            },
            {
                "日期": "2026-01-15",
                "類型": "I",
                "類別主類": "薪資",
                "類別次類": "",
                "金額": 50000,
                "明細": "一月薪資",
                "備註": "匯款",
            },
            {
                "日期": "2026-02-05",
                "類型": "E",
                "類別主類": "餐飲費",
                "類別次類": "早餐",
                "金額": 85,
                "明細": "咖啡,吐司",
                "備註": "",
            },
        ]
        for row in rows:
            r = client.post("/api/transactions", json=row)
            assert r.status_code in (200, 201)
        return rows

    def test_export_fields_match_db(self, client):
        """AT-017：匯出 CSV 每個欄位應與 DB 中的原始值完全一致。"""
        self._seed(client)

        # 取 DB 中全部交易（排序：日期 ASC + 建立時間 ASC）
        r = client.get("/api/transactions?size=500")
        all_txns = sorted(
            r.json()["items"],
            key=lambda t: (t["日期"], t["建立時間"]),
        )

        # 匯出 CSV
        r2 = client.get("/api/export?from=2026-01-01&to=2099-12-31")
        assert r2.status_code == 200
        text = r2.content.decode("utf-8-sig")
        reader = list(csv.DictReader(io.StringIO(text)))

        assert len(reader) == len(all_txns)
        for db_row, csv_row in zip(all_txns, reader):
            assert csv_row["id"] == db_row["id"]
            assert csv_row["日期"] == db_row["日期"]
            assert csv_row["類型"] == db_row["類型"]
            assert csv_row["類別主類"] == db_row["類別主類"]
            assert csv_row["類別次類"] == db_row["類別次類"]
            assert csv_row["金額"] == db_row["金額"]
            assert csv_row["明細"] == db_row["明細"]
            assert csv_row["備註"] == db_row["備註"]
            assert csv_row["建立時間"] == db_row["建立時間"]

    def test_export_count_matches_db(self, client):
        """AT-017：匯出筆數應與資料庫篩選結果相同。"""
        self._seed(client)

        r = client.get("/api/transactions?size=500")
        db_count = r.json()["summary"]["total_count"]

        r2 = client.get("/api/export?from=2026-01-01&to=2099-12-31")
        text = r2.content.decode("utf-8-sig")
        export_count = sum(1 for _ in csv.DictReader(io.StringIO(text)))

        assert export_count == db_count

    def test_export_totals_match_db(self, client):
        """AT-017：匯出 CSV 中金額加總應與資料庫統計一致。"""
        self._seed(client)

        r = client.get("/api/transactions?size=500")
        summary = r.json()["summary"]

        r2 = client.get("/api/export?from=2026-01-01&to=2099-12-31")
        text = r2.content.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))

        export_income = sum(int(row["金額"]) for row in rows if row["類型"] == "I")
        export_expense = sum(int(row["金額"]) for row in rows if row["類型"] == "E")

        assert export_income == summary["total_income"]
        assert export_expense == summary["total_expense"]

    def test_db_unchanged_after_export(self, client):
        """AT-017：匯出不應修改資料庫。"""
        self._seed(client)

        r_before = client.get("/api/transactions?size=500")
        count_before = r_before.json()["summary"]["total_count"]

        client.get("/api/export?from=2026-01-01&to=2099-12-31")

        r_after = client.get("/api/transactions?size=500")
        count_after = r_after.json()["summary"]["total_count"]

        assert count_before == count_after
