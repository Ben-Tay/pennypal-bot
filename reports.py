from __future__ import annotations

from categorize import TOTAL_ALIASES, TOTAL_KEY, resolve_category
from store import store
from utils import (
    bar,
    current_month,
    days_left_in_month,
    escape,
    fmt_money,
    month_label,
)


async def build_report(user_id: int, month_key: str | None = None) -> tuple[str, dict[str, float], dict]:
    month_key = month_key or current_month()
    expenses = await store.month_expenses(user_id, month_key)
    totals: dict[str, float] = {}
    for e in expenses:
        totals[e["category"]] = totals.get(e["category"], 0.0) + e["amount"]
    spent = sum(totals.values())
    salary = await store.get_salary(user_id, month_key) or 0.0
    budgets = await store.get_budgets(user_id)
    total_budget = budgets.get(TOTAL_KEY, 0.0)

    income_base = salary if salary > 0 else total_budget
    available = (income_base - spent) if income_base > 0 else None

    lines = []
    if salary > 0:
        lines.append(f"Income     {fmt_money(salary):>14}")
        if total_budget > 0:
            lines.append(f"Budget cap {fmt_money(total_budget):>14}")
        pct_income = spent / salary * 100 if salary else 0
        lines.append(f"Spent      {fmt_money(spent):>14}  ({pct_income:.1f}% of income)")
    elif total_budget > 0:
        lines.append(f"Budget cap {fmt_money(total_budget):>14}")
        pct_budget = spent / total_budget * 100
        lines.append(f"Spent      {fmt_money(spent):>14}  ({pct_budget:.1f}% of budget)")
    else:
        lines.append(f"Spent      {fmt_money(spent):>14}")

    rows = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    budgeted_extra = [c for c in budgets if c != TOTAL_KEY and c not in totals]
    rows += [(c, 0.0) for c in budgeted_extra]

    detail_lines = []
    for category, value in rows:
        limit = budgets.get(category, 0.0)
        pct = value / limit * 100 if limit > 0 else 0
        cat_disp = category[:16].ljust(16)
        spent_disp = fmt_money(value).rjust(12)
        if limit > 0:
            bar_disp = bar(pct)
            detail_lines.append(
                f"{cat_disp}{spent_disp}  [{bar_disp}] {pct:3.0f}% of {fmt_money(limit)}"
            )
        else:
            detail_lines.append(f"{cat_disp}{spent_disp}   (no budget set)")

    body = "\n".join(lines)
    detail = "\n".join(detail_lines)

    footer_bits = []
    if available is not None and available >= 0:
        left_days = days_left_in_month()
        footer_bits.append(f"Available: {fmt_money(available)}")
        if left_days > 0:
            safe_daily = available / left_days
            footer_bits.append(f"Safe daily spend: ~{fmt_money(safe_daily)}")
    elif available is not None:
        footer_bits.append(f"You are OVER by {fmt_money(-available)}")

    header = f"<b>Budget Report - {escape(month_label(month_key))}</b>"
    text = header + "\n<pre>" + escape(body)
    if detail:
        text += "\n\n" + escape(detail)
    text += "</pre>"
    if footer_bits:
        text += "\n" + escape(" | ".join(footer_bits))
    if salary == 0 and total_budget == 0:
        text += "\n<i>Tip: set /salary and /budget so I can track what's left.</i>"
    if not expenses:
        text += "\n<i>No expenses logged yet this month.</i>"

    meta = {"spent": spent, "salary": salary, "total_budget": total_budget, "count": len(expenses)}
    return text, totals, meta


def parse_budget_target(text: str) -> tuple[str | None, float | None]:
    tokens = text.split()
    if len(tokens) < 2:
        return None, None
    from utils import parse_amount

    amount = parse_amount(tokens[-1])
    if amount is None:
        return None, None
    category_text = " ".join(tokens[:-1])
    if category_text.lower() in TOTAL_ALIASES:
        return TOTAL_KEY, amount
    return resolve_category(category_text), amount
