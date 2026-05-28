"""
Step 5 功能需求測試 — 涵蓋規格 5.5 / 6.1 / 6.1a / 6.1b / 6.2 / 4.4 全部需求

FR-1  Preview 不寫入 DB
FR-2  欄位對映（6.1）：帳戶丟棄、id格式、建立時間、日期轉換、金額絕對值
FR-3  A/L 過濾（6.1a）：不進 DB、不進 categories
FR-4  分類聯集累積（6.1b）：舊分類保留、多次匯入累積、無重複
FR-5  去重鍵 6 欄（6.2）：各欄位獨立驗證、備註不在鍵中、批次內自去重
FR-6  Preview/Confirm 流程：token 格式、TTL、單次使用、response shape
FR-7  匯入後 DB 完整性：欄位正確、分類寫入順序
"""
import re
import sys
import time
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

_HEADER = "日期,類型,類別主類,類別次類,帳戶,金額,明細,備註\r\n"


def _csv(*rows: str) -> bytes:
    return (_HEADER + "\r\n".join(rows) + "\r\n").encode("utf-8")


def _upload(client, content: bytes, filename: str = "test.csv"):
    return client.post(
        "/api/import/preview",
        files={"file": (filename, content, "text/csv")},
    )


def _confirm(client, token: str):
    return client.post("/api/import/confirm", json={"preview_token": token})


def _full_import(client, content: bytes):
    """Preview → Confirm，回傳 confirm 的 response dict。"""
    token = _upload(client, content).json()["preview_token"]
    return _confirm(client, token).json()


# ── FR-1：Preview 不寫入 DB ────────────────────────────────────────────────

def test_fr1_preview_no_db_write(client):
    """Preview 後 DB 交易數為 0，categories 也為空。"""
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,-20,豆漿,",
        "2025/12/01,I,薪資,,A-現金,50000,,",
    )
    _upload(client, content)
    assert dm.query_transactions()["total"] == 0
    assert dm.get_categories() == []


def test_fr1_preview_twice_no_db_write(client):
    """連續兩次 preview 均不寫入。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    _upload(client, content)
    _upload(client, content)
    assert dm.query_transactions()["total"] == 0


# ── FR-2：欄位對映（規格 6.1）────────────────────────────────────────────

def test_fr2_account_column_not_stored(client):
    """帳戶欄不寫入 DB（main_db.csv 欄位不含帳戶）。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-100,早餐,備註")
    _full_import(client, content)
    rows = dm._read_csv(dm.MAIN_DB)
    assert len(rows) == 1
    assert "帳戶" not in rows[0]


def test_fr2_id_format_8hex(client):
    """匯入後交易 id 為 8 碼小寫 hex。"""
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,-100,,",
        "2025/12/02,I,薪資,,A-現金,50000,,",
    )
    _full_import(client, content)
    for row in dm._read_csv(dm.MAIN_DB):
        assert re.fullmatch(r"[0-9a-f]{8}", row["id"]), f"id 格式錯誤：{row['id']}"


def test_fr2_id_unique_across_batch(client):
    """同批次匯入的每筆交易 id 不重複。"""
    rows = [f"2025/12/0{i},E,餐飲費,早餐,A-現金,-20,," for i in range(1, 6)]
    _full_import(client, _csv(*rows))
    ids = [r["id"] for r in dm._read_csv(dm.MAIN_DB)]
    assert len(ids) == len(set(ids))


def test_fr2_created_at_iso_format(client):
    """建立時間格式為 YYYY-MM-DDTHH:MM:SSZ（UTC）。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-100,,")
    _full_import(client, content)
    iso_re = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    for row in dm._read_csv(dm.MAIN_DB):
        assert iso_re.match(row["建立時間"]), f"建立時間格式錯誤：{row['建立時間']}"


def test_fr2_same_batch_share_created_at(client):
    """同批次的所有交易共用相同建立時間（批次原子性識別）。"""
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,-20,,",
        "2025/12/02,I,薪資,,A-現金,50000,,",
        "2025/12/03,E,交通費,捷運,A-現金,-30,,",
    )
    _full_import(client, content)
    ts_set = {r["建立時間"] for r in dm._read_csv(dm.MAIN_DB)}
    assert len(ts_set) == 1, f"同批次應共用一個建立時間，實際有 {ts_set}"


def test_fr2_date_stored_as_iso(client):
    """DB 中日期為 YYYY-MM-DD，非原始的 YYYY/MM/DD。"""
    content = _csv("2026/04/09,E,餐飲費,早餐,A-現金,-100,,")
    _full_import(client, content)
    rows = dm._read_csv(dm.MAIN_DB)
    assert rows[0]["日期"] == "2026-04-09"
    assert "/" not in rows[0]["日期"]


def test_fr2_amount_stored_as_positive_integer(client):
    """DB 中金額為正整數字串（負號已去除）。"""
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,-130,,",   # 負數
        "2025/12/01,I,薪資,,A-現金,50000,,",         # 正數
    )
    _full_import(client, content)
    for row in dm._read_csv(dm.MAIN_DB):
        assert int(row["金額"]) > 0
        assert not row["金額"].startswith("-")


def test_fr2_type_ei_preserved(client):
    """DB 中類型欄位保留為 E 或 I。"""
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,-100,,",
        "2025/12/02,I,薪資,,A-現金,50000,,",
    )
    _full_import(client, content)
    types = {r["類型"] for r in dm._read_csv(dm.MAIN_DB)}
    assert types == {"E", "I"}


def test_fr2_all_main_fields_correct(client):
    """各欄位值完整且正確寫入（端到端欄位驗證）。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-130,豆漿早餐,測試備註")
    _full_import(client, content)
    r = dm._read_csv(dm.MAIN_DB)[0]
    assert r["日期"]     == "2025-12-01"
    assert r["類型"]     == "E"
    assert r["類別主類"] == "餐飲費"
    assert r["類別次類"] == "早餐"
    assert r["金額"]     == "130"
    assert r["明細"]     == "豆漿早餐"
    assert r["備註"]     == "測試備註"
    assert "帳戶" not in r


# ── FR-3：A/L 過濾（規格 6.1a）────────────────────────────────────────────

def test_fr3_a_type_not_in_db(client):
    """A（資產）類型記錄不寫入 DB。"""
    content = _csv(
        "2025/12/01,A,現金,,Equity,0,,",
        "2025/12/01,E,餐飲費,早餐,A-現金,-20,,",
    )
    _full_import(client, content)
    assert dm.query_transactions()["total"] == 1
    assert dm._read_csv(dm.MAIN_DB)[0]["類型"] == "E"


def test_fr3_l_type_not_in_db(client):
    """L（負債）類型記錄不寫入 DB。"""
    content = _csv(
        "2025/12/01,L,信用卡,,Equity,0,,",
        "2025/12/01,I,薪資,,A-現金,50000,,",
    )
    _full_import(client, content)
    assert dm.query_transactions()["total"] == 1
    assert dm._read_csv(dm.MAIN_DB)[0]["類型"] == "I"


def test_fr3_al_categories_not_added_to_csv(client):
    """A/L 行的分類名稱不寫入 categories.csv。"""
    content = _csv(
        "2025/12/01,A,現金,,Equity,0,,",       # 「現金」是 A 類分類，不應加入
        "2025/12/01,L,信用卡,,Equity,0,,",     # 「信用卡」是 L 類分類，不應加入
        "2025/12/01,E,餐飲費,早餐,A-現金,-20,,",
    )
    _full_import(client, content)
    main_cats = {c["主類"] for c in dm.get_categories()}
    assert "現金" not in main_cats
    assert "信用卡" not in main_cats
    assert "餐飲費" in main_cats


def test_fr3_al_not_in_preview_new_categories(client):
    """預覽結果的 new_categories 不包含 A/L 行所屬分類。"""
    content = _csv(
        "2025/12/01,A,現金,,Equity,0,,",
        "2025/12/01,E,餐飲費,早餐,A-現金,-20,,",
    )
    data = _upload(client, content).json()
    new_cat_mains = {c["主類"] for c in data["new_categories"]}
    assert "現金" not in new_cat_mains
    assert "餐飲費" in new_cat_mains


def test_fr3_all_al_preview_still_200(client):
    """全部為 A/L 的 CSV，preview 仍回 200（to_import=0）。"""
    content = _csv(
        "2025/12/01,A,現金,,Equity,0,,",
        "2025/12/01,L,信用卡,,Equity,0,,",
    )
    res = _upload(client, content)
    assert res.status_code == 200
    s = res.json()["summary"]
    assert s["filtered"] == 2
    assert s["to_import"] == 0


# ── FR-4：分類聯集累積（規格 6.1b）────────────────────────────────────────

def test_fr4_existing_categories_preserved(client):
    """已存在的分類在匯入後仍保留（不被刪除）。"""
    dm.add_category("E", "舊分類", "舊次類")
    dm.add_category("I", "舊收入", "")
    content = _csv("2025/12/01,E,新分類,新次類,A-現金,-100,,")
    _full_import(client, content)
    main_cats = {c["主類"] for c in dm.get_categories()}
    assert "舊分類" in main_cats
    assert "舊收入" in main_cats
    assert "新分類" in main_cats


def test_fr4_multiple_imports_accumulate_categories(client):
    """兩次不同 CSV 匯入，分類聯集累積。"""
    _full_import(client, _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,"))
    _full_import(client, _csv("2025/12/02,E,交通費,捷運,A-現金,-50,,"))
    main_cats = {c["主類"] for c in dm.get_categories()}
    assert "餐飲費" in main_cats
    assert "交通費" in main_cats


def test_fr4_no_duplicate_categories_on_reimport(client):
    """重複匯入同一 CSV，categories.csv 無重複列。"""
    for _ in range(3):
        _full_import(client, _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,"))
    cats = dm.get_categories()
    assert len(cats) == 1
    assert cats[0]["類型"] == "E"
    assert cats[0]["主類"] == "餐飲費"
    assert cats[0]["次類"] == "早餐"


def test_fr4_new_categories_count_second_import_is_zero(client):
    """第二次匯入相同分類，new_categories_count=0。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    _full_import(client, content)
    content2 = _csv("2025/12/02,E,餐飲費,早餐,A-現金,-30,,")  # 同分類、不同日期
    data2 = _upload(client, content2).json()
    assert data2["new_categories_count"] == 0
    assert data2["new_categories"] == []


# ── FR-5：去重鍵 6 欄（規格 6.2）────────────────────────────────────────

def _seed(dm_module):
    """建立基準交易（dedup 對照用）。"""
    dm_module.add_category("E", "餐飲費", "早餐")
    dm_module.add_transaction(
        "2025-12-01", "E", "餐飲費", "早餐", 100, "早餐豆漿", ""
    )


def test_fr5_dedup_exact_match(client):
    """六欄完全相同 → duplicates=1，to_import=0。"""
    _seed(dm)
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-100,早餐豆漿,")
    s = _upload(client, content).json()["summary"]
    assert s["duplicates"] == 1
    assert s["to_import"] == 0


def test_fr5_different_date_not_dup(client):
    """日期不同 → 非重複。"""
    _seed(dm)
    s = _upload(client, _csv("2025/12/02,E,餐飲費,早餐,A-現金,-100,早餐豆漿,")).json()["summary"]
    assert s["to_import"] == 1 and s["duplicates"] == 0


def test_fr5_different_type_not_dup(client):
    """類型不同（E→I）→ 非重複。"""
    _seed(dm)
    dm.add_category("I", "餐飲費", "早餐")
    s = _upload(client, _csv("2025/12/01,I,餐飲費,早餐,A-現金,100,早餐豆漿,")).json()["summary"]
    assert s["to_import"] == 1 and s["duplicates"] == 0


def test_fr5_different_main_category_not_dup(client):
    """主類不同 → 非重複。"""
    _seed(dm)
    dm.add_category("E", "其他費", "早餐")
    s = _upload(client, _csv("2025/12/01,E,其他費,早餐,A-現金,-100,早餐豆漿,")).json()["summary"]
    assert s["to_import"] == 1 and s["duplicates"] == 0


def test_fr5_different_sub_category_not_dup(client):
    """次類不同 → 非重複。"""
    _seed(dm)
    dm.add_category("E", "餐飲費", "午餐")
    s = _upload(client, _csv("2025/12/01,E,餐飲費,午餐,A-現金,-100,早餐豆漿,")).json()["summary"]
    assert s["to_import"] == 1 and s["duplicates"] == 0


def test_fr5_different_amount_not_dup(client):
    """金額不同 → 非重複。"""
    _seed(dm)
    s = _upload(client, _csv("2025/12/01,E,餐飲費,早餐,A-現金,-200,早餐豆漿,")).json()["summary"]
    assert s["to_import"] == 1 and s["duplicates"] == 0


def test_fr5_different_detail_not_dup(client):
    """明細不同 → 非重複。"""
    _seed(dm)
    s = _upload(client, _csv("2025/12/01,E,餐飲費,早餐,A-現金,-100,不同明細,")).json()["summary"]
    assert s["to_import"] == 1 and s["duplicates"] == 0


def test_fr5_note_not_in_dedup_key(client):
    """備註不在去重鍵中，只改備註 → 仍為重複。"""
    _seed(dm)
    # 六欄相同，只有備註不同
    s = _upload(client, _csv("2025/12/01,E,餐飲費,早餐,A-現金,-100,早餐豆漿,不同備註")).json()["summary"]
    assert s["duplicates"] == 1
    assert s["to_import"] == 0


def test_fr5_account_not_in_dedup_key(client):
    """帳戶欄不在去重鍵中，帳戶不同 → 仍為重複。"""
    _seed(dm)
    # 帳戶從 A-現金 改為 A-銀行
    s = _upload(client, _csv("2025/12/01,E,餐飲費,早餐,A-銀行,-100,早餐豆漿,")).json()["summary"]
    assert s["duplicates"] == 1
    assert s["to_import"] == 0


def test_fr5_batch_self_dedup(client):
    """CSV 內同一行出現 3 次，只匯入 1 筆，重複 2 筆。"""
    row = "2025/12/01,E,餐飲費,早餐,A-現金,-100,豆漿,"
    content = _csv(row, row, row)
    s = _upload(client, content).json()["summary"]
    assert s["to_import"] == 1
    assert s["duplicates"] == 2


def test_fr5_dedup_confirmed_in_db(client):
    """Confirm 後只有 1 筆寫入，重複的不寫入。"""
    _seed(dm)
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,-100,早餐豆漿,",  # dup
        "2025/12/02,E,餐飲費,早餐,A-現金,-50,午餐,",        # new
    )
    _full_import(client, content)
    assert dm.query_transactions()["total"] == 2   # 原有 1 筆 + 新增 1 筆


# ── FR-6：Preview/Confirm 流程（規格 4.4）─────────────────────────────────

def test_fr6_token_is_32hex(client):
    """preview_token 為 32 碼小寫 hex（UUID4 hex 格式）。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    token = _upload(client, content).json()["preview_token"]
    assert re.fullmatch(r"[0-9a-f]{32}", token), f"token 格式錯誤：{token}"


def test_fr6_token_ttl_600s(client):
    """preview_token 的 TTL 為 600 秒。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    t0 = time.time()
    token = _upload(client, content).json()["preview_token"]
    t1 = time.time()
    expires = _app_module._preview_store[token]["expires"]
    # 容差 1 秒
    assert t0 + 600 <= expires <= t1 + 601


def test_fr6_token_single_use(client):
    """同一 token 第二次 confirm → 410。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    token = _upload(client, content).json()["preview_token"]
    _confirm(client, token)
    assert _confirm(client, token).status_code == 410


def test_fr6_token_cleared_after_confirm(client):
    """Confirm 成功後 token 從 store 移除。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    token = _upload(client, content).json()["preview_token"]
    _confirm(client, token)
    assert token not in _app_module._preview_store


def test_fr6_expired_token_returns_410(client):
    """強制過期的 token → 410 Gone。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    token = _upload(client, content).json()["preview_token"]
    _app_module._preview_store[token]["expires"] = time.time() - 1
    assert _confirm(client, token).status_code == 410


def test_fr6_nonexistent_token_returns_410(client):
    """不存在的 token → 410。"""
    assert _confirm(client, "0" * 32).status_code == 410


def test_fr6_confirm_response_shape(client):
    """Confirm 回傳 {added: int, skipped: int, new_categories: int}。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    token = _upload(client, content).json()["preview_token"]
    data = _confirm(client, token).json()
    assert isinstance(data.get("added"), int)
    assert isinstance(data.get("skipped"), int)
    assert isinstance(data.get("new_categories"), int)


def test_fr6_preview_summary_shape(client):
    """Preview 回傳 summary 含 total/filtered/to_import/duplicates。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    data = _upload(client, content).json()
    s = data["summary"]
    for key in ("total", "filtered", "to_import", "duplicates"):
        assert key in s and isinstance(s[key], int), f"summary 缺少 {key}"


def test_fr6_preview_returns_all_new_categories(client):
    """Preview new_categories 包含 CSV 中所有不存在於 categories.csv 的分類。"""
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,-20,,",
        "2025/12/02,E,餐飲費,午餐,A-現金,-80,,",
        "2025/12/03,I,薪資,,A-現金,50000,,",
    )
    data = _upload(client, content).json()
    assert data["new_categories_count"] == 3
    found = {(c["類型"], c["主類"], c["次類"]) for c in data["new_categories"]}
    assert found == {("E", "餐飲費", "早餐"), ("E", "餐飲費", "午餐"), ("I", "薪資", "")}


# ── FR-7：匯入後 DB 完整性──────────────────────────────────────────────────

def test_fr7_categories_written_before_transactions(client):
    """Confirm 先寫分類後寫交易，交易的分類在 categories.csv 中存在。"""
    content = _csv("2025/12/01,E,全新分類,全新次類,A-現金,-100,,")
    _full_import(client, content)
    assert dm.category_exists("E", "全新分類", "全新次類")
    assert dm.query_transactions()["total"] == 1


def test_fr7_all_new_categories_in_csv(client):
    """Confirm 後所有 new_categories 均出現在 categories.csv。"""
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,-20,,",
        "2025/12/01,E,餐飲費,午餐,A-現金,-80,,",
        "2025/12/02,I,薪資,,A-現金,50000,,",
    )
    result = _full_import(client, content)
    assert result["new_categories"] == 3
    assert dm.category_exists("E", "餐飲費", "早餐")
    assert dm.category_exists("E", "餐飲費", "午餐")
    assert dm.category_exists("I", "薪資", "")


def test_fr7_multiple_imports_accumulate_transactions(client):
    """多次不同 CSV 匯入，交易筆數累積。"""
    _full_import(client, _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,"))
    _full_import(client, _csv("2025/12/02,E,餐飲費,早餐,A-現金,-50,,"))
    assert dm.query_transactions()["total"] == 2


def test_fr7_preview_sample_max_5(client):
    """preview sample_transactions 最多 5 筆。"""
    rows = [f"2025/12/0{i},E,餐飲費,早餐,A-現金,-20,," for i in range(1, 9)]
    data = _upload(client, _csv(*rows)).json()
    assert len(data["sample_transactions"]) == 5


def test_fr7_preview_date_range_only_new(client):
    """date_range 只計算新交易（非重複）的日期範圍。"""
    dm.add_category("E", "餐飲費", "早餐")
    # 已存在早期交易
    dm.add_transaction("2024-01-01", "E", "餐飲費", "早餐", 100, "舊交易", "")
    content = _csv(
        "2024/01/01,E,餐飲費,早餐,A-現金,-100,舊交易,",  # dup → 不計入 date_range
        "2025/06/15,E,餐飲費,早餐,A-現金,-50,新交易,",   # new
        "2025/12/31,E,餐飲費,早餐,A-現金,-80,新交易2,",  # new
    )
    data = _upload(client, content).json()
    # date_range 只包含新交易
    assert data["date_range"]["min"] == "2025-06-15"
    assert data["date_range"]["max"] == "2025-12-31"
