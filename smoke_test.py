import asyncio
import os
import pathlib
import tempfile

os.environ.pop("REDIS_URL", None)
os.environ.pop("LIBSQL_URL", None)
os.environ.setdefault("CURRENCY", "S$")
os.environ.setdefault("TIMEZONE", "Asia/Singapore")

tmp = tempfile.mkdtemp()

import store as store_mod
import reports
from categorize import guess_category, resolve_category
from charts import spending_chart
from reports import build_report, parse_budget_target
from utils import parse_amount, parse_entry

UID = 42
MONTH = "2026-08"

entries = [
    (5.5, "kopi and kaya toast"),
    (18.2, "grab home"),
    (89.9, "uniqlo winter jacket"),
    (64.35, "ntuc weekly groceries"),
    (12.0, "mystery item"),
]


async def run_suite(s, label: str) -> dict:
    await s.init()

    for amount, desc in entries:
        cat = guess_category(desc)
        if cat is None:
            cat = "Others"
            assert desc == "mystery item"
        await s.add_expense(UID, amount, desc, cat, "2026-08-23 09:00:00", MONTH)

    assert guess_category("netflix subscription") == "Entertainment"
    assert guess_category("gym membership") == "Health & Fitness"
    assert resolve_category("fd") == "Food & Drinks"
    assert resolve_category("TOTAL") == "__total__"
    assert resolve_category("health") == "Health & Fitness"

    assert parse_entry("12.50 kopi") == (12.5, "kopi")
    assert parse_entry("grab $18.20 home")[0] == 18.2
    assert parse_entry("1,234.50 laptop") == (1234.5, "laptop")
    assert parse_entry("hello world") is None
    assert parse_amount("/budget food 400".split()[-1]) == 400.0

    await s.set_salary(UID, MONTH, 5200.0)
    assert await s.get_salary(UID, MONTH) == 5200.0
    await s.set_budget(UID, "__total__", 2500.0)
    await s.set_budget(UID, "Food & Drinks", 100.0)
    budgets = await s.get_budgets(UID)
    assert budgets["Food & Drinks"] == 100.0 and budgets["__total__"] == 2500.0

    reports.store = s
    text, totals, meta = await build_report(UID, MONTH)
    print(f"--- {label} report ---")
    print(text.replace("<b>", "").replace("</b>", "").replace("<pre>", "").replace("</pre>", "").replace("<i>", "").replace("</i>", ""))
    print("---")
    print("totals:", totals)
    print("meta:", meta)
    assert abs(meta["spent"] - sum(a for a, _ in entries)) < 0.01
    assert meta["count"] == len(entries)

    cat, amt = parse_budget_target("food 400")
    assert cat == "Food & Drinks" and amt == 400.0
    cat, amt = parse_budget_target("total 2500")
    assert cat == "__total__" and amt == 2500.0

    rows = await s.month_expenses(UID, MONTH)
    assert len(rows) == len(entries)
    amounts = [r["amount"] for r in rows]
    assert set(amounts) == {a for a, _ in entries}

    last = await s.last_expense(UID)
    assert float(last["amount"]) == 12.0
    assert await s.delete_expense(UID, last["id"]) is True
    assert await s.delete_expense(UID, 999999) is False
    remaining = await s.month_expenses(UID, MONTH)
    assert len(remaining) == len(entries) - 1

    await s.set_pending(UID, 15.0, "salmon dinner")
    pending = await s.pop_pending(UID)
    assert pending and abs(pending["amount"] - 15.0) < 0.01
    assert pending["desc"] == "salmon dinner"
    assert "ts" in pending
    assert await s.pop_pending(UID) is None

    chart_path = os.path.join(tmp, f"chart-{label}.png")
    spending_chart(totals, chart_path, "S$190")
    assert os.path.getsize(chart_path) > 10000

    return totals


async def main() -> None:
    sqlite_store = store_mod.SqliteStore(pathlib.Path(tmp) / "test.db")
    totals = await run_suite(sqlite_store, "sqlite")
    print("SQLITE SUITE OK")

    redis_url = os.getenv("TEST_REDIS_URL", "").strip()
    if redis_url:
        redis_store = store_mod.RedisStore(redis_url, prefix="pennypal-smoketest")
        try:
            c = redis_store._c()

            async def wipe():
                keys = [k async for k in c.scan_iter(match="pennypal-smoketest:*")]
                if keys:
                    await c.delete(*keys)

            await wipe()
            await run_suite(redis_store, "redis")
            print("REDIS SUITE OK")
            await wipe()
        finally:
            await redis_store.close()
    else:
        print("REDIS SUITE SKIPPED (set TEST_REDIS_URL to run it)")


asyncio.run(main())
