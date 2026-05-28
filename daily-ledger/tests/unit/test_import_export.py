"""
unit tests — import_export.py（MyAB CSV 解析邏輯）
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import import_export as ie

# ── 測試用 CSV 內容 ──

_HEADER = "日期,類型,類別主類,類別次類,帳戶,金額,明細,備註\r\n"


def _csv(*rows: str) -> bytes:
    """組合 CSV bytes（UTF-8，無 BOM）。"""
    return (_HEADER + "\r\n".join(rows) + "\r\n").encode("utf-8")


def _csv_bom(*rows: str) -> bytes:
    """組合 CSV bytes（UTF-8 with BOM）。"""
    return b"\xef\xbb\xbf" + _csv(*rows)


# ── parse_myab_csv ──

def test_basic_ei_rows():
    """E 與 I 類型正常解析。"""
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,-20,豆漿,",
        "2025/12/02,I,薪資,,A-現金,50000,薪水,",
    )
    result = ie.parse_myab_csv(content)
    assert result["total_count"] == 2
    assert result["filtered_count"] == 0
    rows = result["rows"]
    assert len(rows) == 2

    e = rows[0]
    assert e["日期"] == "2025-12-01"
    assert e["類型"] == "E"
    assert e["類別主類"] == "餐飲費"
    assert e["類別次類"] == "早餐"
    assert e["金額"] == "20"          # 取絕對值
    assert e["明細"] == "豆漿"
    assert e["備註"] == ""
    assert len(e["id"]) == 8
    assert "T" in e["建立時間"]

    i = rows[1]
    assert i["類型"] == "I"
    assert i["金額"] == "50000"
    assert i["類別次類"] == ""


def test_al_filtered():
    """A/L 類型被過濾，不出現在 rows。"""
    content = _csv(
        "2025/12/01,A,現金,,Equity,0,初值,",
        "2025/12/01,L,信用卡,,Equity,0,初值,",
        "2025/12/01,E,餐飲費,早餐,A-現金,-20,,",
    )
    result = ie.parse_myab_csv(content)
    assert result["total_count"] == 3
    assert result["filtered_count"] == 2
    assert len(result["rows"]) == 1
    assert result["rows"][0]["類型"] == "E"


def test_bom_handling():
    """UTF-8 BOM 自動去除，標頭正確解析。"""
    content = _csv_bom("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    result = ie.parse_myab_csv(content)
    assert len(result["rows"]) == 1
    assert result["rows"][0]["日期"] == "2025-12-01"


def test_date_conversion():
    """YYYY/MM/DD → YYYY-MM-DD。"""
    content = _csv("2026/04/09,E,餐飲費,早餐,A-現金,-50,,")
    result = ie.parse_myab_csv(content)
    assert result["rows"][0]["日期"] == "2026-04-09"


def test_amount_absolute_value():
    """負金額取絕對值；正金額不變。"""
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,-130,,",
        "2025/12/01,I,薪資,,A-現金,50000,,",
    )
    rows = ie.parse_myab_csv(content)["rows"]
    assert rows[0]["金額"] == "130"
    assert rows[1]["金額"] == "50000"


def test_sub_category_empty():
    """次類空白保留為空字串。"""
    content = _csv("2025/12/01,I,薪資,,A-現金,50000,,")
    rows = ie.parse_myab_csv(content)["rows"]
    assert rows[0]["類別次類"] == ""


def test_whitespace_stripped():
    """欄位前後空白被 strip。"""
    content = _csv("2025/12/01,E, 餐飲費 , 早餐 ,A-現金,-20, 豆漿 , 備註 ")
    rows = ie.parse_myab_csv(content)["rows"]
    assert rows[0]["類別主類"] == "餐飲費"
    assert rows[0]["類別次類"] == "早餐"
    assert rows[0]["明細"] == "豆漿"
    assert rows[0]["備註"] == "備註"


def test_empty_csv():
    """只有 header，無資料列。"""
    result = ie.parse_myab_csv(_HEADER.encode("utf-8"))
    assert result["total_count"] == 0
    assert result["filtered_count"] == 0
    assert result["rows"] == []


def test_all_filtered():
    """全部為 A/L，rows 為空。"""
    content = _csv(
        "2025/12/01,A,現金,,Equity,0,,",
        "2025/12/01,L,信用卡,,Equity,0,,",
    )
    result = ie.parse_myab_csv(content)
    assert result["total_count"] == 2
    assert result["filtered_count"] == 2
    assert result["rows"] == []


def test_amount_zero_filtered():
    """金額為 0 的 E/I 行計入 filtered_count，不進入 rows。"""
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,0,,",    # 金額=0，應過濾
        "2025/12/01,E,餐飲費,午餐,A-現金,-50,,",  # 正常
    )
    result = ie.parse_myab_csv(content)
    assert result["total_count"] == 2
    assert result["filtered_count"] == 1
    assert len(result["rows"]) == 1
    assert result["rows"][0]["類別次類"] == "午餐"


def test_amount_invalid_string_filtered():
    """金額無法解析（空白）的行計入 filtered_count。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,,,")
    result = ie.parse_myab_csv(content)
    assert result["filtered_count"] == 1
    assert result["rows"] == []


def test_invalid_date_empty_filtered():
    """日期為空字串的行計入 filtered_count。"""
    content = _csv(",E,餐飲費,早餐,A-現金,-20,,")
    result = ie.parse_myab_csv(content)
    assert result["filtered_count"] == 1
    assert result["rows"] == []


def test_invalid_date_format_filtered():
    """日期格式不符 YYYY-MM-DD（轉換後）的行計入 filtered_count。"""
    content = _csv("12/01/2025,E,餐飲費,早餐,A-現金,-20,,")   # MM/DD/YYYY 格式
    result = ie.parse_myab_csv(content)
    assert result["filtered_count"] == 1
    assert result["rows"] == []


def test_total_equals_filtered_plus_rows():
    """total_count == filtered_count + len(rows) 等式成立。"""
    content = _csv(
        "2025/12/01,A,現金,,Equity,0,,",       # A/L → filtered
        "2025/12/01,E,餐飲費,早餐,,0,,",        # amount=0 → filtered
        ",E,餐飲費,早餐,,-20,,",                # 空日期 → filtered
        "2025/12/01,E,餐飲費,午餐,,-50,,",      # 正常
        "2025/12/02,I,薪資,,, 50000,,",         # 正常
    )
    result = ie.parse_myab_csv(content)
    assert result["total_count"] == result["filtered_count"] + len(result["rows"])


def test_id_unique():
    """每筆 id 唯一。"""
    lines = [f"2025/12/0{i},E,餐飲費,早餐,A-現金,-20,," for i in range(1, 6)]
    rows = ie.parse_myab_csv(_csv(*lines))["rows"]
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))


# ── extract_categories ──

def test_extract_categories_dedup():
    """相同 (類型,主類,次類) 只保留一筆。"""
    rows = [
        {"類型": "E", "類別主類": "餐飲費", "類別次類": "早餐"},
        {"類型": "E", "類別主類": "餐飲費", "類別次類": "早餐"},
        {"類型": "E", "類別主類": "餐飲費", "類別次類": "午餐"},
        {"類型": "I", "類別主類": "薪資",   "類別次類": ""},
    ]
    cats = ie.extract_categories(rows)
    assert len(cats) == 3
    assert {"類型": "E", "主類": "餐飲費", "次類": "早餐"} in cats
    assert {"類型": "I", "主類": "薪資",   "次類": ""}     in cats


def test_extract_categories_order():
    """插入順序保留（第一次出現順序）。"""
    rows = [
        {"類型": "I", "類別主類": "薪資",   "類別次類": ""},
        {"類型": "E", "類別主類": "餐飲費", "類別次類": "早餐"},
    ]
    cats = ie.extract_categories(rows)
    assert cats[0]["主類"] == "薪資"
    assert cats[1]["主類"] == "餐飲費"
