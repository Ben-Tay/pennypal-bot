from __future__ import annotations

import asyncio
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from utils import TZ

LOCAL_DB_PATH = Path(__file__).resolve().parent / "data" / "expenses.db"

PENDING_TTL = 900

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        category TEXT NOT NULL,
        created_at TEXT NOT NULL,
        month TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_expenses_user_month ON expenses (user_id, month)",
    """
    CREATE TABLE IF NOT EXISTS salaries (
        user_id INTEGER NOT NULL,
        month TEXT NOT NULL,
        amount REAL NOT NULL,
        PRIMARY KEY (user_id, month)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS budgets (
        user_id INTEGER NOT NULL,
        category TEXT NOT NULL,
        monthly_limit REAL NOT NULL,
        PRIMARY KEY (user_id, category)
    )
    """,
]


class SqliteStore:
    def __init__(self, path: Path | str = LOCAL_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    async def init(self) -> None:
        conn = self._conn()
        try:
            conn.executescript(";".join(SCHEMA))
        finally:
            conn.close()

    async def add_expense(
        self,
        user_id: int,
        amount: float,
        description: str,
        category: str,
        created_at: str,
        month: str,
    ) -> int:
        conn = self._conn()
        try:
            cur = conn.execute(
                "INSERT INTO expenses (user_id, amount, description, category, created_at, month)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, amount, description.strip(), category, created_at, month),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    async def last_expense(self, user_id: int) -> dict | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    async def delete_expense(self, user_id: int, row_id: int) -> bool:
        conn = self._conn()
        try:
            cur = conn.execute(
                "DELETE FROM expenses WHERE id = ? AND user_id = ?", (row_id, user_id)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    async def month_expenses(self, user_id: int, month: str) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM expenses WHERE user_id = ? AND month = ? ORDER BY id DESC",
                (user_id, month),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    async def set_salary(self, user_id: int, month: str, amount: float) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO salaries (user_id, month, amount) VALUES (?, ?, ?)"
                " ON CONFLICT (user_id, month) DO UPDATE SET amount = excluded.amount",
                (user_id, month, amount),
            )
            conn.commit()
        finally:
            conn.close()

    async def get_salary(self, user_id: int, month: str) -> float | None:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT amount FROM salaries WHERE user_id = ? AND month = ?",
                (user_id, month),
            ).fetchone()
            return row["amount"] if row else None
        finally:
            conn.close()

    async def set_budget(self, user_id: int, category: str, amount: float) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO budgets (user_id, category, monthly_limit) VALUES (?, ?, ?)"
                " ON CONFLICT (user_id, category) DO UPDATE SET monthly_limit = excluded.monthly_limit",
                (user_id, category, amount),
            )
            conn.commit()
        finally:
            conn.close()

    async def clear_budget(self, user_id: int, category: str) -> bool:
        conn = self._conn()
        try:
            cur = conn.execute(
                "DELETE FROM budgets WHERE user_id = ? AND category = ?",
                (user_id, category),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    async def get_budgets(self, user_id: int) -> dict[str, float]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT category, monthly_limit FROM budgets WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            return {r["category"]: r["monthly_limit"] for r in rows}
        finally:
            conn.close()

    def __init__(self, path: Path | str = LOCAL_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._pending: dict[int, dict] = {}

    async def set_pending(self, user_id: int, amount: float, desc: str) -> None:
        self._pending[user_id] = {"amount": amount, "desc": desc, "ts": time.time()}

    async def pop_pending(self, user_id: int) -> dict | None:
        return self._pending.pop(user_id, None)


class LibsqlStore:
    def __init__(self, url: str, auth_token: str):
        from libsql_client import create_client

        self._client = create_client(url, auth_token=auth_token)
        self._pending: dict[int, dict] = {}

    @staticmethod
    def _to_dicts(result) -> list[dict]:
        columns = list(result.columns)
        return [dict(zip(columns, row)) for row in result.rows]

    async def init(self) -> None:
        for ddl in SCHEMA:
            await self._client.execute(ddl)

    async def add_expense(
        self,
        user_id: int,
        amount: float,
        description: str,
        category: str,
        created_at: str,
        month: str,
    ) -> int:
        result = await self._client.execute(
            "INSERT INTO expenses (user_id, amount, description, category, created_at, month)"
            " VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
            [user_id, amount, description.strip(), category, created_at, month],
        )
        return int(result.rows[0][0])

    async def last_expense(self, user_id: int) -> dict | None:
        result = await self._client.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            [user_id],
        )
        rows = self._to_dicts(result)
        return rows[0] if rows else None

    async def delete_expense(self, user_id: int, row_id: int) -> bool:
        result = await self._client.execute(
            "SELECT id FROM expenses WHERE id = ? AND user_id = ?",
            [row_id, user_id],
        )
        if not result.rows:
            return False
        await self._client.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?",
            [row_id, user_id],
        )
        return True

    async def month_expenses(self, user_id: int, month: str) -> list[dict]:
        result = await self._client.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND month = ? ORDER BY id DESC",
            [user_id, month],
        )
        return self._to_dicts(result)

    async def set_salary(self, user_id: int, month: str, amount: float) -> None:
        await self._client.execute(
            "INSERT INTO salaries (user_id, month, amount) VALUES (?, ?, ?)"
            " ON CONFLICT (user_id, month) DO UPDATE SET amount = excluded.amount",
            [user_id, month, amount],
        )

    async def get_salary(self, user_id: int, month: str) -> float | None:
        result = await self._client.execute(
            "SELECT amount FROM salaries WHERE user_id = ? AND month = ?",
            [user_id, month],
        )
        if not result.rows:
            return None
        return float(result.rows[0][0])

    async def set_budget(self, user_id: int, category: str, amount: float) -> None:
        await self._client.execute(
            "INSERT INTO budgets (user_id, category, monthly_limit) VALUES (?, ?, ?)"
            " ON CONFLICT (user_id, category) DO UPDATE SET monthly_limit = excluded.monthly_limit",
            [user_id, category, amount],
        )

    async def clear_budget(self, user_id: int, category: str) -> bool:
        result = await self._client.execute(
            "SELECT category FROM budgets WHERE user_id = ? AND category = ?",
            [user_id, category],
        )
        if not result.rows:
            return False
        await self._client.execute(
            "DELETE FROM budgets WHERE user_id = ? AND category = ?",
            [user_id, category],
        )
        return True

    async def get_budgets(self, user_id: int) -> dict[str, float]:
        result = await self._client.execute(
            "SELECT category, monthly_limit FROM budgets WHERE user_id = ?",
            [user_id],
        )
        return {row["category"]: row["monthly_limit"] for row in self._to_dicts(result)}

    async def set_pending(self, user_id: int, amount: float, desc: str) -> None:
        self._pending[user_id] = {"amount": amount, "desc": desc, "ts": time.time()}

    async def pop_pending(self, user_id: int) -> dict | None:
        return self._pending.pop(user_id, None)


class RedisStore:
    def __init__(self, url: str, prefix: str = "pennypal"):
        from redis import asyncio as aioredis

        self._aioredis = aioredis
        self._url = url
        self._prefix = prefix
        self._client = None
        self._loop = None

    def _c(self):
        loop = asyncio.get_running_loop()
        if self._client is None or self._loop is not loop:
            self._client = self._aioredis.from_url(
                self._url,
                decode_responses=True,
                socket_connect_timeout=10,
                socket_timeout=10,
            )
            self._loop = loop
        return self._client

    def _user_key(self, user_id: int) -> str:
        return f"{self._prefix}:user:{user_id}"

    def _expense_key(self, expense_id: int) -> str:
        return f"{self._prefix}:expense:{expense_id}"

    def _expenses_zset(self, user_id: int) -> str:
        return f"{self._user_key(user_id)}:expenses"

    def _salary_key(self, user_id: int, month: str) -> str:
        return f"{self._user_key(user_id)}:salary:{month}"

    def _budgets_key(self, user_id: int) -> str:
        return f"{self._user_key(user_id)}:budgets"

    def _pending_key(self, user_id: int) -> str:
        return f"{self._user_key(user_id)}:pending"

    @staticmethod
    def _month_bounds(month: str) -> tuple[float, float]:
        year, mon = int(month[:4]), int(month[5:7])
        start = datetime(year, mon, 1, tzinfo=TZ)
        if mon == 12:
            end = datetime(year + 1, 1, 1, tzinfo=TZ)
        else:
            end = datetime(year, mon + 1, 1, tzinfo=TZ)
        return start.timestamp(), end.timestamp()

    @staticmethod
    def _epoch(created_at: str) -> float:
        return datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ).timestamp()

    @staticmethod
    def _row(h: dict | None) -> dict | None:
        if not h:
            return None
        return {
            "id": int(h["id"]),
            "user_id": int(h["user_id"]),
            "amount": float(h["amount"]),
            "description": h.get("description", ""),
            "category": h["category"],
            "created_at": h["created_at"],
            "month": h["month"],
        }

    async def init(self) -> None:
        await self._c().ping()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._loop = None

    async def add_expense(
        self,
        user_id: int,
        amount: float,
        description: str,
        category: str,
        created_at: str,
        month: str,
    ) -> int:
        c = self._c()
        eid = await c.incr(f"{self._prefix}:expenses:id")
        pipe = c.pipeline(transaction=True)
        try:
            pipe.hset(
                self._expense_key(eid),
                mapping={
                    "id": eid,
                    "user_id": user_id,
                    "amount": amount,
                    "description": description.strip(),
                    "category": category,
                    "created_at": created_at,
                    "month": month,
                },
            )
            pipe.zadd(self._expenses_zset(user_id), {str(eid): self._epoch(created_at)})
            await pipe.execute()
        finally:
            await pipe.aclose()
        return eid

    async def last_expense(self, user_id: int) -> dict | None:
        ids = await self._c().zrevrange(self._expenses_zset(user_id), 0, 0)
        if not ids:
            return None
        h = await self._c().hgetall(self._expense_key(int(ids[0])))
        return self._row(h)

    async def delete_expense(self, user_id: int, row_id: int) -> bool:
        c = self._c()
        owner = await c.hget(self._expense_key(row_id), "user_id")
        if owner is None or int(owner) != user_id:
            return False
        pipe = c.pipeline(transaction=True)
        try:
            pipe.delete(self._expense_key(row_id))
            pipe.zrem(self._expenses_zset(user_id), str(row_id))
            await pipe.execute()
        finally:
            await pipe.aclose()
        return True

    async def month_expenses(self, user_id: int, month: str) -> list[dict]:
        lo, hi = self._month_bounds(month)
        c = self._c()
        ids = await c.zrangebyscore(self._expenses_zset(user_id), lo, f"({hi}")
        ids.reverse()
        if not ids:
            return []
        pipe = c.pipeline(transaction=False)
        try:
            for i in ids:
                pipe.hgetall(self._expense_key(int(i)))
            rows = await pipe.execute()
        finally:
            await pipe.aclose()
        out = [self._row(h) for h in rows]
        return [r for r in out if r]

    async def set_salary(self, user_id: int, month: str, amount: float) -> None:
        await self._c().set(self._salary_key(user_id, month), repr(float(amount)))

    async def get_salary(self, user_id: int, month: str) -> float | None:
        value = await self._c().get(self._salary_key(user_id, month))
        return float(value) if value is not None else None

    async def set_budget(self, user_id: int, category: str, amount: float) -> None:
        await self._c().hset(self._budgets_key(user_id), category, repr(float(amount)))

    async def clear_budget(self, user_id: int, category: str) -> bool:
        c = self._c()
        key = self._budgets_key(user_id)
        exists = await c.hexists(key, category)
        if not exists:
            return False
        await c.hdel(key, category)
        return True

    async def get_budgets(self, user_id: int) -> dict[str, float]:
        raw = await self._c().hgetall(self._budgets_key(user_id))
        return {category: float(limit) for category, limit in raw.items()}

    async def set_pending(self, user_id: int, amount: float, desc: str) -> None:
        c = self._c()
        key = self._pending_key(user_id)
        pipe = c.pipeline(transaction=True)
        try:
            pipe.hset(
                key,
                mapping={
                    "amount": repr(float(amount)),
                    "desc": desc.strip(),
                    "ts": repr(time.time()),
                },
            )
            pipe.expire(key, PENDING_TTL)
            await pipe.execute()
        finally:
            await pipe.aclose()

    async def pop_pending(self, user_id: int) -> dict | None:
        c = self._c()
        key = self._pending_key(user_id)
        raw = await c.hgetall(key)
        if not raw:
            return None
        await c.delete(key)
        return {
            "amount": float(raw["amount"]),
            "desc": raw.get("desc", ""),
            "ts": float(raw["ts"]),
        }


_redis_url = os.getenv("REDIS_URL", "").strip()
_libsql_url = os.getenv("LIBSQL_URL", "").strip()
_token = os.getenv("LIBSQL_AUTH_TOKEN", "").strip()

if _redis_url:
    store: SqliteStore | LibsqlStore | RedisStore = RedisStore(_redis_url)
elif _libsql_url:
    store = LibsqlStore(_libsql_url, _token)
else:
    store = SqliteStore()
