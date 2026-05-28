"""
data_manager.py — CSV CRUD、去重、分類 merge 邏輯
"""
import csv
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
MAIN_DB = DATA_DIR / "main_db.csv"
CATEGORIES_CSV = DATA_DIR / "categories.csv"

MAIN_HEADERS = ["id", "日期", "類型", "類別主類", "類別次類", "金額", "明細", "備註", "建立時間"]
CAT_HEADERS = ["類型", "主類", "次類", "sort_order"]

# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------

def init_data_files():
    """首次啟動時建立空 CSV（含 header），並清理殘留 .tmp 檔。
    若既有 categories.csv 缺少 sort_order 欄位，自動遷移補齊。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # 清理上次崩潰留下的暫存檔
    for tmp in DATA_DIR.glob("*.tmp"):
        tmp.unlink(missing_ok=True)
    if not MAIN_DB.exists():
        with open(MAIN_DB, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(MAIN_HEADERS)
    if not CATEGORIES_CSV.exists():
        with open(CATEGORIES_CSV, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(CAT_HEADERS)
    else:
        _migrate_sort_order()

def _migrate_sort_order():
    """若既有 categories.csv 缺少 sort_order 欄位，依原始順序補齊。"""
    with open(CATEGORIES_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if "sort_order" in (reader.fieldnames or []):
            return  # 已遷移
        rows = list(reader)
    # 按出現順序，在各自範圍內給定 sort_order
    _assign_sort_order_batch(rows)
    _write_csv(CATEGORIES_CSV, rows, CAT_HEADERS)


def _assign_sort_order_batch(rows: list[dict]):
    """為一批分類列依原始順序分配 sort_order。
    主類在同類型內排序；次類在同主類內排序。"""
    # 追蹤各範圍的計數器
    main_counters: dict[str, int] = {}       # type → next sort_order for main
    sub_counters: dict[tuple, int] = {}      # (type, main) → next sort_order for sub
    seen_mains: dict[str, set] = {}          # type → set of seen main names

    for row in rows:
        t, m, s = row["類型"], row["主類"], row.get("次類", "")
        if t not in seen_mains:
            seen_mains[t] = set()
            main_counters[t] = 0
        if s == "":
            # 主類條目（無次類）：在同類型內排序
            if m not in seen_mains[t]:
                row["sort_order"] = str(main_counters[t])
                main_counters[t] += 1
                seen_mains[t].add(m)
            else:
                row["sort_order"] = str(main_counters[t])
                main_counters[t] += 1
        else:
            # 次類條目：在同 (type, main) 內排序
            # 先確保主類已被計入
            if m not in seen_mains[t]:
                seen_mains[t].add(m)
                main_counters[t] += 1
            key = (t, m)
            if key not in sub_counters:
                sub_counters[key] = 0
            row["sort_order"] = str(sub_counters[key])
            sub_counters[key] += 1


def _get_sort_order_int(row: dict) -> int:
    """取得 sort_order 的整數值，缺值時回傳 999999。"""
    try:
        return int(row.get("sort_order", "999999"))
    except (ValueError, TypeError):
        return 999999


# ---------------------------------------------------------------------------
# 內部讀寫工具
# ---------------------------------------------------------------------------

def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict], headers: list[str]):
    """原子性寫入：先寫暫存檔再 rename。"""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)

# ---------------------------------------------------------------------------
# 分類管理
# ---------------------------------------------------------------------------

def get_categories(type_filter: str | None = None, include_count: bool = False) -> list[dict]:
    rows = _read_csv(CATEGORIES_CSV)
    if type_filter:
        rows = [r for r in rows if r["類型"] == type_filter]

    # 建立主類群組排序（key: (type, main) → sort_order）
    # 策略：用 first_seen（檔案出現順序）做基礎排序，
    #        有主類條目（次類=""）且有明確 sort_order 的用 sort_order 覆蓋。
    #        這確保未排序的主類群組保持原始順序，排序過的群組依 sort_order 排。
    main_order: dict[tuple, int] = {}
    first_seen_idx = 0
    for r in rows:
        key = (r["類型"], r["主類"])
        if key not in main_order:
            main_order[key] = first_seen_idx
            first_seen_idx += 1

    # 對有主類條目（次類=""）的，覆蓋為其 sort_order
    for r in rows:
        if r.get("次類", "") == "":
            main_order[(r["類型"], r["主類"])] = _get_sort_order_int(r)

    # 排序：先依主類群組 sort_order，主類條目排同名次類前，再依次類 sort_order
    rows.sort(key=lambda r: (
        main_order.get((r["類型"], r["主類"]), 999999),
        0 if r.get("次類", "") == "" else 1,
        _get_sort_order_int(r),
    ))

    if include_count:
        txns = _read_csv(MAIN_DB)
        for row in rows:
            row["count"] = sum(
                1 for t in txns
                if t["類別主類"] == row["主類"] and t["類別次類"] == row["次類"] and t["類型"] == row["類型"]
            )
    return rows


def add_category(type_: str, main: str, sub: str) -> dict:
    rows = _read_csv(CATEGORIES_CSV)
    if any(r["類型"] == type_ and r["主類"] == main and r["次類"] == sub for r in rows):
        raise ValueError("duplicate")
    # 計算同範圍的最大 sort_order + 1
    if sub == "":
        # 主類：在同類型內排末位
        scope = [r for r in rows if r["類型"] == type_ and r.get("次類", "") == ""]
    else:
        # 次類：在同 (type, main) 內排末位
        scope = [r for r in rows if r["類型"] == type_ and r["主類"] == main and r.get("次類", "") != ""]
    max_order = max((_get_sort_order_int(r) for r in scope), default=-1)
    new_row = {"類型": type_, "主類": main, "次類": sub, "sort_order": str(max_order + 1)}
    rows.append(new_row)
    _write_csv(CATEGORIES_CSV, rows, CAT_HEADERS)
    return new_row


def delete_category(type_: str, main: str, sub: str) -> None:
    txns = _read_csv(MAIN_DB)
    in_use = any(t["類型"] == type_ and t["類別主類"] == main and t["類別次類"] == sub for t in txns)
    if in_use:
        raise ValueError("in_use")
    rows = _read_csv(CATEGORIES_CSV)
    new_rows = [r for r in rows if not (r["類型"] == type_ and r["主類"] == main and r["次類"] == sub)]
    if len(new_rows) == len(rows):
        raise ValueError("not_found")
    _write_csv(CATEGORIES_CSV, new_rows, CAT_HEADERS)


def merge_categories(src_type: str, src_main: str, src_sub: str,
                     dst_type: str, dst_main: str, dst_sub: str) -> dict:
    """將所有引用 src 的交易改為 dst，並刪除 src 分類。回傳 {updated, deleted}。"""
    if (src_type, src_main, src_sub) == (dst_type, dst_main, dst_sub):
        raise ValueError("src_equals_dst")
    txns = _read_csv(MAIN_DB)
    updated = 0
    for t in txns:
        if t["類型"] == src_type and t["類別主類"] == src_main and t["類別次類"] == src_sub:
            t["類型"] = dst_type
            t["類別主類"] = dst_main
            t["類別次類"] = dst_sub
            updated += 1
    if updated:
        _write_csv(MAIN_DB, txns, MAIN_HEADERS)

    cats = _read_csv(CATEGORIES_CSV)
    new_cats = [c for c in cats if not (c["類型"] == src_type and c["主類"] == src_main and c["次類"] == src_sub)]
    deleted = len(cats) - len(new_cats)
    _write_csv(CATEGORIES_CSV, new_cats, CAT_HEADERS)

    return {"updated": updated, "deleted": deleted,
            "deleted_category": {"類型": src_type, "主類": src_main, "次類": src_sub}}


def category_exists(type_: str, main: str, sub: str) -> bool:
    return any(
        r["類型"] == type_ and r["主類"] == main and r["次類"] == sub
        for r in _read_csv(CATEGORIES_CSV)
    )


def reorder_category(type_: str, main: str, sub: str, direction: str) -> None:
    """將指定分類在同範圍內上移(up)或下移(down)一格（交換 sort_order）。

    - direction: "up" 或 "down"
    - 主類（sub==""）在同類型內排序
    - 次類（sub!=""）在同主類內排序
    """
    if direction not in ("up", "down"):
        raise ValueError("invalid_direction")

    rows = _read_csv(CATEGORIES_CSV)

    # 找出同範圍的項目
    if sub == "":
        # 主類排序：找出同類型所有主類條目（次類為空）
        scope = [r for r in rows if r["類型"] == type_ and r.get("次類", "") == ""]
    else:
        # 次類排序：找出同 (type, main) 所有次類條目（次類不為空）
        scope = [r for r in rows if r["類型"] == type_ and r["主類"] == main and r.get("次類", "") != ""]

    # 依 sort_order 排序
    scope.sort(key=_get_sort_order_int)

    # 找到目標項目在 scope 中的位置
    target_idx = None
    for i, r in enumerate(scope):
        if sub == "" and r["主類"] == main:
            target_idx = i
            break
        elif sub != "" and r["次類"] == sub:
            target_idx = i
            break

    if target_idx is None:
        raise ValueError("not_found")

    # 計算交換對象的索引
    if direction == "up":
        if target_idx == 0:
            raise ValueError("already_first")
        swap_idx = target_idx - 1
    else:
        if target_idx == len(scope) - 1:
            raise ValueError("already_last")
        swap_idx = target_idx + 1

    # 交換 sort_order
    scope[target_idx]["sort_order"], scope[swap_idx]["sort_order"] = \
        scope[swap_idx]["sort_order"], scope[target_idx]["sort_order"]

    _write_csv(CATEGORIES_CSV, rows, CAT_HEADERS)


def ensure_categories(new_cats: list[dict]) -> int:
    """批次新增尚未存在的分類（匯入用）。回傳新增筆數。"""
    existing = _read_csv(CATEGORIES_CSV)
    existing_set = {(r["類型"], r["主類"], r["次類"]) for r in existing}
    added = 0
    for c in new_cats:
        key = (c["類型"], c["主類"], c["次類"])
        if key not in existing_set:
            sub = c.get("次類", "")
            # 計算同範圍最大 sort_order + 1
            if sub == "":
                scope = [r for r in existing if r["類型"] == c["類型"] and r.get("次類", "") == ""]
            else:
                scope = [r for r in existing if r["類型"] == c["類型"] and r["主類"] == c["主類"] and r.get("次類", "") != ""]
            max_order = max((_get_sort_order_int(r) for r in scope), default=-1)
            new_row = {"類型": c["類型"], "主類": c["主類"], "次類": sub, "sort_order": str(max_order + 1)}
            existing.append(new_row)
            existing_set.add(key)
            added += 1
    if added:
        _write_csv(CATEGORIES_CSV, existing, CAT_HEADERS)
    return added

# ---------------------------------------------------------------------------
# 交易 CRUD
# ---------------------------------------------------------------------------

def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def add_transaction(date: str, type_: str, cat_main: str, cat_sub: str,
                    amount: int, detail: str, note: str) -> dict:
    row = {
        "id": _new_id(),
        "日期": date,
        "類型": type_,
        "類別主類": cat_main,
        "類別次類": cat_sub,
        "金額": str(amount),
        "明細": detail,
        "備註": note,
        "建立時間": _now_iso(),
    }
    rows = _read_csv(MAIN_DB)
    rows.append(row)
    _write_csv(MAIN_DB, rows, MAIN_HEADERS)
    return row


def get_transaction(id_: str) -> dict | None:
    for r in _read_csv(MAIN_DB):
        if r["id"] == id_:
            return r
    return None


def update_transaction(id_: str, date: str, type_: str, cat_main: str, cat_sub: str,
                       amount: int, detail: str, note: str) -> dict | None:
    rows = _read_csv(MAIN_DB)
    for r in rows:
        if r["id"] == id_:
            r["日期"] = date
            r["類型"] = type_
            r["類別主類"] = cat_main
            r["類別次類"] = cat_sub
            r["金額"] = str(amount)
            r["明細"] = detail
            r["備註"] = note
            _write_csv(MAIN_DB, rows, MAIN_HEADERS)
            return r
    return None


def delete_transaction(id_: str) -> bool:
    rows = _read_csv(MAIN_DB)
    new_rows = [r for r in rows if r["id"] != id_]
    if len(new_rows) == len(rows):
        return False
    _write_csv(MAIN_DB, new_rows, MAIN_HEADERS)
    return True


def query_transactions(
    from_date: str | None = None,
    to_date: str | None = None,
    type_: str | None = None,
    cat_main: str | None = None,
    cat_sub: str | None = None,
    keyword: str | None = None,
    amount_min: int | None = None,
    amount_max: int | None = None,
    page: int = 1,
    size: int = 100,
) -> dict:
    if size <= 0:
        raise ValueError("size must be > 0")
    if page < 1:
        raise ValueError("page must be >= 1")
    rows = _read_csv(MAIN_DB)

    # 篩選
    filtered = []
    for r in rows:
        if from_date and r["日期"] < from_date:
            continue
        if to_date and r["日期"] > to_date:
            continue
        if type_ and r["類型"] != type_:
            continue
        if cat_main and r["類別主類"] != cat_main:
            continue
        if cat_sub is not None and cat_sub != "" and r["類別次類"] != cat_sub:
            continue
        if keyword:
            kw = keyword.lower()
            if kw not in r["明細"].lower() and kw not in r["備註"].lower():
                continue
        amt = int(r["金額"])
        if amount_min is not None and amt < amount_min:
            continue
        if amount_max is not None and amt > amount_max:
            continue
        filtered.append(r)

    # 排序：日期 DESC + 建立時間 DESC
    filtered.sort(key=lambda r: (r["日期"], r["建立時間"]), reverse=True)

    # 統計摘要
    total_income = sum(int(r["金額"]) for r in filtered if r["類型"] == "I")
    total_expense = sum(int(r["金額"]) for r in filtered if r["類型"] == "E")
    summary = {
        "total_count": len(filtered),
        "total_income": total_income,
        "total_expense": total_expense,
        "net": total_income - total_expense,
    }

    # 分頁
    total = len(filtered)
    pages = max(1, (total + size - 1) // size)
    start = (page - 1) * size
    items = filtered[start: start + size]

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
        "summary": summary,
    }


def get_date_range() -> dict:
    rows = _read_csv(MAIN_DB)
    if not rows:
        return {"min": None, "max": None, "count": 0}
    dates = [r["日期"] for r in rows]
    return {"min": min(dates), "max": max(dates), "count": len(rows)}


def export_transactions(from_date: str, to_date: str) -> list[dict]:
    """回傳日期範圍內的交易，依日期 ASC + 建立時間 ASC 排序。"""
    rows = _read_csv(MAIN_DB)
    filtered = [r for r in rows if from_date <= r["日期"] <= to_date]
    filtered.sort(key=lambda r: (r["日期"], r["建立時間"]))
    return filtered


# ---------------------------------------------------------------------------
# 匯入輔助（去重檢查）
# ---------------------------------------------------------------------------

DEDUP_KEYS = ("日期", "類型", "類別主類", "類別次類", "金額", "明細")


def _dedup_key(row: dict) -> tuple:
    return tuple(row.get(k, "") for k in DEDUP_KEYS)


def bulk_import(rows: list[dict]) -> dict:
    """批次寫入交易，跳過重複。rows 已含所有欄位（id/建立時間已設好）。"""
    existing = _read_csv(MAIN_DB)
    existing_keys = {_dedup_key(r) for r in existing}
    added, skipped = [], 0
    for r in rows:
        k = _dedup_key(r)
        if k in existing_keys:
            skipped += 1
        else:
            existing.append(r)
            existing_keys.add(k)
            added.append(r)
    if added:
        _write_csv(MAIN_DB, existing, MAIN_HEADERS)
    return {"added": len(added), "skipped": skipped}


def check_duplicates(rows: list[dict]) -> tuple[list[dict], int]:
    """回傳 (new_rows, duplicate_count)，不寫入。
    同時對輸入批次自身去重，確保與 bulk_import 結果一致。"""
    existing = _read_csv(MAIN_DB)
    seen_keys = {_dedup_key(r) for r in existing}
    new_rows, dup_count = [], 0
    for r in rows:
        k = _dedup_key(r)
        if k in seen_keys:
            dup_count += 1
        else:
            new_rows.append(r)
            seen_keys.add(k)  # 防止批次內重複被重複計入 new_rows
    return new_rows, dup_count
