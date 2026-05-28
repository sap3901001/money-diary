"""
Step 3 補充測試（DL_Step3_自動測試計畫，36 tests）
獨立於 test_list_filtering.py，涵蓋 response shape、篩選缺口、排序深度、
摘要跨頁一致性、PUT 驗證邊界、特殊字元、date_range、資料完整性。
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
    dm.add_category("I", "獎金", "")


@pytest.fixture
def client():
    from app import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def seed(client):
    """建立 5 筆測試資料"""
    dm.add_transaction("2026-01-05", "E", "餐飲費", "早餐", 80, "豆漿", "")
    dm.add_transaction("2026-01-10", "E", "餐飲費", "午餐", 120, "便當", "")
    dm.add_transaction("2026-01-15", "E", "交通", "", 50, "捷運", "")
    dm.add_transaction("2026-01-20", "I", "薪資", "", 50000, "", "")
    dm.add_transaction("2026-02-01", "E", "餐飲費", "早餐", 90, "稀飯", "")


# ===========================================================================
# 一、Response Shape 與資料合約（S-01 ~ S-06）
# ===========================================================================

EXPECTED_TOP_KEYS = {"items", "total", "page", "size", "pages", "summary"}
EXPECTED_ITEM_KEYS = {
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


def test_s01_response_top_level_keys(client, seed):
    """S-01：GET /api/transactions response 頂層欄位完整"""
    res = client.get("/api/transactions")
    assert res.status_code == 200
    assert EXPECTED_TOP_KEYS == set(res.json().keys())


def test_s02_item_keys_complete(client, seed):
    """S-02：items[] 每筆交易欄位完整（9 欄）"""
    items = client.get("/api/transactions").json()["items"]
    assert len(items) > 0
    for item in items:
        assert EXPECTED_ITEM_KEYS == set(
            item.keys()
        ), f"缺欄位: {EXPECTED_ITEM_KEYS - set(item.keys())}"


def test_s03_amount_is_string(client, seed):
    """S-03：金額欄位型別為字串"""
    items = client.get("/api/transactions").json()["items"]
    for item in items:
        assert isinstance(item["金額"], str)


def test_s04_get_single_transaction(client):
    """S-04：GET /api/transactions/{id} 回傳完整單筆"""
    row = dm.add_transaction("2026-03-01", "E", "餐飲費", "早餐", 100, "測試", "備")
    res = client.get(f"/api/transactions/{row['id']}")
    assert res.status_code == 200
    data = res.json()
    assert EXPECTED_ITEM_KEYS == set(data.keys())
    assert data["日期"] == "2026-03-01"
    assert data["金額"] == "100"
    assert data["明細"] == "測試"
    assert data["備註"] == "備"


def test_s05_get_nonexistent_404(client):
    """S-05：GET /api/transactions/{id} 不存在回 404"""
    res = client.get("/api/transactions/nonexistent")
    assert res.status_code == 404
    assert "detail" in res.json()


def test_s06_delete_204_no_body(client):
    """S-06：DELETE 回 204 且無 body"""
    row = dm.add_transaction("2026-03-01", "E", "餐飲費", "早餐", 100, "", "")
    res = client.delete(f"/api/transactions/{row['id']}")
    assert res.status_code == 204
    assert res.content == b""


# ===========================================================================
# 二、篩選缺口（F-01 ~ F-08）
# ===========================================================================


def test_f01_keyword_matches_note(client):
    """F-01：keyword 搜尋備註欄位"""
    dm.add_transaction("2026-03-01", "E", "餐飲費", "早餐", 100, "無關明細", "特殊備註")
    res = client.get("/api/transactions?keyword=特殊備註")
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["備註"] == "特殊備註"


def test_f02_keyword_case_insensitive(client):
    """F-02：keyword 大小寫不敏感"""
    dm.add_transaction("2026-03-01", "E", "餐飲費", "早餐", 100, "Hello ABC World", "")
    res = client.get("/api/transactions?keyword=abc")
    assert res.json()["total"] == 1


def test_f03_from_equals_to_same_day(client):
    """F-03：from = to（同一天）僅回傳該日交易"""
    dm.add_transaction("2026-05-15", "E", "餐飲費", "早餐", 100, "", "")
    dm.add_transaction("2026-05-16", "E", "餐飲費", "午餐", 200, "", "")
    res = client.get("/api/transactions?from=2026-05-15&to=2026-05-15")
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["日期"] == "2026-05-15"


def test_f04_from_greater_than_to(client, seed):
    """F-04：from > to（反向區間）回 0 筆"""
    res = client.get("/api/transactions?from=2026-12-31&to=2026-01-01")
    assert res.json()["total"] == 0
    assert res.json()["items"] == []


def test_f05_exact_amount(client):
    """F-05：amount_min = amount_max（精確金額）"""
    dm.add_transaction("2026-03-01", "E", "餐飲費", "早餐", 100, "", "")
    dm.add_transaction("2026-03-02", "E", "餐飲費", "午餐", 200, "", "")
    dm.add_transaction("2026-03-03", "E", "交通", "", 100, "", "")
    res = client.get("/api/transactions?amount_min=100&amount_max=100")
    assert res.json()["total"] == 2
    for item in res.json()["items"]:
        assert item["金額"] == "100"


def test_f06_sub_without_main_returns_422(client, seed):
    """F-06：僅指定 category_sub 不指定 category_main → 422"""
    res = client.get("/api/transactions?category_sub=早餐")
    assert res.status_code == 422


def test_f07_invalid_type_returns_422(client, seed):
    """F-07：type 傳無效值 → 422"""
    res = client.get("/api/transactions?type=X")
    assert res.status_code == 422


def test_f08_no_filters_returns_all(client, seed):
    """F-08：無篩選條件回傳全部資料"""
    res = client.get("/api/transactions")
    data = res.json()
    assert data["total"] == 5
    assert data["summary"]["total_count"] == 5


# ===========================================================================
# 三、排序深度驗證（O-01 ~ O-03）
# ===========================================================================


def test_o01_same_date_all_returned(client):
    """O-01：同日期多筆全部回傳（不強制建立時間排序，因精度為秒）"""
    dm.add_transaction("2026-06-01", "E", "餐飲費", "早餐", 100, "第一筆", "")
    dm.add_transaction("2026-06-01", "E", "餐飲費", "午餐", 200, "第二筆", "")
    dm.add_transaction("2026-06-01", "E", "交通", "", 50, "第三筆", "")
    items = client.get("/api/transactions?from=2026-06-01&to=2026-06-01").json()[
        "items"
    ]
    assert len(items) == 3
    assert all(t["日期"] == "2026-06-01" for t in items)
    assert {t["明細"] for t in items} == {"第一筆", "第二筆", "第三筆"}


def test_o02_cross_year_sort(client):
    """O-02：跨月跨年排序正確（2025-12-31 排在 2026-01-01 之後）"""
    dm.add_transaction("2025-12-31", "E", "餐飲費", "早餐", 100, "舊年", "")
    dm.add_transaction("2026-01-01", "E", "餐飲費", "午餐", 200, "新年", "")
    items = client.get("/api/transactions").json()["items"]
    dates = [t["日期"] for t in items]
    assert dates.index("2026-01-01") < dates.index("2025-12-31")


def test_o03_sort_preserved_after_filter(client):
    """O-03：排序不受篩選影響"""
    dm.add_transaction("2026-03-01", "E", "餐飲費", "早餐", 100, "", "")
    dm.add_transaction("2026-03-15", "E", "餐飲費", "午餐", 200, "", "")
    dm.add_transaction("2026-03-28", "E", "餐飲費", "早餐", 150, "", "")
    items = client.get("/api/transactions?category_main=餐飲費").json()["items"]
    dates = [t["日期"] for t in items]
    assert dates == sorted(dates, reverse=True)


# ===========================================================================
# 四、摘要 summary 跨頁一致性（M-01 ~ M-03）
# ===========================================================================


def test_m01_summary_covers_all_filtered(client):
    """M-01：summary 統計涵蓋全部篩選結果而非僅當頁"""
    for i in range(10):
        dm.add_transaction("2026-04-01", "E", "餐飲費", "早餐", 100, f"item{i}", "")
    res = client.get("/api/transactions?from=2026-04-01&to=2026-04-01&size=3&page=1")
    data = res.json()
    assert len(data["items"]) == 3  # 當頁只有 3 筆
    assert data["summary"]["total_count"] == 10  # 摘要涵蓋全部 10 筆


def test_m02_summary_consistent_across_pages(client):
    """M-02：summary 在不同 page 間數值一致"""
    for i in range(6):
        dm.add_transaction("2026-04-01", "E", "餐飲費", "早餐", 100, f"item{i}", "")
    s1 = client.get("/api/transactions?size=3&page=1").json()["summary"]
    s2 = client.get("/api/transactions?size=3&page=2").json()["summary"]
    assert s1 == s2


def test_m03_net_negative_for_expense_only(client):
    """M-03：純支出場景 net 為負"""
    dm.add_transaction("2026-04-01", "E", "餐飲費", "早餐", 100, "", "")
    dm.add_transaction("2026-04-02", "E", "餐飲費", "午餐", 200, "", "")
    s = client.get("/api/transactions?from=2026-04-01&to=2026-04-30").json()["summary"]
    assert s["total_income"] == 0
    assert s["total_expense"] == 300
    assert s["net"] == -300


# ===========================================================================
# 五、PUT 驗證邊界（P-01 ~ P-06）
# ===========================================================================


@pytest.fixture
def one_tx():
    """建立一筆交易供 PUT 測試"""
    return dm.add_transaction("2026-03-01", "E", "餐飲費", "早餐", 100, "原始", "")


def _put(client, tx_id, **overrides):
    body = {
        "日期": "2026-03-01",
        "類型": "E",
        "類別主類": "餐飲費",
        "類別次類": "早餐",
        "金額": 100,
        "明細": "",
        "備註": "",
    }
    body.update(overrides)
    return client.put(f"/api/transactions/{tx_id}", json=body)


def test_p01_put_invalid_date_format(client, one_tx):
    """P-01：日期格式錯誤 → 422"""
    res = _put(client, one_tx["id"], **{"日期": "2026/01/01"})
    assert res.status_code == 422


def test_p02_put_invalid_type(client, one_tx):
    """P-02：類型非 E/I → 422"""
    res = _put(client, one_tx["id"], **{"類型": "A"})
    assert res.status_code == 422


def test_p03_put_amount_zero(client, one_tx):
    """P-03：金額 = 0 → 422"""
    res = _put(client, one_tx["id"], **{"金額": 0})
    assert res.status_code == 422


def test_p04_put_amount_negative(client, one_tx):
    """P-04：金額 = -100 → 422"""
    res = _put(client, one_tx["id"], **{"金額": -100})
    assert res.status_code == 422


def test_p05_put_missing_required_field(client, one_tx):
    """P-05：缺少必填欄位（無日期）→ 422"""
    body = {"類型": "E", "類別主類": "餐飲費", "類別次類": "早餐", "金額": 100}
    res = client.put(f"/api/transactions/{one_tx['id']}", json=body)
    assert res.status_code == 422


def test_p06_put_change_type_category_match(client, one_tx):
    """P-06：PUT 將類型從 E 改為 I，分類需匹配"""
    # I 類無「餐飲費/早餐」→ 422
    res = _put(
        client, one_tx["id"], **{"類型": "I", "類別主類": "餐飲費", "類別次類": "早餐"}
    )
    assert res.status_code == 422

    # I 類有「薪資/」→ 200
    res = _put(
        client, one_tx["id"], **{"類型": "I", "類別主類": "薪資", "類別次類": ""}
    )
    assert res.status_code == 200
    assert res.json()["類型"] == "I"
    assert res.json()["類別主類"] == "薪資"


# ===========================================================================
# 六、特殊字元與 CSV 安全（C-01 ~ C-04）
# ===========================================================================


def test_c01_detail_with_comma(client):
    """C-01：明細含逗號（CSV 邊界）"""
    res = client.post(
        "/api/transactions",
        json={
            "日期": "2026-03-01",
            "類型": "E",
            "類別主類": "餐飲費",
            "類別次類": "早餐",
            "金額": 100,
            "明細": "早餐,午餐",
            "備註": "",
        },
    )
    assert res.status_code == 201
    tx_id = res.json()["id"]
    got = client.get(f"/api/transactions/{tx_id}").json()
    assert got["明細"] == "早餐,午餐"


def test_c02_detail_with_double_quotes(client):
    """C-02：明細含雙引號（CSV escape）"""
    detail = '他說"你好"'
    res = client.post(
        "/api/transactions",
        json={
            "日期": "2026-03-01",
            "類型": "E",
            "類別主類": "餐飲費",
            "類別次類": "早餐",
            "金額": 100,
            "明細": detail,
            "備註": "",
        },
    )
    assert res.status_code == 201
    got = client.get(f"/api/transactions/{res.json()['id']}").json()
    assert got["明細"] == detail


def test_c03_note_with_newline(client):
    """C-03：備註含換行符（RFC 4180 CSV round-trip）"""
    note = "line1\nline2"
    res = client.post(
        "/api/transactions",
        json={
            "日期": "2026-03-01",
            "類型": "E",
            "類別主類": "餐飲費",
            "類別次類": "早餐",
            "金額": 100,
            "明細": "",
            "備註": note,
        },
    )
    assert res.status_code == 201
    got = client.get(f"/api/transactions/{res.json()['id']}").json()
    assert got["備註"] == note


def test_c04_empty_string_preserved(client):
    """C-04：空字串存取一致"""
    res = client.post(
        "/api/transactions",
        json={
            "日期": "2026-03-01",
            "類型": "E",
            "類別主類": "餐飲費",
            "類別次類": "早餐",
            "金額": 100,
            "明細": "",
            "備註": "",
        },
    )
    assert res.status_code == 201
    got = client.get(f"/api/transactions/{res.json()['id']}").json()
    assert got["明細"] == ""
    assert got["備註"] == ""


# ===========================================================================
# 七、GET /api/transactions/date_range（D-01 ~ D-03）
# ===========================================================================


def test_d01_date_range_empty_db(client):
    """D-01：空資料庫"""
    res = client.get("/api/transactions/date_range")
    assert res.status_code == 200
    data = res.json()
    assert data["min"] is None
    assert data["max"] is None
    assert data["count"] == 0


def test_d02_date_range_single_record(client):
    """D-02：單筆資料"""
    dm.add_transaction("2026-07-15", "E", "餐飲費", "早餐", 100, "", "")
    data = client.get("/api/transactions/date_range").json()
    assert data["min"] == "2026-07-15"
    assert data["max"] == "2026-07-15"
    assert data["count"] == 1


def test_d03_date_range_multiple_months(client):
    """D-03：多筆跨月資料"""
    dm.add_transaction("2026-01-01", "E", "餐飲費", "早餐", 100, "", "")
    dm.add_transaction("2026-03-15", "E", "餐飲費", "午餐", 200, "", "")
    dm.add_transaction("2026-06-30", "I", "薪資", "", 50000, "", "")
    data = client.get("/api/transactions/date_range").json()
    assert data["min"] == "2026-01-01"
    assert data["max"] == "2026-06-30"
    assert data["count"] == 3


# ===========================================================================
# 八、資料完整性（I-01 ~ I-03）
# ===========================================================================


def test_i01_post_put_get_consistency(client):
    """I-01：POST → PUT → GET 資料一致"""
    res = client.post(
        "/api/transactions",
        json={
            "日期": "2026-03-01",
            "類型": "E",
            "類別主類": "餐飲費",
            "類別次類": "早餐",
            "金額": 100,
            "明細": "原始",
            "備註": "",
        },
    )
    tx_id = res.json()["id"]

    client.put(
        f"/api/transactions/{tx_id}",
        json={
            "日期": "2026-03-02",
            "類型": "E",
            "類別主類": "交通",
            "類別次類": "",
            "金額": 250,
            "明細": "修改後",
            "備註": "新備註",
        },
    )

    got = client.get(f"/api/transactions/{tx_id}").json()
    assert got["日期"] == "2026-03-02"
    assert got["類別主類"] == "交通"
    assert got["金額"] == "250"
    assert got["明細"] == "修改後"
    assert got["備註"] == "新備註"


def test_i02_post_delete_disappears(client):
    """I-02：POST → DELETE → list 確認消失"""
    res = client.post(
        "/api/transactions",
        json={
            "日期": "2026-03-01",
            "類型": "E",
            "類別主類": "餐飲費",
            "類別次類": "早餐",
            "金額": 100,
            "明細": "",
            "備註": "",
        },
    )
    tx_id = res.json()["id"]
    before = client.get("/api/transactions").json()["total"]

    client.delete(f"/api/transactions/{tx_id}")

    after = client.get("/api/transactions").json()["total"]
    assert after == before - 1
    assert client.get(f"/api/transactions/{tx_id}").status_code == 404


def test_i03_batch_post_order_and_summary(client):
    """I-03：批次 POST 5 筆 → list 順序與 summary 正確"""
    amounts = [100, 200, 300, 400, 500]
    for i, amt in enumerate(amounts):
        client.post(
            "/api/transactions",
            json={
                "日期": f"2026-04-{10+i:02d}",
                "類型": "E",
                "類別主類": "餐飲費",
                "類別次類": "早餐",
                "金額": amt,
                "明細": f"batch{i}",
                "備註": "",
            },
        )

    data = client.get("/api/transactions?from=2026-04-10&to=2026-04-14").json()
    assert data["total"] == 5
    # 日期 DESC
    dates = [t["日期"] for t in data["items"]]
    assert dates == sorted(dates, reverse=True)
    # summary
    assert data["summary"]["total_expense"] == sum(amounts)
    assert data["summary"]["total_income"] == 0
    assert data["summary"]["net"] == -sum(amounts)
