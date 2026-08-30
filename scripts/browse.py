import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()


async def main() -> int:
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        print("REDIS_URL is not set in .env")
        return 1
    import store as store_mod

    r = store_mod.RedisStore(url)
    try:
        c = r._c()
        args = sys.argv[1:]
        if not args:
            keys = [k async for k in c.scan_iter(match="*")]
            for k in sorted(keys):
                t = await c.type(k)
                print(f"{t:>7}  {k}")
            print(f"\n{len(keys)} key(s). Inspect one: python scripts/browse.py <key>")
            return 0
        key = args[0]
        t = await c.type(key)
        if t == "none":
            print(f"'{key}' does not exist")
            return 1
        if t == "string":
            print(await c.get(key))
        elif t == "hash":
            for field, value in (await c.hgetall(key)).items():
                print(f"{field}: {value}")
        elif t == "zset":
            for member, score in await c.zrange(key, 0, -1, withscores=True):
                print(f"{score:.3f}  {member}")
        else:
            print(f"type '{t}' not supported here")
            return 1
        return 0
    finally:
        await r.close()


raise SystemExit(asyncio.run(main()))
