# PennyPal - Telegram Expense Tracker

Track your monthly expenses and salary by chatting with a Telegram bot.
Type an expense in plain English ("`12.50 kopi`"), and PennyPal logs it,
guesses the category automatically, warns you when you approach your
budget caps, and sends you a monthly report with a donut chart.

## Features

- **Quick add** - just send `5.50 chicken rice` or `grab $18.20 home`
- **Auto-categorization** - 100+ keywords map descriptions to 11 categories
  (SG hawker life included: kopi, mala, dabao, NTUC, Grab, ERP...)
- **Inline category picker** - if the bot can't guess, it shows buttons
- **Salary tracking** - `/salary 5200`, see what's left of your income
- **Budget caps** - per-category (`/budget food 400`) plus a total cap
  (`/budget total 2500`), with warnings at 80% and 100%
- **Monthly report + chart** - `/summary` sends a text breakdown and a
  donut chart photo, including "safe daily spend" for the rest of the month
- **History / undo / export** - `/history`, `/undo`, `/export` (CSV)
- **Two storage modes** - local SQLite for personal use, or Turso cloud DB
  + Vercel webhook hosting so the bot is up 24/7 for multiple users

## Setup (run locally)

1. **Create the bot on Telegram**
   - Open Telegram, talk to [@BotFather](https://t.me/BotFather)
   - Send `/newbot`, choose a name and username
   - Copy the token it gives you

2. **Install Python 3.10+**, then:

   ```powershell
   cd "expense-tracker"
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. **Configure**

   ```powershell
   Copy-Item .env.example .env
   ```

   Edit `.env` and paste your token into `BOT_TOKEN`.
   Optionally set `OWNER_ID` to your numeric Telegram user id so only
   you can use the bot (get it from @userinfobot).

4. **Run**

   ```powershell
   python bot.py
   ```

   Open your bot in Telegram and send `/start`.

With no extra config, data is stored locally in `data/expenses.db`.

## Usage cheatsheet

| Action | Example |
| --- | --- |
| Add expense | `12.50 kopi` or `$18.20 grab home` |
| Add with explicit command | `/add 89.90 uniqlo jacket` |
| Set salary | `/salary 5200` |
| Set category budget | `/budget food 400` |
| Set total budget | `/budget total 2500` |
| View report | `/budget` or `/summary` (with chart) |
| Recent entries | `/history 15` |
| Delete last entry | `/undo` |
| Export CSV | `/export` |

Categories: Food & Drinks, Groceries, Transport, Bills & Utilities, Rent,
Shopping, Entertainment, Health & Fitness, Travel, Education,
Gifts & Donations, Others.

## Customization

- **Currency / timezone**: edit `CURRENCY` and `TIMEZONE` in `.env`
- **Categories & keywords**: edit `categorize.py` - add your own keywords
  to `KEYWORDS` or shortcuts to `ALIASES`
- **Report layout**: see `reports.py`

## Data

Everything lives in `data/expenses.db` (SQLite) when running locally, or in
your Upstash Redis / Turso cloud database when `REDIS_URL` / `LIBSQL_URL`
is set (see below). Charts are written to `data/charts/`. Back up or
`/export` occasionally.

## Hosting on Vercel (24/7, free, multi-user)

The bot ships with a webhook mode (`api/index.py`) designed for Vercel's
free tier: Telegram pushes each message to a tiny serverless function, and
expenses live in **Upstash Redis** (free serverless Redis) instead of a
local file. Anyone can then use the bot anytime, even with your PC off.

### 1. Create the cloud database

1. Sign up at [upstash.com](https://upstash.com) (free tier is ample)
2. Create a database - pick the region closest to you (e.g. ap-southeast-1)
3. Open its **Connect** page and copy the endpoint under
   **"Redis Connect" / native protocol**: it looks like
   `rediss://default:<password>@<host>.upstash.io:6379`

No schema/migration step needed - Redis is schemaless.

### 2. Test locally (optional but recommended)

Put `REDIS_URL=<that rediss:// url>` into your `.env`, then:

```powershell
$env:TEST_REDIS_URL = (Get-Content .env | Select-String "REDIS_URL=").Line.Split("=",2)[1]
python smoke_test.py
```

You should see `REDIS SUITE OK`. From now on, local runs of `python bot.py`
share the same cloud data as the deployed bot.

### 3. Deploy to Vercel

```powershell
npm i -g vercel      # once; needs Node.js
vercel login
vercel link
vercel env add BOT_TOKEN                # paste your BotFather token
vercel env add REDIS_URL                # paste the rediss:// URL
py -c "import secrets; print(secrets.token_hex(32))"   # copy this secret
vercel env add TELEGRAM_WEBHOOK_SECRET  # paste that secret
vercel deploy --prod
```

Leave `OWNER_ID` unset so friends can use it too. Note the deployment URL
(e.g. `https://pennypal.vercel.app`).

### 4. Point Telegram at your deployment

Add the same `TELEGRAM_WEBHOOK_SECRET` to your local `.env`, then:

```powershell
python scripts/set_webhook.py https://YOUR-PROJECT.vercel.app/webhook
```

Done. Message your bot from any account - it responds 24/7.

### How your data maps to Redis

A nice crash course while you use the app - inspect it anytime with
Upstash's built-in CLI in their dashboard:

| Key pattern | Type | Holds |
| --- | --- | --- |
| `pennypal:expenses:id` | string counter | auto-increment expense IDs |
| `pennypal:expense:{id}` | hash | one expense record (amount, category...) |
| `pennypal:user:{uid}:expenses` | sorted set | timeline: members are ids, scores are timestamps |
| `pennypal:user:{uid}:salary:{YYYY-MM}` | string | that month's income |
| `pennypal:user:{uid}:budgets` | hash | category -> monthly cap |
| `pennypal:user:{uid}:pending` | hash, 15-min TTL | expense awaiting a category button press |

Commands used under the hood: `INCR`, `HSET/HGETALL/HDEL`, `ZADD`,
`ZRANGEBYSCORE` (month filtering by timestamp range), `ZREVRANGE`
(newest entry), and transactional `MULTI/EXEC` pipelines for writes.

### Alternatives

The storage layer (`store.py`) also ships a **Turso/libSQL** backend
(SQLite dialect over HTTPS): set `LIBSQL_URL` + `LIBSQL_AUTH_TOKEN`
instead of `REDIS_URL` and run `python scripts/init_turso.py` once.
Backend precedence: `REDIS_URL` > `LIBSQL_URL` > local SQLite file.

### Notes on the Vercel setup

- Local `python bot.py` still works for testing.
- First reply after idle time can be slow (~10s cold start); later
  messages are instant while the function stays warm.
- The monthly donut chart requires matplotlib, which inflates Vercel's
  bundle but fits within the free limit.
- To switch back to local-only mode: remove `REDIS_URL` from `.env`.

## Running on your own PC instead (optional)

Keep `python bot.py` running whenever you want the bot up. To auto-start
it on login, put a shortcut to a `.bat` file containing
`cd /d "%~dp0" && .venv\Scripts\python.exe bot.py` into the Startup folder
(`Win+R` -> `shell:startup`). Remember the bot only responds while the PC
is on.
