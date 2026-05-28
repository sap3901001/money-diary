"""
import_export.py — MyAB CSV 解析（A/L 過濾、欄位對映）
"""

import csv
import io
import re
import uuid
from datetime import datetime, timezone

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_myab_csv(content: bytes) -> dict:
    """
    解析 MyAB 匯出 CSV（支援 UTF-8 BOM 與 UTF-8）。

    回傳 dict：
      - rows         : list[dict]  轉換後的交易（含 id/建立時間），僅保留 E/I 類型且資料合法
      - filtered_count: int        被過濾掉的筆數（A/L 類型 + 無效日期 + 金額 ≤ 0）
      - total_count  : int         原始總筆數（不含標頭）

    欄位對映規則：
      - 日期 YYYY/MM/DD → YYYY-MM-DD（不符合格式則過濾）
      - 類型 E/I 保留，其他過濾
      - 金額 取絕對值（≤ 0 則過濾）
      - 帳戶欄 丟棄
    """
    text = content.decode("utf-8-sig")  # 自動去除 BOM
    reader = csv.DictReader(io.StringIO(text))

    # 驗證必要欄位存在
    _REQUIRED_HEADERS = {"類型", "日期", "金額"}
    if reader.fieldnames is None or not _REQUIRED_HEADERS.issubset(
        set(reader.fieldnames)
    ):
        missing = _REQUIRED_HEADERS - set(reader.fieldnames or [])
        raise ValueError(
            f"CSV 缺少必要欄位：{', '.join(sorted(missing))}，請確認是否為 MyAB 匯出格式"
        )

    rows: list[dict] = []
    filtered_count = 0
    total_count = 0

    ts = _now_iso()  # 批次共用相同建立時間

    for rec in reader:
        total_count += 1
        t = rec.get("類型", "").strip()
        if t not in ("E", "I"):
            filtered_count += 1
            continue

        # 日期格式轉換並驗證
        date_raw = rec.get("日期", "").strip()
        date = date_raw.replace("/", "-")
        if not _DATE_RE.match(date):
            filtered_count += 1
            continue

        # 金額取絕對值（≤ 0 視為無效，同樣過濾）
        try:
            amount = abs(round(float(rec.get("金額", 0))))
        except (ValueError, TypeError):
            filtered_count += 1
            continue
        if amount <= 0:
            filtered_count += 1
            continue

        rows.append(
            {
                "id": _new_id(),
                "日期": date,
                "類型": t,
                "類別主類": rec.get("類別主類", "").strip(),
                "類別次類": rec.get("類別次類", "").strip(),
                "金額": str(amount),
                "明細": rec.get("明細", "").strip(),
                "備註": rec.get("備註", "").strip(),
                "建立時間": ts,
            }
        )

    return {
        "rows": rows,
        "filtered_count": filtered_count,
        "total_count": total_count,
    }


def extract_categories(rows: list[dict]) -> list[dict]:
    """從交易列表提取唯一分類（去重，保留插入順序）。"""
    seen: set[tuple] = set()
    cats: list[dict] = []
    for r in rows:
        key = (r["類型"], r["類別主類"], r["類別次類"])
        if key not in seen:
            seen.add(key)
            cats.append(
                {"類型": r["類型"], "主類": r["類別主類"], "次類": r["類別次類"]}
            )
    return cats
