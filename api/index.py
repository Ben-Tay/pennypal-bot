import asyncio
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("pennypal.webhook")

TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()

from flask import Flask, Response, request
from telegram import Update
from telegram.ext import Application

import bot as bot_module
from store import store

application = None
_ready = False

if TOKEN:
    application = Application.builder().token(TOKEN).updater(None).build()
    bot_module.register_handlers(application)

app = Flask(__name__)


async def process_update(body: dict) -> None:
    global _ready
    async with application:
        if not _ready:
            await store.init()
            await application.bot.set_my_commands(bot_module.BOT_COMMANDS)
            _ready = True
        update = Update.de_json(body, application.bot)
        if update is not None:
            await application.process_update(update)
    close = getattr(store, "close", None)
    if close is not None:
        await close()


@app.route("/", defaults={"path": ""}, methods=["GET"])
@app.route("/<path:path>", methods=["GET"])
def health(path: str) -> Response:
    return Response("PennyPal webhook is running\n", mimetype="text/plain")


@app.route("/", defaults={"path": ""}, methods=["POST"])
@app.route("/<path:path>", methods=["POST"])
def entry(path: str):
    if not application:
        return Response("BOT_TOKEN is not configured\n", status=500)
    if WEBHOOK_SECRET and request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        return Response("forbidden\n", status=403)
    try:
        body = request.get_json(force=True, silent=True) or {}
        asyncio.run(process_update(body))
    except Exception:
        log.exception("failed handling update")
    return Response("ok", mimetype="text/plain")
