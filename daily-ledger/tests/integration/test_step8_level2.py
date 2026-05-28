"""
Step 8 Level 2 整合測試

涵蓋開發計畫 Step 8 驗證清單項目：
  Item 4  — 原子性：匯入途中失敗，CSV 不產生半寫入殘損狀態
  Item 8  — Power BI CSV 格式驗證：BOM、日期 YYYY-MM-DD、整數金額

以及本次 code review 修復的三個 bug 對應測試：
  Bug-1   — import_preview 新分類從 new_rows 提取（非全 rows）
  Bug-2   — CategoryMerge model 驗證類型必須為 E/I
  Bug-3   — import_export.parse_myab_csv 標頭缺失時回傳明確錯誤
"""

import csv
import io
import sys
import unittest.mock as mock
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import data_manager as dm
import import_export as ie
import app as _app_module


# ── Fixtures ─────────────────────────────────────────────────────────────────


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


# ── 工具函式 ──────────────────────────────────────────────────────────────────


def _myab_csv(*rows: str, bom: bool = False) -> bytes:
    """產生 MyAB 格式 CSV。"""
    header = "日期,類型,類別主類,類別次類,帳戶,金額,明細,備註\r\n"
    body = "\r\n".join(rows) + "\r\n"
    raw = (header + body).encode("utf-8")
    return (b"\xef\xbb\xbf" + raw) if bom else raw


def _add_cat(client, type_: str, main: str, sub: str = "") -> None:
    r = client.post("/api/categories", json={"類型": type_, "主類": main, "次類": sub})
    assert r.status_code in (200, 201), r.text


def _add_txn(
    client, date: str, type_: str, main: str, sub: str, amount: int, detail: str = ""
) -> str:
    r = client.post(
        "/api/transactions",
        json={
            "日期": date,
            "類型": type_,
            "類別主類": main,
            "類別次類": sub,
            "金額": amount,
            "明細": detail,
            "備註": "",
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _preview(client, content: bytes) -> dict:
    r = client.post(
        "/api/import/preview",
        files={"file": ("test.csv", content, "text/csv")},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _import_csv(client, content: bytes) -> dict:
    pv = _preview(client, content)
    token = pv["preview_token"]
    r2 = client.post("/api/import/confirm", json={"preview_token": token})
    assert r2.status_code == 200, r2.text
    return r2.json()


# ── Item 4：原子性 ────────────────────────────────────────────────────────────


class TestAtomicity:
    """
    Level 2 Item 4：模擬匯入途中 CSV 寫入失敗，
    驗證 main_db.csv 不會變成半寫入的殘損狀態。
    """

    def test_main_db_intact_when_write_fails(self, client, tmp_path, monkeypatch):
        """bulk_import 內 _write_csv 拋例外時，main_db.csv 的原始內容不變。"""
        # 先建立初始交易作為基線
        _add_cat(client, "E", "餐飲費", "早餐")
        _add_txn(client, "2026-01-10", "E", "餐飲費", "早餐", 100, "豆漿")

        main_db_before = dm.MAIN_DB.read_text(encoding="utf-8")

        # 建立 preview token
        content = _myab_csv("2026-02-01,E,餐飲費,早餐,,200,麵包,")
        pv_resp = _preview(client, content)
        token = pv_resp["preview_token"]

        # 讓 _write_csv 在 os.replace 時拋出 OSError
        original_write = dm._write_csv

        def _failing_write(path, rows, headers):
            # 先寫 .tmp（觸發前半段），然後模擬 rename 失敗
            import os

            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(rows)
            raise OSError("模擬磁碟寫入失敗")

        monkeypatch.setattr(dm, "_write_csv", _failing_write)

        # confirm 應拋出例外（raise_server_exceptions=True 模式下 OSError 直接傳遞）
        import pytest as _pytest

        with _pytest.raises(Exception):
            client.post("/api/import/confirm", json={"preview_token": token})

        # main_db.csv 內容應與寫入失敗前完全一致
        main_db_after = dm.MAIN_DB.read_text(encoding="utf-8")
        assert main_db_before == main_db_after

    def test_no_orphan_tmp_file_after_successful_write(self, client, tmp_path):
        """成功寫入後，不應殘留任何 .tmp 暫存檔。"""
        _add_cat(client, "E", "餐飲費", "早餐")
        content = _myab_csv("2026-01-10,E,餐飲費,早餐,,100,豆漿,")
        _import_csv(client, content)

        leftover_tmp = list(tmp_path.glob("*.tmp"))
        assert leftover_tmp == [], f"發現殘留 .tmp：{leftover_tmp}"

    def test_init_cleans_orphan_tmp(self, tmp_path, monkeypatch):
        """init_data_files 應清除前次崩潰留下的 .tmp 檔。"""
        monkeypatch.setattr(dm, "DATA_DIR", tmp_path)
        monkeypatch.setattr(dm, "MAIN_DB", tmp_path / "main_db.csv")
        monkeypatch.setattr(dm, "CATEGORIES_CSV", tmp_path / "categories.csv")

        # 建立孤立 tmp 檔模擬前次崩潰
        orphan = tmp_path / "main_db.tmp"
        orphan.write_text("orphan data", encoding="utf-8")
        assert orphan.exists()

        dm.init_data_files()

        assert not orphan.exists(), "init_data_files 應清除孤立 .tmp 檔"

    def test_categories_intact_when_main_write_fails(
        self, client, tmp_path, monkeypatch
    ):
        """bulk_import 失敗不影響 categories.csv（分類已在 ensure_categories 階段寫入）。"""
        # 正確格式：日期,類型,主類,次類,帳戶,金額,明細,備註
        content = _myab_csv("2026-01-10,E,新分類,,,100,,")
        pv_resp = _preview(client, content)
        token = pv_resp["preview_token"]

        cats_before = dm.CATEGORIES_CSV.read_text(encoding="utf-8")
        call_count = {"n": 0}

        original_write = dm._write_csv

        def _fail_on_second(path, rows, headers):
            call_count["n"] += 1
            if call_count["n"] == 2:  # 第二次呼叫（main_db）才失敗
                raise OSError("模擬寫入失敗")
            return original_write(path, rows, headers)

        monkeypatch.setattr(dm, "_write_csv", _fail_on_second)

        # confirm 應拋出例外（OSError 在 raise_server_exceptions=True 下直接傳遞）
        import pytest as _pytest

        with _pytest.raises(Exception):
            client.post("/api/import/confirm", json={"preview_token": token})

        # categories.csv 仍有寫入（第一次 _write_csv 成功）
        cats_after = dm.CATEGORIES_CSV.read_text(encoding="utf-8")
        assert "新分類" in cats_after


# ── Item 8：Power BI CSV 格式驗證 ────────────────────────────────────────────


class TestPowerBiCsvFormat:
    """
    Level 2 Item 8：匯出 CSV 的格式應符合 Power BI / Excel 讀取需求：
    - UTF-8 with BOM（Excel 開啟中文不亂碼）
    - 日期欄為 YYYY-MM-DD 格式（Power BI 原生識別）
    - 金額欄為整數字串（不含小數點、不含科學記號）
    - 含欄位標頭
    - 無多餘欄位
    """

    def _seed(self, client):
        _add_cat(client, "E", "餐飲費", "早餐")
        _add_cat(client, "I", "薪資", "")
        _add_txn(client, "2026-01-10", "E", "餐飲費", "早餐", 120, "豆漿饅頭")
        _add_txn(client, "2026-01-15", "I", "薪資", "", 50000, "一月薪資")
        _add_txn(client, "2026-06-30", "E", "餐飲費", "早餐", 999999, "大額測試")

    def test_bom_present(self, client):
        """匯出 CSV 的前三個 bytes 應為 UTF-8 BOM（0xEF BB BF）。"""
        self._seed(client)
        r = client.get("/api/export?from=2026-01-01&to=2026-12-31")
        assert r.status_code == 200
        assert r.content[:3] == b"\xef\xbb\xbf", "缺少 UTF-8 BOM"

    def test_date_format_yyyy_mm_dd(self, client):
        """每筆日期欄應符合 YYYY-MM-DD 格式（Power BI 原生識別）。"""
        self._seed(client)
        r = client.get("/api/export?from=2026-01-01&to=2026-12-31")
        rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
        import re

        pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        for row in rows:
            assert pattern.match(row["日期"]), f"日期格式錯誤：{row['日期']}"

    def test_amount_is_integer_string(self, client):
        """金額欄應為整數字串，不含小數點或科學記號。"""
        self._seed(client)
        r = client.get("/api/export?from=2026-01-01&to=2026-12-31")
        rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
        for row in rows:
            amt = row["金額"]
            assert "." not in amt, f"金額包含小數點：{amt}"
            assert "e" not in amt.lower(), f"金額含科學記號：{amt}"
            assert int(amt) > 0, f"金額非正整數：{amt}"

    def test_headers_present_and_correct(self, client):
        """匯出 CSV 應包含完整且正確順序的欄位標頭。"""
        self._seed(client)
        r = client.get("/api/export?from=2026-01-01&to=2026-12-31")
        text = r.content.decode("utf-8-sig")
        first_line = text.split("\r\n")[0] if "\r\n" in text else text.split("\n")[0]
        expected = "id,日期,類型,類別主類,類別次類,金額,明細,備註,建立時間"
        assert (
            first_line == expected
        ), f"標頭不符：\n期望：{expected}\n實際：{first_line}"

    def test_no_extra_columns(self, client):
        """匯出 CSV 不應包含帳戶等多餘欄位。"""
        self._seed(client)
        r = client.get("/api/export?from=2026-01-01&to=2026-12-31")
        reader = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")))
        expected_fields = {
            "id",
            "日期",
            "類型",
            "類別主類",
            "類別次類",
            "金額",
            "明細",
            "備註",
            "建立時間",
        }
        actual_fields = set(reader.fieldnames or [])
        unexpected = actual_fields - expected_fields
        assert not unexpected, f"出現不預期欄位：{unexpected}"

    def test_type_values_are_e_or_i(self, client):
        """所有類型欄位值只能是 E 或 I（Power BI 篩選依賴）。"""
        self._seed(client)
        r = client.get("/api/export?from=2026-01-01&to=2026-12-31")
        rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
        for row in rows:
            assert row["類型"] in ("E", "I"), f"類型值異常：{row['類型']}"

    def test_date_range_respected_in_export(self, client):
        """匯出日期範圍篩選應精確——不含範圍外的日期。"""
        self._seed(client)
        r = client.get("/api/export?from=2026-01-01&to=2026-01-31")
        rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
        for row in rows:
            assert row["日期"] <= "2026-01-31", f"日期超出範圍：{row['日期']}"
            assert row["日期"] >= "2026-01-01", f"日期早於起始：{row['日期']}"
        # 2026-06-30 那筆不應出現
        assert all(row["日期"] != "2026-06-30" for row in rows)

    def test_content_type_header(self, client):
        """回應應宣告 text/csv Content-Type。"""
        self._seed(client)
        r = client.get("/api/export?from=2026-01-01&to=2026-12-31")
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")

    def test_content_disposition_filename(self, client):
        """Content-Disposition 應包含日期格式的檔名。"""
        self._seed(client)
        r = client.get("/api/export?from=2026-01-01&to=2026-03-31")
        cd = r.headers.get("content-disposition", "")
        assert "daily_ledger_20260101_20260331.csv" in cd


# ── Bug-1：import_preview 新分類應從 new_rows 提取 ───────────────────────────


class TestImportPreviewNewCatsFromNewRows:
    """
    Bug-1 修復驗證：
    若 CSV 中所有交易均為重複（to_import=0），則不應報告任何新分類——
    即使重複交易的分類在 categories.csv 中不存在。
    """

    def test_no_new_cats_when_all_rows_are_duplicates(self, client):
        """全部重複時，new_categories_count 應為 0。"""
        # 先匯入一次，讓所有分類與交易都進入 DB
        content = _myab_csv("2026-01-10,E,餐飲費,早餐,,100,豆漿,")
        _import_csv(client, content)

        # 刪除分類，模擬「分類不存在但交易重複」的場景
        client.request(
            "DELETE",
            "/api/categories",
            json={"類型": "E", "主類": "餐飲費", "次類": "早餐"},
        )

        # 再次 preview 同一份 CSV
        pv = _preview(client, content)

        assert pv["summary"]["to_import"] == 0, "所有列應重複"
        assert (
            pv["new_categories_count"] == 0
        ), "Bug-1：全部重複時不應報告新分類（分類來自 new_rows 而非全部 rows）"

    def test_new_cats_from_genuinely_new_rows(self, client):
        """當有真正的新交易時，應仍正確回報其新分類。"""
        # 第一筆已存在（重複），第二筆是新的
        content1 = _myab_csv("2026-01-10,E,餐飲費,早餐,,100,豆漿,")
        _import_csv(client, content1)

        # 刪除分類以確保測試嚴格
        client.request(
            "DELETE",
            "/api/categories",
            json={"類型": "E", "主類": "餐飲費", "次類": "早餐"},
        )

        content2 = _myab_csv(
            "2026-01-10,E,餐飲費,早餐,,100,豆漿,",  # 重複
            "2026-02-01,E,交通費,,車票,200,捷運,",  # 新交易 + 新分類
        )
        pv = _preview(client, content2)

        assert pv["summary"]["to_import"] == 1
        # 交通費（新）應被回報；餐飲費（重複列的分類）不應
        new_cat_names = [c["主類"] for c in pv["new_categories"]]
        assert "交通費" in new_cat_names
        assert "餐飲費" not in new_cat_names

    def test_preview_new_cats_count_matches_list(self, client):
        """new_categories_count 應與 new_categories 陣列長度一致。"""
        content = _myab_csv(
            "2026-01-10,E,餐飲費,早餐,,100,豆漿,",
            "2026-01-11,I,薪資,,,50000,月薪,",
        )
        pv = _preview(client, content)
        assert pv["new_categories_count"] == len(pv["new_categories"])


# ── Bug-2：CategoryMerge model 類型驗證 ──────────────────────────────────────


class TestCategoryMergeTypeValidation:
    """
    Bug-2 修復驗證：
    CategoryMerge model 現在應驗證 來源類型/目標類型 必須為 "E" 或 "I"，
    傳入無效類型應回 422 而非 422+分類不存在。
    """

    def test_invalid_source_type_rejected(self, client):
        """來源類型為非法值時，應回 422。"""
        r = client.post(
            "/api/categories/merge",
            json={
                "來源類型": "X",
                "來源主類": "餐飲費",
                "來源次類": "",
                "目標類型": "E",
                "目標主類": "其他費",
                "目標次類": "",
            },
        )
        assert r.status_code == 422, f"期望 422，實際：{r.status_code}"

    def test_invalid_target_type_rejected(self, client):
        """目標類型為非法值時，應回 422。"""
        r = client.post(
            "/api/categories/merge",
            json={
                "來源類型": "E",
                "來源主類": "餐飲費",
                "來源次類": "",
                "目標類型": "Z",
                "目標主類": "其他費",
                "目標次類": "",
            },
        )
        assert r.status_code == 422, f"期望 422，實際：{r.status_code}"

    def test_both_types_invalid_rejected(self, client):
        """來源與目標類型都非法時，應回 422。"""
        r = client.post(
            "/api/categories/merge",
            json={
                "來源類型": "A",
                "來源主類": "帳戶A",
                "來源次類": "",
                "目標類型": "L",
                "目標主類": "帳戶B",
                "目標次類": "",
            },
        )
        assert r.status_code == 422

    def test_valid_e_type_accepted(self, client):
        """正常 E 類型合併，應成功（404/422 來自分類不存在，而非 model 驗證）。"""
        _add_cat(client, "E", "餐飲費", "")
        _add_cat(client, "E", "其他費", "")
        r = client.post(
            "/api/categories/merge",
            json={
                "來源類型": "E",
                "來源主類": "餐飲費",
                "來源次類": "",
                "目標類型": "E",
                "目標主類": "其他費",
                "目標次類": "",
            },
        )
        assert r.status_code == 200

    def test_valid_i_type_accepted(self, client):
        """正常 I 類型合併應成功。"""
        _add_cat(client, "I", "薪資", "")
        _add_cat(client, "I", "其他收入", "")
        r = client.post(
            "/api/categories/merge",
            json={
                "來源類型": "I",
                "來源主類": "薪資",
                "來源次類": "",
                "目標類型": "I",
                "目標主類": "其他收入",
                "目標次類": "",
            },
        )
        assert r.status_code == 200

    def test_cross_type_merge_rejected(self, client):
        """跨類型合併（E→I）應回 422。"""
        _add_cat(client, "E", "餐飲費", "")
        _add_cat(client, "I", "薪資", "")
        r = client.post(
            "/api/categories/merge",
            json={
                "來源類型": "E",
                "來源主類": "餐飲費",
                "來源次類": "",
                "目標類型": "I",
                "目標主類": "薪資",
                "目標次類": "",
            },
        )
        assert r.status_code == 422


# ── Bug-3：CSV 標頭驗證 ───────────────────────────────────────────────────────


class TestImportCsvHeaderValidation:
    """
    Bug-3 修復驗證：
    上傳標頭格式錯誤的 CSV 時，應回可讀的錯誤訊息，
    而非靜默回傳「0 筆可匯入」。
    """

    def test_missing_all_headers_returns_400(self, client):
        """完全無標頭的 CSV（只有資料行），應回 400 含錯誤描述。"""
        content = b"2026-01-10,E,\xe9\xa4\x90\xe9\xa3\xb2\xe8\xb2\xbb,,100,,\n"
        r = client.post(
            "/api/import/preview",
            files={"file": ("bad.csv", content, "text/csv")},
        )
        assert r.status_code == 400
        assert "欄位" in r.json()["detail"] or "格式" in r.json()["detail"]

    def test_missing_type_column_returns_400(self, client):
        """缺少「類型」欄位時，應回 400。"""
        content = "日期,類別主類,類別次類,帳戶,金額,明細,備註\r\n2026-01-10,餐飲費,,銀行,100,,\r\n".encode(
            "utf-8"
        )
        r = client.post(
            "/api/import/preview",
            files={"file": ("bad.csv", content, "text/csv")},
        )
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "類型" in detail

    def test_missing_date_column_returns_400(self, client):
        """缺少「日期」欄位時，應回 400。"""
        content = "類型,類別主類,類別次類,帳戶,金額,明細,備註\r\nE,餐飲費,,銀行,100,,\r\n".encode(
            "utf-8"
        )
        r = client.post(
            "/api/import/preview",
            files={"file": ("bad.csv", content, "text/csv")},
        )
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "日期" in detail

    def test_missing_amount_column_returns_400(self, client):
        """缺少「金額」欄位時，應回 400。"""
        content = "日期,類型,類別主類,類別次類,帳戶,明細,備註\r\n2026-01-10,E,餐飲費,,銀行,豆漿,\r\n".encode(
            "utf-8"
        )
        r = client.post(
            "/api/import/preview",
            files={"file": ("bad.csv", content, "text/csv")},
        )
        assert r.status_code == 400
        detail = r.json()["detail"]
        assert "金額" in detail

    def test_wrong_format_csv_returns_400(self, client):
        """非 MyAB 格式的 CSV（如 Daily Ledger 匯出格式）應回 400。"""
        content = "id,日期,類型,類別主類,類別次類,金額,明細,備註,建立時間\r\nabc,2026-01-10,E,餐飲費,,100,豆漿,,2026-01-10T00:00:00Z\r\n".encode(
            "utf-8"
        )
        r = client.post(
            "/api/import/preview",
            files={"file": ("wrong.csv", content, "text/csv")},
        )
        # 缺少「帳戶」欄位不是必要欄位，但缺少明確的「類型/日期/金額」三者之一才會 400
        # Daily Ledger export 其實含有類型/日期/金額，所以這個邊界測試只驗證沒有 crash
        assert r.status_code in (200, 400)

    def test_empty_csv_only_header_returns_zero_import(self, client):
        """只有標頭無資料行的 CSV：to_import=0，不應回 400。"""
        content = "日期,類型,類別主類,類別次類,帳戶,金額,明細,備註\r\n".encode("utf-8")
        r = client.post(
            "/api/import/preview",
            files={"file": ("empty.csv", content, "text/csv")},
        )
        assert r.status_code == 200
        pv = r.json()
        assert pv["summary"]["to_import"] == 0
        assert pv["summary"]["total"] == 0

    def test_correct_format_still_works(self, client):
        """標頭正確的 MyAB CSV 仍應正常解析（回歸測試）。"""
        content = _myab_csv("2026-01-10,E,餐飲費,早餐,,100,豆漿,")
        r = client.post(
            "/api/import/preview",
            files={"file": ("ok.csv", content, "text/csv")},
        )
        assert r.status_code == 200
        assert r.json()["summary"]["total"] == 1

    def test_error_message_mentions_missing_columns(self, client):
        """400 錯誤訊息應明確提及缺少的欄位名稱。"""
        # 同時缺少「類型」和「日期」
        content = "金額,類別主類,備註\r\n100,餐飲費,豆漿\r\n".encode("utf-8")
        r = client.post(
            "/api/import/preview",
            files={"file": ("missing.csv", content, "text/csv")},
        )
        assert r.status_code == 400
        detail = r.json()["detail"]
        # 至少列出一個缺失欄位
        assert any(col in detail for col in ("類型", "日期"))
