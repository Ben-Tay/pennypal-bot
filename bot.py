from __future__ import annotations

import csv
import logging
import os
import sys
import time
from datetime import datetime
from io import BytesIO

from dotenv import load_dotenv

load_dotenv()

from categorize import CATEGORIES, TOTAL_KEY, guess_category, resolve_category
from reports import build_report, parse_budget_target
from store import store
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from utils import (
    TZ,
    bar,
    current_month,
    days_left_in_month,
    escape,
    fmt_money,
    month_label,
    parse_amount,
    parse_entry,
)

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

OWNER_ID = os.getenv("OWNER_ID", "").strip()
PENDING_TTL = 900

CHART_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "charts")

BOT_COMMANDS = [
    ("start", "Welcome and quick guide"),
    ("salary", "Set this month's income"),
    ("budget", "Set or view monthly caps"),
    ("summary", "Full report with chart"),
    ("history", "Recent entries"),
    ("undo", "Delete last entry"),
    ("export", "Download CSV"),
    ("help", "Full guide"),
]


def restricted(handler):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if OWNER_ID and update.effective_user and str(update.effective_user.id) != OWNER_ID:
            return
        return await handler(update, context)

    return wrapper


def category_keyboard(expense_id: int | None = None) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for i, category in enumerate(CATEGORIES):
        suffix = f":{expense_id}" if expense_id else ""
        row.append(
            InlineKeyboardButton(
                category.replace(" & ", "/"), callback_data=f"cat:{category}{suffix}"
            )
        )
        if len(row) == 3 or i == len(CATEGORIES) - 1:
            rows.append(row)
            row = []
    return InlineKeyboardMarkup(rows)


async def budget_status_line(user_id: int, category: str) -> tuple[str | None, bool]:
    budgets = await store.get_budgets(user_id)
    limit = budgets.get(category)
    total_limit = budgets.get(TOTAL_KEY)
    expenses = await store.month_expenses(user_id, current_month())

    parts = []
    alert = False
    if limit:
        value = sum(e["amount"] for e in expenses if e["category"] == category)
        pct = value / limit * 100
        line = f"{category}: {fmt_money(value)} / {fmt_money(limit)} [{bar(pct)}] {pct:.0f}%"
        if pct >= 100:
            alert = True
        elif pct >= 80:
            alert = True
            line += " (close to limit)"
        parts.append(line)
    if total_limit:
        value = sum(e["amount"] for e in expenses)
        pct = value / total_limit * 100
        parts.append(f"Total: {fmt_money(value)} / {fmt_money(total_limit)} [{bar(pct)}] {pct:.0f}%")
        alert = alert or pct >= 100
    if not parts:
        return None, False
    return "\n".join(parts), alert


async def save_and_confirm(update: Update, user_id: int, amount: float, desc: str, category: str):
    now = datetime.now(TZ)
    month_key = current_month(now)
    expense_id = await store.add_expense(
        user_id, amount, desc, category, now.strftime("%Y-%m-%d %H:%M:%S"), month_key
    )
    status, alert = await budget_status_line(user_id, category)
    text = f"Logged #{expense_id}: <b>{escape(fmt_money(amount))}</b> - {escape(desc)}\nCategory: <b>{escape(category)}</b>"
    if status:
        text += "\n\n<pre>" + escape(status) + "</pre>"
    if alert:
        left_days = days_left_in_month()
        text += "\n<b>Warning:</b> budget nearly used or exceeded."
        if left_days > 0:
            text += f" {left_days} day(s) left this month."
    text += "\n<i>Wrong entry? Send /undo</i>"
    await update.effective_message.reply_html(text)


@restricted
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(
        "Hi! I am PennyPal, your monthly money sidekick.\n\n"
        "<b>Add an expense by just typing it:</b>\n"
        "<code>12.50 kopi</code>\n"
        "<code>grab $18.20 home</code>\n"
        "<code>89.90 uniqlo jacket</code>\n\n"
        "I guess the category automatically. If unsure, I will show buttons to pick.\n\n"
        "<b>Commands</b>\n"
        "/salary 5200 - set this month's income\n"
        "/budget food 400 - set a category cap\n"
        "/budget total 2500 - overall monthly cap\n"
        "/budget - see budget report\n"
        "/summary - full report + chart\n"
        "/history 10 - recent entries\n"
        "/undo - delete last entry\n"
        "/export - CSV of this month\n"
        "/help - full guide",
    )


@restricted
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    categories_text = ", ".join(CATEGORIES)
    await update.message.reply_html(
        "<b>How to use PennyPal</b>\n\n"
        "<b>Log expenses</b> - send any message containing an amount:\n"
        "<code>5.50 chicken rice</code> or <code>$3.80 teh</code>\n"
        "I detect the category from keywords; otherwise I ask with buttons.\n\n"
        "<b>/salary</b> &lt;amount&gt; - set income for this month\n"
        "<b>/salary clear</b> - remove this month's salary\n"
        "<b>/budget</b> &lt;category&gt; &lt;amount&gt; - set a monthly cap\n"
        "Example: <code>/budget food 400</code>, <code>/budget transport 150</code>, "
        "<code>/budget total 2500</code>\n"
        "<b>/budget clear food</b> - remove a cap\n"
        "<b>/summary</b> - full month report + donut chart photo\n"
        "<b>/history</b> [n] - last n entries (default 10)\n"
        "<b>/undo</b> - delete your latest expense\n"
        "<b>/export</b> - download this month as CSV\n\n"
        f"<b>Categories:</b> {escape(categories_text)}\n\n"
        f"All times use {TZ.key}.",
    )


@restricted
async def cmd_salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    month_key = current_month()
    args = context.args
    if not args:
        salary = await store.get_salary(uid, month_key)
        label = month_label(month_key)
        if salary:
            await update.message.reply_html(
                f"Income set for {escape(label)}: <b>{escape(fmt_money(salary))}</b>\nUpdate with /salary 5200",
            )
        else:
            await update.message.reply_html(
                f"No income set for {escape(label)} yet.\nExample: <code>/salary 5200</code>",
            )
        return
    if args[0].lower() in ("clear", "remove", "none"):
        await store.set_salary(uid, month_key, 0.0)
        await update.message.reply_html("Salary cleared for this month.")
        return
    amount = parse_amount(" ".join(args))
    if amount is None:
        await update.message.reply_html("Usage: <code>/salary 5200</code>")
        return
    await store.set_salary(uid, month_key, amount)
    await update.message.reply_html(
        f"Income for {escape(month_label(month_key))} set to <b>{escape(fmt_money(amount))}</b>. "
        "Check /summary to see what's left.",
    )


@restricted
async def cmd_budget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = context.args
    if not args:
        text, _, _ = await build_report(uid, current_month())
        await update.message.reply_html(text)
        return
    if args[0].lower() == "clear":
        target = " ".join(args[1:])
        if not target or target.lower() in ("total", "overall", "all"):
            await store.clear_budget(uid, TOTAL_KEY)
            await update.message.reply_html("Total budget cleared.")
            return
        category = resolve_category(target)
        if category is None:
            await update.message.reply_html(f"Unknown category: {escape(target)}")
            return
        await store.clear_budget(uid, category)
        await update.message.reply_html(f"Budget for {escape(category)} cleared.")
        return
    category, amount = parse_budget_target(" ".join(args))
    if amount is None:
        await update.message.reply_html(
            "Usage: <code>/budget food 400</code> or <code>/budget total 2500</code>\n"
            "Send /budget alone to view everything.",
        )
        return
    if category is None:
        await update.message.reply_html(
            "Unknown category. Try one of:\n"
            + escape(", ".join(CATEGORIES))
            + "\nOr use: /budget total 2500",
        )
        return
    name = "Total" if category == TOTAL_KEY else category
    await store.set_budget(uid, category, amount)
    await update.message.reply_html(
        f"Monthly cap for <b>{escape(name)}</b> set to <b>{escape(fmt_money(amount))}</b>."
    )


@restricted
async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    month_key = current_month()
    text, totals, meta = await build_report(uid, month_key)
    await update.message.reply_html(text)
    if totals:
        os.makedirs(CHART_DIR, exist_ok=True)
        chart_path = os.path.join(CHART_DIR, "month.png")
        try:
            from charts import spending_chart

            spending_chart(totals, chart_path, fmt_money(meta["spent"]))
            caption = f"{month_label(month_key)} spending"
            with open(chart_path, "rb") as photo:
                await update.message.reply_photo(photo=photo, caption=caption)
        except Exception:
            logging.exception("chart generation failed")


@restricted
async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    n = 10
    if context.args:
        try:
            n = max(1, min(50, int(context.args[0])))
        except ValueError:
            pass
    rows = (await store.month_expenses(uid, current_month()))[:n]
    if not rows:
        await update.message.reply_html(
            "No expenses logged yet this month. Try: <code>12.50 kopi</code>"
        )
        return
    lines = []
    total = 0.0
    for r in reversed(rows):
        total += r["amount"]
        dt = datetime.strptime(str(r["created_at"]), "%Y-%m-%d %H:%M:%S")
        date_part = dt.strftime("%b %d")
        desc = str(r["description"])[:22].ljust(22)
        cat = str(r["category"])[:14].ljust(14)
        lines.append(f"{date_part}  {r['amount']:>9,.2f}  {desc}{cat}")
    header = (
        f"<b>Last {len(lines)} entries - {escape(month_label(current_month()))}</b>\n<pre>"
    )
    footer = "</pre>Total shown: <b>" + escape(fmt_money(total)) + "</b>"
    await update.message.reply_html(header + escape("\n".join(lines)) + footer)


@restricted
async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    last = await store.last_expense(uid)
    if not last:
        await update.message.reply_html("Nothing to undo.")
        return
    deleted = await store.delete_expense(uid, last["id"])
    if not deleted:
        await update.message.reply_html("Nothing to undo.")
        return
    dt = datetime.strptime(str(last["created_at"]), "%Y-%m-%d %H:%M:%S")
    await update.message.reply_html(
        f"Deleted #{last['id']}: <b>{escape(fmt_money(last['amount']))}</b> - "
        f"{escape(str(last['description']))} ({escape(str(last['category']))}, {dt.strftime('%b %d')})",
    )


@restricted
async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    month_key = current_month()
    rows = await store.month_expenses(uid, month_key)
    if not rows:
        await update.message.reply_html("Nothing to export yet this month.")
        return
    buf = BytesIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "amount", "category", "description"])
    for r in sorted(rows, key=lambda x: x["created_at"]):
        writer.writerow([r["created_at"], f"{r['amount']:.2f}", r["category"], r["description"]])
    buf.seek(0)
    buf.name = f"expenses-{month_key}.csv"
    await update.message.reply_document(document=buf, filename=buf.name)


@restricted
async def handle_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = " ".join(context.args)
    if not text:
        await update.message.reply_html("Usage: <code>/add 12.50 kopi</code>")
        return
    parsed = parse_entry(text)
    if parsed is None:
        await update.message.reply_html(
            "Could not read that. Example: <code>/add 12.50 kopi</code>"
        )
        return
    amount, desc = parsed
    category = guess_category(desc)
    if category:
        await save_and_confirm(update, uid, amount, desc, category)
        return
    await store.set_pending(uid, amount, desc)
    await update.message.reply_html(
        f"How should I file <b>{escape(fmt_money(amount))}</b> - {escape(desc)}?",
        reply_markup=category_keyboard(),
    )


@restricted
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    parsed = parse_entry(update.message.text or "")
    if parsed is None:
        await update.message.reply_html(
            "I did not find an amount in that.\nTry: <code>12.50 lunch at max</code> or <code>grab $18 home</code>",
        )
        return
    amount, desc = parsed
    category = guess_category(desc)
    if category:
        await save_and_confirm(update, uid, amount, desc, category)
        return
    await store.set_pending(uid, amount, desc)
    await update.message.reply_html(
        f"How should I file <b>{escape(fmt_money(amount))}</b> - {escape(desc)}?",
        reply_markup=category_keyboard(),
    )


@restricted
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    parts = query.data.split(":")
    category = parts[1]
    pending = await store.pop_pending(uid)
    if pending is None or time.time() - pending["ts"] > PENDING_TTL:
        await query.edit_message_text("This selection expired. Please send the expense again.")
        return
    await save_and_confirm(update, uid, pending["amount"], pending["desc"], category)


@restricted
async def handle_unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html("Unknown command. Send /help to see what I can do.")


def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler(["start"], cmd_start))
    app.add_handler(CommandHandler(["help"], cmd_help))
    app.add_handler(CommandHandler(["salary"], cmd_salary))
    app.add_handler(CommandHandler(["budget"], cmd_budget))
    app.add_handler(CommandHandler(["summary", "report"], cmd_summary))
    app.add_handler(CommandHandler(["history"], cmd_history))
    app.add_handler(CommandHandler(["undo"], cmd_undo))
    app.add_handler(CommandHandler(["export"], cmd_export))
    app.add_handler(CommandHandler(["add", "spend"], handle_add))
    app.add_handler(CallbackQueryHandler(handle_button, pattern=r"^cat:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.COMMAND, handle_unknown_command))


async def post_init(application: Application):
    await store.init()
    await application.bot.set_my_commands(BOT_COMMANDS)


def main():
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        print("Missing BOT_TOKEN. Copy .env.example to .env and paste your BotFather token.")
        sys.exit(1)
    app = Application.builder().token(token).post_init(post_init).build()
    register_handlers(app)
    app.run_polling()


if __name__ == "__main__":
    main()
