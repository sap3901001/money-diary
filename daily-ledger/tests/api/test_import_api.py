"""
Step 5 API 測試：匯入端點（AT-009, AT-010）
"""
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
    # 每個測試前清空 preview store
    _app_module._preview_store.clear()


@pytest.fixture
def client():
    from app import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── 測試用 CSV 工具 ──

_HEADER = "日期,類型,類別主類,類別次類,帳戶,金額,明細,備註\r\n"


def _csv(*rows: str) -> bytes:
    return (_HEADER + "\r\n".join(rows) + "\r\n").encode("utf-8")


def _upload(client, content: bytes, filename: str = "test.csv"):
    return client.post(
        "/api/import/preview",
        files={"file": (filename, content, "text/csv")},
    )


# ── AT-009：POST /api/import/preview ──

def test_preview_basic(client):
    """AT-009：正常預覽，回傳正確摘要結構。"""
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,-20,豆漿,",
        "2025/12/01,I,薪資,,A-現金,50000,,",
        "2025/12/01,A,現金,,Equity,0,,",   # 應被過濾
    )
    res = _upload(client, content)
    assert res.status_code == 200
    data = res.json()

    # 必要欄位存在
    assert "preview_token" in data
    assert "summary" in data
    assert "date_range" in data
    assert "new_categories" in data
    assert "new_categories_count" in data
    assert "sample_transactions" in data

    s = data["summary"]
    assert s["total"] == 3
    assert s["filtered"] == 1
    assert s["to_import"] == 2
    assert s["duplicates"] == 0


def test_preview_new_categories(client):
    """預覽回傳正確的新分類清單。"""
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,-20,,",
        "2025/12/01,E,餐飲費,午餐,A-現金,-80,,",
        "2025/12/02,I,薪資,,A-現金,50000,,",
    )
    res = _upload(client, content)
    data = res.json()
    assert data["new_categories_count"] == 3
    cats = {(c["類型"], c["主類"], c["次類"]) for c in data["new_categories"]}
    assert ("E", "餐飲費", "早餐") in cats
    assert ("E", "餐飲費", "午餐") in cats
    assert ("I", "薪資",   "")    in cats


def test_preview_existing_categories_not_in_new(client):
    """已存在的分類不出現在 new_categories。"""
    dm.add_category("E", "餐飲費", "早餐")
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    res = _upload(client, content)
    data = res.json()
    assert data["new_categories_count"] == 0
    assert data["new_categories"] == []


def test_preview_date_range(client):
    """date_range 回傳新交易的最小/最大日期。"""
    content = _csv(
        "2025/01/15,E,餐飲費,早餐,A-現金,-20,,",
        "2025/12/31,E,餐飲費,午餐,A-現金,-80,,",
    )
    res = _upload(client, content)
    data = res.json()
    assert data["date_range"]["min"] == "2025-01-15"
    assert data["date_range"]["max"] == "2025-12-31"


def test_preview_sample_max_5(client):
    """sample_transactions 最多回傳 5 筆。"""
    rows = [f"2025/12/0{i},E,餐飲費,早餐,A-現金,-20,," for i in range(1, 9)]
    content = _csv(*rows)
    res = _upload(client, content)
    data = res.json()
    assert len(data["sample_transactions"]) == 5


def test_preview_duplicate_detection(client):
    """重複交易計入 duplicates，不進入 to_import。"""
    dm.add_category("E", "餐飲費", "早餐")
    dm.add_transaction("2025-12-01", "E", "餐飲費", "早餐", 20, "豆漿", "")
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,-20,豆漿,",   # 重複
        "2025/12/02,E,餐飲費,早餐,A-現金,-50,早餐,",   # 新增
    )
    res = _upload(client, content)
    data = res.json()
    assert data["summary"]["duplicates"] == 1
    assert data["summary"]["to_import"] == 1


def test_preview_empty_rows(client):
    """全部 A/L 或空檔，date_range 回傳 null。"""
    content = _csv("2025/12/01,A,現金,,Equity,0,,")
    res = _upload(client, content)
    data = res.json()
    assert data["summary"]["to_import"] == 0
    assert data["date_range"]["min"] is None
    assert data["date_range"]["max"] is None


def test_preview_token_stored(client):
    """preview_token 存入 _preview_store。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    res = _upload(client, content)
    token = res.json()["preview_token"]
    assert token in _app_module._preview_store


# ── AT-010：POST /api/import/confirm token 過期 ──

def test_confirm_expired_token(client):
    """AT-010：preview_token 過期（TTL=0）→ 410。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    prev_res = _upload(client, content)
    token = prev_res.json()["preview_token"]

    # 強制過期
    _app_module._preview_store[token]["expires"] = time.time() - 1

    res = client.post("/api/import/confirm", json={"preview_token": token})
    assert res.status_code == 410


def test_confirm_invalid_token(client):
    """不存在的 token → 410。"""
    res = client.post("/api/import/confirm", json={"preview_token": "deadbeef"})
    assert res.status_code == 410


def test_confirm_success(client):
    """正常確認：寫入交易 + 新增分類，token 被清除。"""
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,-20,豆漿,",
        "2025/12/02,I,薪資,,A-現金,50000,,",
    )
    # Preview
    prev_res = _upload(client, content)
    token = prev_res.json()["preview_token"]

    # Confirm
    res = client.post("/api/import/confirm", json={"preview_token": token})
    assert res.status_code == 200
    data = res.json()
    assert data["added"] == 2
    assert data["skipped"] == 0
    assert data["new_categories"] == 2

    # token 已清除
    assert token not in _app_module._preview_store

    # 資料實際寫入
    result = dm.query_transactions()
    assert result["total"] == 2


def test_confirm_dedup_on_write(client):
    """確認時資料已重複，實際 added 比預覽少（極端 race condition 保護）。"""
    dm.add_category("E", "餐飲費", "早餐")
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,豆漿,")
    prev_res = _upload(client, content)
    token = prev_res.json()["preview_token"]

    # 在 confirm 前插入相同交易（模擬 race condition）
    dm.add_transaction("2025-12-01", "E", "餐飲費", "早餐", 20, "豆漿", "")

    res = client.post("/api/import/confirm", json={"preview_token": token})
    assert res.status_code == 200
    data = res.json()
    assert data["added"] == 0
    assert data["skipped"] == 1


def test_confirm_token_can_only_be_used_once(client):
    """同一 token 不能使用兩次。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    prev_res = _upload(client, content)
    token = prev_res.json()["preview_token"]

    client.post("/api/import/confirm", json={"preview_token": token})
    res2 = client.post("/api/import/confirm", json={"preview_token": token})
    assert res2.status_code == 410


def test_preview_bom_csv(client):
    """支援 UTF-8 BOM CSV（MyAB 匯出格式）。"""
    bom_csv = b"\xef\xbb\xbf" + _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    res = _upload(client, bom_csv)
    assert res.status_code == 200
    assert res.json()["summary"]["to_import"] == 1


def test_preview_all_al_filtered(client):
    """全部 A/L，to_import=0，new_categories=[]，狀態仍 200。"""
    content = _csv(
        "2025/12/01,A,現金,,Equity,0,,",
        "2025/12/01,L,信用卡,,Equity,0,,",
    )
    res = _upload(client, content)
    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["to_import"] == 0
    assert data["summary"]["filtered"] == 2
    assert data["new_categories"] == []


# ── 新增：資料驗證 ──

def test_preview_amount_zero_filtered(client):
    """金額=0 的 E/I 行被 filtered，不計入 to_import。"""
    content = _csv(
        "2025/12/01,E,餐飲費,早餐,A-現金,0,,",   # 金額=0 → filtered
        "2025/12/01,E,餐飲費,午餐,A-現金,-50,,",  # 正常
    )
    res = _upload(client, content)
    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["total"] == 2
    assert data["summary"]["filtered"] == 1
    assert data["summary"]["to_import"] == 1


def test_preview_invalid_date_filtered(client):
    """無效日期的行被 filtered，不計入 to_import。"""
    content = _csv(",E,餐飲費,早餐,A-現金,-20,,")   # 空日期
    res = _upload(client, content)
    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["filtered"] == 1
    assert data["summary"]["to_import"] == 0


def test_preview_total_equals_filtered_plus_import_plus_dup(client):
    """total == filtered + to_import + duplicates。"""
    dm.add_category("E", "餐飲費", "早餐")
    dm.add_transaction("2025-12-01", "E", "餐飲費", "早餐", 20, "豆漿", "")
    content = _csv(
        "2025/12/01,A,現金,,Equity,0,,",          # filtered（A/L）
        "2025/12/01,E,餐飲費,早餐,A-現金,-20,豆漿,",  # dup
        "2025/12/02,E,餐飲費,早餐,A-現金,-50,,",  # new
    )
    res = _upload(client, content)
    data = res.json()
    s = data["summary"]
    assert s["total"] == s["filtered"] + s["to_import"] + s["duplicates"]


# ── 新增：安全性 ──

def test_preview_file_size_limit(client):
    """超過 10MB 的檔案回 413。"""
    large_content = b"x" * (10 * 1024 * 1024 + 1)
    res = client.post(
        "/api/import/preview",
        files={"file": ("big.csv", large_content, "text/csv")},
    )
    assert res.status_code == 413


def test_preview_non_csv_extension(client):
    """非 .csv 副檔名回 400。"""
    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    res = client.post(
        "/api/import/preview",
        files={"file": ("data.txt", content, "text/plain")},
    )
    assert res.status_code == 400


def test_preview_cleanup_expired_tokens(client, monkeypatch):
    """每次 preview 呼叫都會清除過期的 token。"""
    import app as _app
    # 手動插入一個已過期的 token
    _app._preview_store["stale"] = {"rows": [], "new_cats": [], "expires": time.time() - 1}

    content = _csv("2025/12/01,E,餐飲費,早餐,A-現金,-20,,")
    _upload(client, content)

    # 過期 token 應已被清除
    assert "stale" not in _app._preview_store
