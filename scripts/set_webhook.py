import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from telegram import Bot


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/set_webhook.py https://your-app.vercel.app/webhook")
        sys.exit(1)
    url = sys.argv[1]
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    token = os.getenv("BOT_TOKEN", "").strip()
    ok = await Bot(token).set_webhook(
        url=url, secret_token=secret or None, allowed_updates=["message", "callback_query"]
    )
    info = await Bot(token).get_webhook_info()
    print("set_webhook:", ok)
    print("url:", info.url)


asyncio.run(main())
