"""
report_engine.py — 統計報表計算（月度/分類/趨勢）
"""
from collections import defaultdict

import data_manager as dm


# ---------------------------------------------------------------------------
# 內部工具
# ---------------------------------------------------------------------------

def _month_range(from_date: str, to_date: str) -> list[str]:
    """產生 from_date 到 to_date 之間所有月份字串（格式 YYYY-MM），空月補 0 用。"""
    ym_from = from_date[:7]
    ym_to = to_date[:7]
    months: list[str] = []
    y, m = int(ym_from[:4]), int(ym_from[5:7])
    y_end, m_end = int(ym_to[:4]), int(ym_to[5:7])
    while (y, m) <= (y_end, m_end):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def _aggregate_by_month(rows: list[dict]) -> tuple[dict, dict]:
    """回傳 (income_by_month, expense_by_month)，key 為 YYYY-MM。"""
    income: dict[str, int] = defaultdict(int)
    expense: dict[str, int] = defaultdict(int)
    for r in rows:
        month = r["日期"][:7]
        amt = int(r["金額"])
        if r["類型"] == "I":
            income[month] += amt
        elif r["類型"] == "E":
            expense[month] += amt
    return income, expense


# ---------------------------------------------------------------------------
# 月度收支摘要
# ---------------------------------------------------------------------------

def monthly_report(from_date: str, to_date: str, type_: str = "all") -> list[dict]:
    """月度收支摘要，含所有月份（空月補 0）。

    type_: 'E' 只含支出, 'I' 只含收入, 'all' 收支皆含
    每筆: {month: 'YYYY-MM', income: int, expense: int, net: int}
    """
    rows = dm.export_transactions(from_date, to_date)
    if type_ == "E":
        rows = [r for r in rows if r["類型"] == "E"]
    elif type_ == "I":
        rows = [r for r in rows if r["類型"] == "I"]

    income_by_month, expense_by_month = _aggregate_by_month(rows)

    result = []
    for month in _month_range(from_date, to_date):
        income = income_by_month.get(month, 0)
        expense = expense_by_month.get(month, 0)
        result.append({"month": month, "income": income, "expense": expense, "net": income - expense})
    return result


# ---------------------------------------------------------------------------
# 分類佔比

# ---------------------------------------------------------------------------

def category_report(from_date: str, to_date: str, type_: str = "E", level: str = "main") -> dict:
    """分類佔比報表，按金額 DESC 排序。

    type_: 'E' 或 'I'
    level: 'main' 只看主類；'sub' 看主類/次類
    回傳: {items: [{name, amount, percent}, ...], total: int}
    """
    rows = dm.export_transactions(from_date, to_date)
    rows = [r for r in rows if r["類型"] == type_]

    totals: dict[str, int] = defaultdict(int)
    for r in rows:
        if level == "sub":
            sub = r["類別次類"]
            name = f"{r['類別主類']}/{sub}" if sub else r["類別主類"]
        else:
            name = r["類別主類"]
        totals[name] += int(r["金額"])

    grand_total = sum(totals.values())
    items = [
        {
            "name": name,
            "amount": amount,
            "percent": round(amount / grand_total * 100, 1) if grand_total > 0 else 0.0,
        }
        for name, amount in sorted(totals.items(), key=lambda x: -x[1])
    ]
    return {"items": items, "total": grand_total}


# ---------------------------------------------------------------------------
# 月度趨勢（可選分類篩選）
# ---------------------------------------------------------------------------

def trend_report(
    from_date: str,
    to_date: str,
    type_: str = "all",
    category_main: str | None = None,
) -> list[dict]:
    """月度趨勢折線，含所有月份（空月補 0）。

    category_main: 若指定則只計算該主類的收支
    每筆: {month: 'YYYY-MM', income: int, expense: int, net: int}
    """
    rows = dm.export_transactions(from_date, to_date)
    if category_main:
        rows = [r for r in rows if r["類別主類"] == category_main]
    if type_ == "E":
        rows = [r for r in rows if r["類型"] == "E"]
    elif type_ == "I":
        rows = [r for r in rows if r["類型"] == "I"]

    income_by_month, expense_by_month = _aggregate_by_month(rows)

    result = []
    for month in _month_range(from_date, to_date):
        income = income_by_month.get(month, 0)
        expense = expense_by_month.get(month, 0)
        result.append({"month": month, "income": income, "expense": expense, "net": income - expense})
    return result


# ---------------------------------------------------------------------------
# 前十大支出項目（逐筆，不彙總）
# ---------------------------------------------------------------------------

def top_expense_report(from_date: str, to_date: str, limit: int = 10) -> list[dict]:
    """回傳指定期間金額最大的前 N 筆支出紀錄（逐筆，不依分類彙總）。

    每筆: {amount, main_cat, sub_cat, date, detail}
    """
    rows = dm.export_transactions(from_date, to_date)
    rows = [r for r in rows if r["類型"] == "E"]
    rows.sort(key=lambda r: int(r["金額"]), reverse=True)
    return [
        {
            "amount": int(r["金額"]),
            "main_cat": r["類別主類"],
            "sub_cat": r["類別次類"],
            "date": r["日期"],
            "detail": r["明細"],
        }
        for r in rows[:limit]
    ]
