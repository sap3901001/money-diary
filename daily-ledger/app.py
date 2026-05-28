"""
app.py — FastAPI 主應用（REST API + StaticFiles 掛載 frontend/）
"""

import csv
import io
import re
import time
import uuid as _uuid_mod
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

import data_manager as dm
import import_export as ie
import report_engine as re_

FRONTEND_DIR = Path(__file__).parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    dm.init_data_files()
    yield


app = FastAPI(title="Daily Ledger", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------


class TransactionCreate(BaseModel):
    日期: str
    類型: str
    類別主類: str
    類別次類: str = ""
    金額: int
    明細: str = ""
    備註: str = ""

    @field_validator("日期")
    @classmethod
    def validate_date(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("日期格式必須為 YYYY-MM-DD")
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("無效日期")
        return v

    @field_validator("類型")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("E", "I"):
            raise ValueError("類型必須為 E 或 I")
        return v

    @field_validator("金額")
    @classmethod
    def validate_amount(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("金額必須為正整數")
        return v


class CategoryCreate(BaseModel):
    類型: str
    主類: str
    次類: str = ""

    @field_validator("類型")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("E", "I"):
            raise ValueError("類型必須為 E 或 I")
        return v

    @field_validator("主類")
    @classmethod
    def validate_main(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("主類不可為空")
        return v.strip()

    @field_validator("次類")
    @classmethod
    def validate_sub(cls, v: str) -> str:
        return v.strip()


class CategoryDelete(BaseModel):
    類型: str
    主類: str
    次類: str = ""

    @field_validator("類型")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("E", "I"):
            raise ValueError("類型必須為 E 或 I")
        return v


class ImportConfirm(BaseModel):
    preview_token: str


class CategoryMerge(BaseModel):
    來源類型: str
    來源主類: str
    來源次類: str = ""
    目標類型: str
    目標主類: str
    目標次類: str = ""

    @field_validator("來源類型", "目標類型")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("E", "I"):
            raise ValueError("類型必須為 E 或 I")
        return v


# ---------------------------------------------------------------------------
# 匯入暫存（記憶體 dict + TTL 10 分鐘）
# ---------------------------------------------------------------------------

_preview_store: dict = {}
_PREVIEW_TTL = 600
_IMPORT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _preview_token() -> str:
    return _uuid_mod.uuid4().hex


def _cleanup_preview_store() -> None:
    """清除過期的 preview token，防止記憶體洩漏。"""
    now = time.time()
    expired = [k for k, v in _preview_store.items() if now > v["expires"]]
    for k in expired:
        del _preview_store[k]


# ---------------------------------------------------------------------------
# 分類 API
# ---------------------------------------------------------------------------


@app.get("/api/categories")
def get_categories(
    type: str | None = Query(None, alias="type"),
    include_count: int = Query(0),
):
    if type is not None and type not in ("E", "I"):
        raise HTTPException(422, detail="type 必須為 E 或 I")
    return dm.get_categories(type_filter=type, include_count=bool(include_count))


@app.post("/api/categories", status_code=201)
def add_category(body: CategoryCreate):
    try:
        return dm.add_category(body.類型, body.主類, body.次類)
    except ValueError as e:
        if "duplicate" in str(e):
            raise HTTPException(409, detail="分類已存在")
        raise HTTPException(422, detail=str(e))


@app.delete("/api/categories", status_code=204)
def delete_category(body: CategoryDelete):
    try:
        dm.delete_category(body.類型, body.主類, body.次類)
    except ValueError as e:
        err = str(e)
        if "in_use" in err:
            raise HTTPException(409, detail="分類仍有交易引用，無法刪除")
        if "not_found" in err:
            raise HTTPException(404, detail="分類不存在")
        raise HTTPException(422, detail=err)


@app.post("/api/categories/merge")
def merge_categories(body: CategoryMerge):
    if body.來源類型 != body.目標類型:
        raise HTTPException(422, detail="來源與目標分類類型必須相同")
    if not dm.category_exists(body.來源類型, body.來源主類, body.來源次類):
        raise HTTPException(422, detail="來源分類不存在")
    if not dm.category_exists(body.目標類型, body.目標主類, body.目標次類):
        raise HTTPException(422, detail="目標分類不存在")
    try:
        return dm.merge_categories(
            body.來源類型,
            body.來源主類,
            body.來源次類,
            body.目標類型,
            body.目標主類,
            body.目標次類,
        )
    except ValueError as e:
        if "src_equals_dst" in str(e):
            raise HTTPException(422, detail="來源與目標分類相同")
        raise HTTPException(422, detail=str(e))


class CategoryReorder(BaseModel):
    類型: str
    主類: str
    次類: str = ""
    direction: str  # "up" or "down"

    @field_validator("類型")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in ("E", "I"):
            raise ValueError("類型必須為 E 或 I")
        return v

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        if v not in ("up", "down"):
            raise ValueError("direction 必須為 up 或 down")
        return v


@app.post("/api/categories/reorder")
def reorder_category(body: CategoryReorder):
    try:
        dm.reorder_category(body.類型, body.主類, body.次類, body.direction)
        return {"ok": True}
    except ValueError as e:
        err = str(e)
        if "not_found" in err:
            raise HTTPException(404, detail="分類不存在")
        if "already_first" in err:
            raise HTTPException(422, detail="已在最前面，無法上移")
        if "already_last" in err:
            raise HTTPException(422, detail="已在最後面，無法下移")
        raise HTTPException(422, detail=err)


# ---------------------------------------------------------------------------
# 交易 API
# ---------------------------------------------------------------------------


@app.get("/api/transactions/date_range")
def get_date_range():
    return dm.get_date_range()


@app.get("/api/transactions")
def list_transactions(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    type: str | None = Query(None, alias="type"),
    category_main: str | None = None,
    category_sub: str | None = None,
    keyword: str | None = None,
    amount_min: int | None = None,
    amount_max: int | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=500),
):
    if type is not None and type not in ("E", "I"):
        raise HTTPException(422, detail="type 必須為 E 或 I")
    if category_sub is not None and not category_main:
        raise HTTPException(422, detail="指定次類時必須同時指定主類")
    return dm.query_transactions(
        from_date=from_,
        to_date=to,
        type_=type,
        cat_main=category_main,
        cat_sub=category_sub,
        keyword=keyword,
        amount_min=amount_min,
        amount_max=amount_max,
        page=page,
        size=size,
    )


@app.get("/api/transactions/{id}")
def get_transaction(id: str):
    row = dm.get_transaction(id)
    if row is None:
        raise HTTPException(404, detail="交易不存在")
    return row


@app.post("/api/transactions", status_code=201)
def create_transaction(body: TransactionCreate):
    if not dm.category_exists(body.類型, body.類別主類, body.類別次類):
        raise HTTPException(422, detail="分類不存在")
    return dm.add_transaction(
        body.日期,
        body.類型,
        body.類別主類,
        body.類別次類,
        body.金額,
        body.明細,
        body.備註,
    )


@app.put("/api/transactions/{id}")
def update_transaction(id: str, body: TransactionCreate):
    if not dm.category_exists(body.類型, body.類別主類, body.類別次類):
        raise HTTPException(422, detail="分類不存在")
    row = dm.update_transaction(
        id,
        body.日期,
        body.類型,
        body.類別主類,
        body.類別次類,
        body.金額,
        body.明細,
        body.備註,
    )
    if row is None:
        raise HTTPException(404, detail="交易不存在")
    return row


@app.delete("/api/transactions/{id}", status_code=204)
def delete_transaction(id: str):
    if not dm.delete_transaction(id):
        raise HTTPException(404, detail="交易不存在")


# ---------------------------------------------------------------------------
# 匯出 API
# ---------------------------------------------------------------------------

_EXPORT_HEADERS = [
    "id",
    "日期",
    "類型",
    "類別主類",
    "類別次類",
    "金額",
    "明細",
    "備註",
    "建立時間",
]
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@app.get("/api/export")
def export_csv(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
):
    if not _DATE_PATTERN.match(from_):
        raise HTTPException(422, detail="from 日期格式必須為 YYYY-MM-DD")
    if not _DATE_PATTERN.match(to):
        raise HTTPException(422, detail="to 日期格式必須為 YYYY-MM-DD")
    try:
        datetime.strptime(from_, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(422, detail="from 為無效日期")
    try:
        datetime.strptime(to, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(422, detail="to 為無效日期")
    if from_ > to:
        raise HTTPException(422, detail="開始日期不可晚於結束日期")

    rows = dm.export_transactions(from_date=from_, to_date=to)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_EXPORT_HEADERS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

    content = output.getvalue().encode("utf-8-sig")  # UTF-8 with BOM（Excel 友善）

    from_str = from_.replace("-", "")
    to_str = to.replace("-", "")
    filename = f"daily_ledger_{from_str}_{to_str}.csv"

    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# 報表 API
# ---------------------------------------------------------------------------


def _default_date_range() -> tuple[str, str]:
    """預設近 12 個月（當月第一日往前推 11 個月 ~ 今天）。"""
    today = date.today()
    y, m = today.year, today.month - 11
    while m <= 0:
        m += 12
        y -= 1
    from_date = date(y, m, 1).isoformat()
    return from_date, today.isoformat()


def _parse_report_dates(from_: str | None, to: str | None) -> tuple[str, str]:
    """驗證報表日期參數，None 時套用近 12 個月預設值。"""
    def_from, def_to = _default_date_range()
    if from_ is None:
        from_ = def_from
    if to is None:
        to = def_to
    if not _DATE_PATTERN.match(from_):
        raise HTTPException(422, detail="from 日期格式必須為 YYYY-MM-DD")
    if not _DATE_PATTERN.match(to):
        raise HTTPException(422, detail="to 日期格式必須為 YYYY-MM-DD")
    try:
        datetime.strptime(from_, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(422, detail="from 為無效日期")
    try:
        datetime.strptime(to, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(422, detail="to 為無效日期")
    if from_ > to:
        raise HTTPException(422, detail="開始日期不可晚於結束日期")
    return from_, to


@app.get("/api/report/monthly")
def report_monthly(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    type: str = Query("all", alias="type"),
):
    if type not in ("E", "I", "all"):
        raise HTTPException(422, detail="type 必須為 E、I 或 all")
    from_, to = _parse_report_dates(from_, to)
    return re_.monthly_report(from_, to, type_=type)


@app.get("/api/report/category")
def report_category(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    type: str = Query("E", alias="type"),
    level: str = Query("main"),
):
    if type not in ("E", "I"):
        raise HTTPException(422, detail="type 必須為 E 或 I")
    if level not in ("main", "sub"):
        raise HTTPException(422, detail="level 必須為 main 或 sub")
    from_, to = _parse_report_dates(from_, to)
    return re_.category_report(from_, to, type_=type, level=level)


@app.get("/api/report/trend")
def report_trend(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    type: str = Query("all", alias="type"),
    category_main: str | None = None,
):
    if type not in ("E", "I", "all"):
        raise HTTPException(422, detail="type 必須為 E、I 或 all")
    from_, to = _parse_report_dates(from_, to)
    return re_.trend_report(from_, to, type_=type, category_main=category_main)


@app.get("/api/report/top-expense")
def report_top_expense(
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    limit: int = 10,
):
    from_, to = _parse_report_dates(from_, to)
    return re_.top_expense_report(from_, to, limit)


# ---------------------------------------------------------------------------
# 匯入 API
# ---------------------------------------------------------------------------


@app.post("/api/import/preview")
async def import_preview(file: UploadFile = File(...)):
    # 副檔名驗證
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, detail="請上傳 CSV 檔案（.csv）")

    content = await file.read()

    # 檔案大小限制
    if len(content) > _IMPORT_MAX_BYTES:
        raise HTTPException(413, detail="檔案過大（上限 10 MB）")

    # 清理過期 token（防止記憶體洩漏）
    _cleanup_preview_store()

    try:
        parsed = ie.parse_myab_csv(content)
    except Exception as e:
        raise HTTPException(400, detail=f"CSV 解析失敗：{e}")

    rows = parsed["rows"]
    new_rows, dup_count = dm.check_duplicates(rows)

    # 找出新分類（僅從實際要匯入的新交易中提取，避免重複列的分類被誤建為孤立分類）
    all_cats = ie.extract_categories(new_rows)
    new_cats = [
        c for c in all_cats if not dm.category_exists(c["類型"], c["主類"], c["次類"])
    ]

    # 新交易的日期範圍
    dates = [r["日期"] for r in new_rows]
    date_min = min(dates) if dates else None
    date_max = max(dates) if dates else None

    token = _preview_token()
    _preview_store[token] = {
        "rows": new_rows,
        "new_cats": new_cats,
        "expires": time.time() + _PREVIEW_TTL,
    }

    return {
        "preview_token": token,
        "summary": {
            "total": parsed["total_count"],
            "filtered": parsed["filtered_count"],
            "to_import": len(new_rows),
            "duplicates": dup_count,
        },
        "date_range": {"min": date_min, "max": date_max},
        "new_categories": new_cats,
        "new_categories_count": len(new_cats),
        "sample_transactions": new_rows[:5],
    }


@app.post("/api/import/confirm")
def import_confirm(body: ImportConfirm):
    entry = _preview_store.get(body.preview_token)
    if not entry or time.time() > entry["expires"]:
        _preview_store.pop(body.preview_token, None)
        raise HTTPException(410, detail="預覽已過期或不存在，請重新上傳")

    rows = entry["rows"]
    new_cats = entry["new_cats"]

    added_cats = dm.ensure_categories(new_cats)
    result = dm.bulk_import(rows)
    _preview_store.pop(body.preview_token, None)

    return {
        "added": result["added"],
        "skipped": result["skipped"],
        "new_categories": added_cats,
    }


# ---------------------------------------------------------------------------
# 靜態前端（最後掛載，API 路由優先）
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
