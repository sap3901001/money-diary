"""
Step 6 功能需求測試 — CSV 匯出
對應 AT-011 / AT-012 / AT-017 / AT-018

FR-EXP-1  資料範圍篩選（閉區間）
FR-EXP-2  排序規則（日期 ASC + 建立時間 ASC）
FR-EXP-3  CSV 格式規範（欄位、編碼、BOM）
FR-EXP-4  檔名規則（Content-Disposition）
FR-EXP-5  輸入驗證
FR-EXP-6  特殊字元 CSV 轉義
FR-EXP-7  無分頁限制（超過 100 筆）
FR-EXP-8  Round-trip 一致性（AT-017）
"""
import csv
import io
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import data_manager as dm
import import_export as ie

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MAIN_HEADERS = ["id", "日期", "類型", "類別主類", "類別次類", "金額", "明細", "備註", "建立時間"]


@pytest.fixture(autouse=True)
def patch_data(tmp_path, monkeypatch):
    monkeypatch.setattr(dm, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dm, "MAIN_DB", tmp_path / "main_db.csv")
    monkeypatch.setattr(dm, "CATEGORIES_CSV", tmp_path / "categories.csv")
    dm.init_data_files()
    dm.add_category("E", "餐飲費", "早餐")
    dm.add_category("E", "餐飲費", "午餐")
    dm.add_category("E", "交通費", "")
    dm.add_category("I", "薪資", "")
    dm.add_category("I", "其他收入", "")


@pytest.fixture
def client():
    from app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _parse_csv(content: bytes) -> list[dict]:
    text = content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def _export(client, from_: str, to: str):
    return client.get(f"/api/export?from={from_}&to={to}")


# ---------------------------------------------------------------------------
# FR-EXP-1：資料範圍篩選（AT-011 部分、AT-012）
# ---------------------------------------------------------------------------

class TestFREXP1_DateRange:
    """FR-EXP-1: 匯出只包含指定日期範圍內的交易（閉區間）。"""

    def test_AT012_empty_range_outputs_header_only(self, client):
        """AT-012: 空範圍仍輸出 header，筆數為 0。"""
        dm.add_transaction("2025-12-31", "E", "餐飲費", "早餐", 100, "前日", "")

        res = _export(client, "2026-01-01", "2026-12-31")
        assert res.status_code == 200
        rows = _parse_csv(res.content)
        assert len(rows) == 0, "空範圍應有 0 筆資料"
        # 確認仍有 header（DictReader 能正常解析）
        text = res.content.decode("utf-8-sig")
        assert "日期" in text.splitlines()[0]

    def test_from_date_included(self, client):
        """from 當天的交易應包含（閉區間左端）。"""
        dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 80, "首日", "")
        dm.add_transaction("2025-12-31", "E", "餐飲費", "午餐", 50, "前日", "")

        rows = _parse_csv(_export(client, "2026-01-01", "2026-12-31").content)
        assert len(rows) == 1
        assert rows[0]["明細"] == "首日"

    def test_to_date_included(self, client):
        """to 當天的交易應包含（閉區間右端）。"""
        dm.add_transaction("2026-01-31", "E", "餐飲費", "早餐", 80, "末日", "")
        dm.add_transaction("2026-02-01", "E", "餐飲費", "午餐", 50, "次月", "")

        rows = _parse_csv(_export(client, "2026-01-01", "2026-01-31").content)
        assert len(rows) == 1
        assert rows[0]["明細"] == "末日"

    def test_single_day_export(self, client):
        """from == to 時應只回傳當天資料。"""
        dm.add_transaction("2026-03-15", "E", "餐飲費", "早餐", 80, "當天", "")
        dm.add_transaction("2026-03-14", "E", "餐飲費", "午餐", 50, "前天", "")
        dm.add_transaction("2026-03-16", "E", "餐飲費", "早餐", 50, "後天", "")

        rows = _parse_csv(_export(client, "2026-03-15", "2026-03-15").content)
        assert len(rows) == 1
        assert rows[0]["明細"] == "當天"

    def test_multiple_types_included(self, client):
        """支出（E）與收入（I）都應匯出，不過濾類型。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "早餐", "")
        dm.add_transaction("2026-01-15", "I", "薪資", "", 50000, "薪水", "")

        rows = _parse_csv(_export(client, "2026-01-01", "2026-01-31").content)
        assert len(rows) == 2
        types = {r["類型"] for r in rows}
        assert types == {"E", "I"}


# ---------------------------------------------------------------------------
# FR-EXP-2：排序規則（AT-011）
# ---------------------------------------------------------------------------

class TestFREXP2_SortOrder:
    """FR-EXP-2: 匯出排序應為日期 ASC + 建立時間 ASC（與列表頁 DESC 相反）。"""

    def test_AT011_sort_by_date_asc(self, client):
        """AT-011: 多筆不同日期，應依日期 ASC 排序。"""
        dm.add_transaction("2026-01-20", "E", "餐飲費", "早餐", 80, "第三", "")
        dm.add_transaction("2026-01-05", "E", "餐飲費", "午餐", 80, "第一", "")
        dm.add_transaction("2026-01-12", "E", "交通費", "", 80, "第二", "")

        rows = _parse_csv(_export(client, "2026-01-01", "2026-01-31").content)
        dates = [r["日期"] for r in rows]
        assert dates == sorted(dates), f"日期應 ASC，實際：{dates}"

    def test_same_date_sort_by_created_time_asc(self, client):
        """同日多筆應依建立時間 ASC 排序（先新增者排前面）。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "先新增", "")
        time.sleep(0.01)  # 確保建立時間不同
        dm.add_transaction("2026-01-10", "E", "餐飲費", "午餐", 80, "後新增", "")

        rows = _parse_csv(_export(client, "2026-01-10", "2026-01-10").content)
        assert len(rows) == 2
        assert rows[0]["明細"] == "先新增"
        assert rows[1]["明細"] == "後新增"

    def test_cross_month_sort_asc(self, client):
        """跨月資料應整體依日期 ASC 排序。"""
        dm.add_transaction("2026-03-01", "E", "餐飲費", "早餐", 80, "三月", "")
        dm.add_transaction("2026-01-01", "E", "餐飲費", "午餐", 80, "一月", "")
        dm.add_transaction("2026-02-01", "E", "交通費", "", 80, "二月", "")

        rows = _parse_csv(_export(client, "2026-01-01", "2026-12-31").content)
        details = [r["明細"] for r in rows]
        assert details == ["一月", "二月", "三月"]


# ---------------------------------------------------------------------------
# FR-EXP-3：CSV 格式規範（AT-018）
# ---------------------------------------------------------------------------

class TestFREXP3_CSVFormat:
    """FR-EXP-3: 匯出 CSV 的格式、編碼與欄位規範。"""

    def test_AT018_utf8_bom_present(self, client):
        """AT-018: 匯出檔必須包含 UTF-8 BOM（Excel 開啟中文無亂碼）。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "測試", "")
        res = _export(client, "2026-01-01", "2026-12-31")
        assert res.content[:3] == b"\xef\xbb\xbf", "首 3 bytes 應為 UTF-8 BOM"

    def test_header_field_order(self, client):
        """CSV header 欄位順序應與 MAIN_HEADERS 完全一致。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "測試", "")
        res = _export(client, "2026-01-01", "2026-12-31")
        text = res.content.decode("utf-8-sig")
        header_line = text.splitlines()[0]
        actual_headers = header_line.split(",")
        assert actual_headers == MAIN_HEADERS, f"欄位順序不符：{actual_headers}"

    def test_amount_always_positive_integer(self, client):
        """金額欄應儲存正整數，收支方向由類型欄決定，不使用負數。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 150, "支出", "")
        dm.add_transaction("2026-01-15", "I", "薪資", "", 50000, "收入", "")

        rows = _parse_csv(_export(client, "2026-01-01", "2026-01-31").content)
        for r in rows:
            amount = int(r["金額"])
            assert amount > 0, f"金額應為正整數，實際值：{r['金額']}"

    def test_all_nine_fields_exported(self, client):
        """每筆資料應包含全部 9 個欄位。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "豆漿", "早餐備註")
        rows = _parse_csv(_export(client, "2026-01-01", "2026-12-31").content)
        assert len(rows) == 1
        assert set(rows[0].keys()) == set(MAIN_HEADERS)

    def test_content_type_header(self, client):
        """Content-Type 應為 text/csv; charset=utf-8（非 utf-8-sig）。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "測試", "")
        res = _export(client, "2026-01-01", "2026-12-31")
        ct = res.headers.get("content-type", "")
        assert "text/csv" in ct
        assert "utf-8" in ct
        assert "utf-8-sig" not in ct, "charset 應為 utf-8，不應出現 utf-8-sig"

    def test_id_and_created_time_present(self, client):
        """id 與建立時間應自動填入且格式正確。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "測試", "")
        rows = _parse_csv(_export(client, "2026-01-01", "2026-12-31").content)
        assert rows[0]["id"]                               # 非空
        assert len(rows[0]["id"]) == 8                     # UUID4 前 8 碼
        assert "T" in rows[0]["建立時間"]                  # ISO 8601 格式（含 T）


# ---------------------------------------------------------------------------
# FR-EXP-4：檔名規則
# ---------------------------------------------------------------------------

class TestFREXP4_Filename:
    """FR-EXP-4: Content-Disposition 的下載檔名規則。"""

    def test_filename_format(self, client):
        """檔名應為 daily_ledger_{YYYYMMDD}_{YYYYMMDD}.csv。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "測試", "")
        res = _export(client, "2026-01-15", "2026-03-20")
        cd = res.headers.get("content-disposition", "")
        assert "daily_ledger_20260115_20260320.csv" in cd

    def test_filename_attachment_disposition(self, client):
        """Content-Disposition 應為 attachment（觸發瀏覽器下載）。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "測試", "")
        res = _export(client, "2026-01-01", "2026-12-31")
        cd = res.headers.get("content-disposition", "")
        assert cd.startswith("attachment"), f"應以 attachment 開頭：{cd}"

    def test_filename_same_day(self, client):
        """from == to 時，兩個日期部分應相同。"""
        dm.add_transaction("2026-03-15", "E", "餐飲費", "早餐", 80, "測試", "")
        res = _export(client, "2026-03-15", "2026-03-15")
        cd = res.headers.get("content-disposition", "")
        assert "daily_ledger_20260315_20260315.csv" in cd


# ---------------------------------------------------------------------------
# FR-EXP-5：輸入驗證
# ---------------------------------------------------------------------------

class TestFREXP5_InputValidation:
    """FR-EXP-5: API 參數驗證。"""

    def test_missing_from_returns_422(self, client):
        res = client.get("/api/export?to=2026-12-31")
        assert res.status_code == 422

    def test_missing_to_returns_422(self, client):
        res = client.get("/api/export?from=2026-01-01")
        assert res.status_code == 422

    def test_invalid_format_from_returns_422(self, client):
        """日期格式錯誤（YYYYMMDD 而非 YYYY-MM-DD）。"""
        res = client.get("/api/export?from=20260101&to=2026-12-31")
        assert res.status_code == 422

    def test_invalid_format_to_returns_422(self, client):
        """日期格式錯誤（YYYY/MM/DD）。"""
        res = client.get("/api/export?from=2026-01-01&to=2026/12/31")
        assert res.status_code == 422

    def test_invalid_date_value_month13_returns_422(self, client):
        """格式正確但月份 13 應回傳 422（strptime 驗證）。"""
        res = client.get("/api/export?from=2026-13-01&to=2026-12-31")
        assert res.status_code == 422

    def test_invalid_date_value_feb30_returns_422(self, client):
        """格式正確但 2 月 30 日應回傳 422（strptime 驗證）。"""
        res = client.get("/api/export?from=2026-01-01&to=2026-02-30")
        assert res.status_code == 422

    def test_from_after_to_returns_422(self, client):
        """from 晚於 to 應回傳 422。"""
        res = client.get("/api/export?from=2026-12-31&to=2026-01-01")
        assert res.status_code == 422
        assert "開始日期" in res.json()["detail"]


# ---------------------------------------------------------------------------
# FR-EXP-6：特殊字元 CSV 轉義
# ---------------------------------------------------------------------------

class TestFREXP6_SpecialChars:
    """FR-EXP-6: 明細/備註含特殊字元時 CSV 應正確轉義，不破壞格式。"""

    def test_comma_in_field(self, client):
        """明細含逗號，CSV 應以雙引號包住。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "豆漿,油條", "")
        rows = _parse_csv(_export(client, "2026-01-01", "2026-01-31").content)
        assert rows[0]["明細"] == "豆漿,油條"

    def test_double_quote_in_field(self, client):
        """明細含雙引號，CSV 應以兩個雙引號轉義。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, '含"引號"', "")
        rows = _parse_csv(_export(client, "2026-01-01", "2026-01-31").content)
        assert rows[0]["明細"] == '含"引號"'

    def test_chinese_characters(self, client):
        """中文字元應正確保留（UTF-8 BOM 確保 Excel 無亂碼）。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "豆漿油條燒餅", "早餐備註：好吃")
        rows = _parse_csv(_export(client, "2026-01-01", "2026-01-31").content)
        assert rows[0]["明細"] == "豆漿油條燒餅"
        assert rows[0]["備註"] == "早餐備註：好吃"

    def test_empty_optional_fields(self, client):
        """次類、備註可為空字串，匯出時應保留空欄位。"""
        dm.add_transaction("2026-01-10", "E", "交通費", "", 50, "捷運", "")
        rows = _parse_csv(_export(client, "2026-01-01", "2026-01-31").content)
        assert rows[0]["類別次類"] == ""
        assert rows[0]["備註"] == ""


# ---------------------------------------------------------------------------
# FR-EXP-7：無分頁限制
# ---------------------------------------------------------------------------

class TestFREXP7_NoPagination:
    """FR-EXP-7: 匯出不受 query_transactions 的 100 筆分頁限制。"""

    def test_export_more_than_100_rows(self, client):
        """匯出 150 筆，應全部包含（不受 API 分頁 size=100 限制）。"""
        for i in range(150):
            dm.add_transaction(
                f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
                "E", "餐飲費", "早餐", 80, f"第{i+1}筆", "",
            )

        res = _export(client, "2026-01-01", "2026-12-31")
        rows = _parse_csv(res.content)
        assert len(rows) == 150, f"應匯出 150 筆，實際 {len(rows)} 筆"

    def test_export_count_independent_of_list_pagination(self, client):
        """確認匯出筆數與 GET /api/transactions 的 total 一致（非僅第一頁）。"""
        for i in range(120):
            dm.add_transaction("2026-01-15", "E", "餐飲費", "早餐", 100, f"t{i}", "")

        export_rows = _parse_csv(_export(client, "2026-01-01", "2026-01-31").content)
        list_total = client.get("/api/transactions?from=2026-01-01&to=2026-01-31&size=1").json()["total"]

        assert len(export_rows) == list_total == 120


# ---------------------------------------------------------------------------
# FR-EXP-8：Round-trip 一致性（AT-017）
# ---------------------------------------------------------------------------

class TestFREXP8_RoundTrip:
    """FR-EXP-8 / AT-017: 匯出資料應與原始資料在計數與金額上完全一致。"""

    def test_AT017_export_count_matches_db(self, client):
        """AT-017: 匯出筆數等於資料庫中該範圍的實際筆數。"""
        txns = [
            ("2026-01-10", "E", "餐飲費", "早餐", 80, "早餐", ""),
            ("2026-02-05", "I", "薪資", "", 50000, "二月薪水", ""),
            ("2026-03-20", "E", "交通費", "", 120, "捷運月票", ""),
        ]
        for t in txns:
            dm.add_transaction(*t)

        export_rows = _parse_csv(_export(client, "2026-01-01", "2026-12-31").content)
        db_total = dm.query_transactions(from_date="2026-01-01", to_date="2026-12-31")["total"]

        assert len(export_rows) == db_total == 3

    def test_AT017_export_amount_sum_matches_db(self, client):
        """AT-017: 匯出金額加總應與資料庫統計一致。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "早餐", "")
        dm.add_transaction("2026-01-15", "E", "交通費", "", 120, "計程車", "")
        dm.add_transaction("2026-01-20", "I", "薪資", "", 50000, "薪水", "")

        export_rows = _parse_csv(_export(client, "2026-01-01", "2026-01-31").content)
        export_expense = sum(int(r["金額"]) for r in export_rows if r["類型"] == "E")
        export_income  = sum(int(r["金額"]) for r in export_rows if r["類型"] == "I")

        db_summary = dm.query_transactions(from_date="2026-01-01", to_date="2026-01-31")["summary"]
        assert export_expense == db_summary["total_expense"] == 200
        assert export_income  == db_summary["total_income"]  == 50000

    def test_AT017_field_values_preserved(self, client):
        """AT-017: 每個欄位值在匯出後應與原始寫入值完全相同。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "午餐", 350, "便當加飲料", "午餐備註")

        rows = _parse_csv(_export(client, "2026-01-01", "2026-12-31").content)
        r = rows[0]
        assert r["日期"]    == "2026-01-10"
        assert r["類型"]    == "E"
        assert r["類別主類"] == "餐飲費"
        assert r["類別次類"] == "午餐"
        assert r["金額"]    == "350"
        assert r["明細"]    == "便當加飲料"
        assert r["備註"]    == "午餐備註"

    def test_AT017_no_data_loss_after_export(self, client):
        """AT-017: 執行匯出後，資料庫原始資料不受影響。"""
        dm.add_transaction("2026-01-10", "E", "餐飲費", "早餐", 80, "早餐", "")

        _export(client, "2026-01-01", "2026-12-31")  # 執行匯出

        # 確認資料仍在資料庫
        result = dm.query_transactions()
        assert result["total"] == 1
        assert result["items"][0]["明細"] == "早餐"
