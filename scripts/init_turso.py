import asyncio
import os

from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    url = os.getenv("LIBSQL_URL", "").strip()
    if not url:
        print("LIBSQL_URL is not set. Add your Turso URL and LIBSQL_AUTH_TOKEN to .env first.")
        raise SystemExit(1)
    import store

    await store.init()
    print("Schema ready at:", url)


asyncio.run(main())
