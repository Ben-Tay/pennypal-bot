from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

import re
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Singapore"))
CURRENCY = os.getenv("CURRENCY", "S$")

CURRENCY_RE = re.compile(
    r"(?:\$|sgd|usd|rm)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.IGNORECASE
)
PLAIN_RE = re.compile(r"(?<![\w.,])([0-9]{1,6}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)(?![\w])")


def now_local() -> datetime:
    return datetime.now(TZ)


def current_month(dt: datetime | None = None) -> str:
    return (dt or now_local()).strftime("%Y-%m")


def month_label(month_key: str) -> str:
    year, month = month_key.split("-")
    return datetime(int(year), int(month), 1).strftime("%B %Y")


def days_left_in_month(dt: datetime | None = None) -> int:
    d = dt or now_local()
    last_day = calendar_last(d.year, d.month)
    return max(0, last_day - d.day)


def calendar_last(year: int, month: int) -> int:
    import calendar

    return calendar.monthrange(year, month)[1]


def fmt_money(value: float) -> str:
    return f"{CURRENCY}{value:,.2f}"


def parse_amount(text: str) -> float | None:
    m = CURRENCY_RE.search(text) or PLAIN_RE.search(text)
    if not m:
        return None
    try:
        value = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    if 0 < value <= 9_999_999:
        return round(value, 2)
    return None


def parse_entry(text: str) -> tuple[float, str] | None:
    t = text.strip()
    if not t or t.startswith("/"):
        return None
    m = CURRENCY_RE.search(t) or PLAIN_RE.search(t)
    if not m:
        return None
    try:
        amount = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    if not 0 < amount <= 9_999_999:
        return None
    desc = (t[: m.start()] + " " + t[m.end() :]).strip()
    desc = re.sub(r"\s+", " ", desc).strip(" -,.$")
    return round(amount, 2), desc


def bar(pct: float, width: int = 14) -> str:
    pct = max(0.0, min(pct, 999.0))
    filled = min(width, int(round(pct / 100 * width)))
    return "#" * filled + "-" * (width - filled)


def escape(value) -> str:
    import html

    return html.escape(str(value), quote=False)
