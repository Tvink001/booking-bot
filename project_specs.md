# Project Specification — Booking Bot

This is the technical source of truth for the project. Sections marked **filled** contain decisions known before development begins, verified through Context7 where library facts are involved. Sections marked **TBD via Prompt N** are completed during development; Claude Code fills them after the corresponding build step, and the operator reviews.

This file is read by Claude Code on every prompt (per `CLAUDE.md` Rule 1) and written to whenever new decisions get made (per `CLAUDE.md` Rule 6). The operator approves changes before they're committed.

All library version claims and API shape claims in this document were verified through Context7 in May 2026. Re-verify before relying on any specific detail at build time — that's the whole point of the Context7 discipline.

---

# 1. Product Summary [filled]

A Telegram bot that handles the full appointment-booking lifecycle for a small service business (salon, barbershop, dance studio, beauty studio, therapist office). The customer interacts via inline keyboards — selects a service, then a master, then a date, then a time slot, then provides a name and phone — and gets a confirmation message plus automatic reminders at 24 hours and 1 hour before the appointment. The business owner manages everything from Google Sheets, which acts as a lightweight CRM.

**Customer flow target:** complete booking in ≤10 button taps.

**Owner flow target:** see every new booking in Sheets within 2 seconds, get a Telegram notification in a private owner chat, and use admin commands (`/today`, `/week`, `/stats`, `/export`) for daily operations.

**Three WOW features** distinguish this from a basic booking bot and directly address gaps mentioned in real Freelancehunt project bids (1617411, 1260079, 1564930):
1. Google Calendar two-way sync — if a master manually blocks time in their calendar, the bot's slot availability reflects that.
2. Automatic VIP status — after 5 completed visits, the client gets a ⭐ marker and a promo-code notification before their 6th booking.
3. Voice name input — at the contact-entry step, the client can record a voice message; Groq Whisper-Large-v3-turbo transcribes it and extracts the name (free tier; see §2.1 for why Groq replaced OpenAI in the original brief).

---

# 2. Tech Stack [filled, Context7-verified May 2026]

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | 3.12 acceptable; 3.13 not yet broadly compatible with all libraries below |
| Bot framework | aiogram 3.27 (current stable, May 2026) | v4.x is alpha — do not use. Verified via Context7 `/websites/aiogram_dev_en_v3_27_0`. `StatesGroup`, `FSMContext`, `Router`, `Dispatcher` |
| Web server | aiohttp | Comes with aiogram; required for webhook receiver via `SimpleRequestHandler` + `setup_application` |
| Storage | gspread v6.x (sync) | Wrapped via `asyncio.to_thread` in async handlers. **Note:** `get_records()` was removed in v6 — use `get_all_records(head=1)` instead. `gspread_asyncio` exists but has low maintenance signal (7 snippets, benchmark 45) — do not use |
| Scheduler | APScheduler 4.0.0a6 (current pre-release; 4.0.0 stable not yet on PyPI as of Prompt 2 build) | **Major API change from v3 documented in section 2.2**. Verified via Context7 `/agronholm/apscheduler`. Uses `AsyncScheduler`, `SQLAlchemyDataStore` + `CBORSerializer`, `add_schedule`, `IntervalTrigger`/`DateTrigger`/`CronTrigger`, `ConflictPolicy.replace`. **Pin in pyproject:** `apscheduler==4.0.0a6` — see §2.1. |
| Scheduler persistence | aiosqlite + SQLAlchemy async engine | `sqlite+aiosqlite:///data/scheduler.db`. Tables auto-created by `SQLAlchemyDataStore` |
| Calendar | google-api-python-client (sync) | `googleapiclient.discovery.build('calendar', 'v3', credentials=...)`. Wrapped via `to_thread` in async handlers. Context manager (`with build(...) as service:`) is supported and closes connections cleanly |
| Auth (Sheets + Calendar) | google-auth `service_account.Credentials.from_service_account_file()` | Single service account shared with each master's calendar and the bookings Sheet |
| Voice transcription | groq v0.13.x (`AsyncGroq` client) | `client.audio.transcriptions.create(model="whisper-large-v3-turbo", file=..., language="ru", response_format="text")`. OpenAI-compatible endpoint, **free tier** (no credit card), Whisper v3 generation (better UA/RU accuracy than OpenAI's `whisper-1`). Verified via Context7 `/groq/groq-python` and `/websites/console_groq` |
| Config | pydantic-settings 2.7.0 | `BaseSettings` + `SettingsConfigDict(env_file='.env', case_sensitive=False, extra='ignore')`. `SecretStr` from `pydantic`. **2.7.0 minimum** required for the `NoDecode` annotation (see §10.1 `bot/config.py`). |
| Linting/typing | ruff + mypy strict | Pre-commit hook recommended |
| Tests | pytest + pytest-asyncio | Cover pure functions in `slots.py` and state-transition tests |
| Deploy target | Railway (Dockerfile) | Persistent volume mounted at `/app/data` for SQLite scheduler.db |

## 2.1 Why these versions

**aiogram 3.27, not 4.x.** v4 is alpha as of May 2026; the `dev-3.x` branch is the actively maintained docs source. Context7 returns the v3.27 docs page as the most snippet-dense source (9054 snippets, source reputation High). Pin `aiogram==3.27.0` in `pyproject.toml`. Re-verify before pinning in case 3.28 has shipped by build time.

**APScheduler 4.0+, not 3.x.** The brief specifies "APScheduler with SQLite (jobstore=SQLAlchemyJobStore)" — that is v3.x syntax. v4 was released and is the current major. The migration is non-trivial: see 2.2 below. **Reality discovered during Prompt 2 install:** APScheduler 4.0.0 stable does **not** exist on PyPI (latest stable is `3.11.2`); v4 ships only as alphas (latest `4.0.0a6`). The new v4 API documented in §9.3 lives in those alphas. We pin `apscheduler==4.0.0a6` rather than downgrading to v3 (which would invalidate §9.3, §14, §10.4). Re-verify before each major rev — once 4.0.0 stable ships, bump to it.

**gspread sync + `to_thread`, not gspread_asyncio.** Verified via Context7: `gspread_asyncio` has 7 code snippets and benchmark score 45 (compare to gspread itself at 239 snippets, score 82). Low signal of active maintenance. Sync gspread is well-supported; `asyncio.to_thread` is the idiomatic async wrapping pattern.

**Heads-up on gspread v6 migration.** v6 removed `Worksheet.get_records()` in favor of `Worksheet.get_all_records(head=1)`. AI-generated code that targets pre-v6 API will raise `AttributeError` at runtime. For partial-range record reads, use `worksheet.get(range)` + `gspread.utils.to_records(header, cells)`. This is the single most likely surprise in the storage layer for May 2026.

**google-api-python-client, not google-cloud-* libraries.** For Calendar, the discovery-based `google-api-python-client` is the standard Python entry point. Verified via Context7 — exact import is `googleapiclient.discovery.build`.

**groq, not openai, for Whisper.** Original brief assumed OpenAI Whisper. Context7 (May 2026) surfaced two facts that flipped the decision:
- OpenAI's "Free" rate-limit tier is officially "Not supported" for API access. The often-cited "$5 onboarding credit" is a marketing perk (not a documented policy), requires a credit card, and expires in ~3 months. For a portfolio project that should keep running without billing, OpenAI is a poor fit.
- Groq exposes an OpenAI-compatible audio endpoint with a **permanent free tier** (audio-seconds-per-day quotas easily covering portfolio demo traffic) and runs the newer `whisper-large-v3` / `whisper-large-v3-turbo` models — v3 architecture, measurably better multilingual accuracy than OpenAI's `whisper-1` (v2).

The Python SDK is `groq` (`pip install groq`). The async client is `AsyncGroq`. The call shape matches OpenAI's exactly (`client.audio.transcriptions.create(...)`), so swapping back to OpenAI later, if ever needed, is a 3-line change.

**pydantic-settings v2 as a separate package**, not `pydantic[settings]`. Pydantic v2 split settings into its own package. Verified via Context7: import is `from pydantic_settings import BaseSettings, SettingsConfigDict`.

**Bumped to pydantic-settings 2.7.0 during Prompt 2** (from skeleton's 2.6.1). Reason: 2.6.1 lacks the `NoDecode` annotation. Without it, the `admin_telegram_ids: list[int]` field is treated as "complex", and pydantic-settings tries `json.loads("1,2,3")` before the field validator runs → `JSONDecodeError`. The `NoDecode` annotation (added in 2.7.0) tells pydantic-settings to pass the raw string straight to the validator, where the CSV-split happens. See §10.1 `bot/config.py` design notes.

## 2.2 Deviations from Brief

**APScheduler API rewrite.** The brief specifies:
> `APScheduler с хранилищем в SQLite (jobstore=SQLAlchemyJobStore)`

That is APScheduler 3.x syntax. APScheduler 4 has a completely new API:

| Brief (v3) | Actual (v4) |
|---|---|
| `AsyncIOScheduler` | `AsyncScheduler` |
| `SQLAlchemyJobStore` | `SQLAlchemyDataStore` |
| `scheduler.add_job(...)` | `await scheduler.add_schedule(...)` |
| `jobstore='default'` arg | `data_store=` constructor arg |
| Sync-by-default | Async-by-default, `async with AsyncScheduler(...)` lifecycle |
| `BackgroundScheduler` | `start_in_background()` method |

This build uses APScheduler 4. Code samples from older tutorials will not work.

**OAuth flow for masters replaced with calendar sharing.** The brief mentions:
> Google Calendar API: тот же service account + OAuth для мастеров

A per-master OAuth flow requires a consent screen, a redirect URL, persistent token storage, and refresh-token handling per master. For this build, we use a simpler model: each master shares their personal Google Calendar with the bot's service account email (via Calendar Settings → Share with specific people → service-account@*.iam.gserviceaccount.com → "Make changes to events"). The service account then reads and writes events on each calendar without any OAuth flow. This matches how the Sheets credential works and avoids ~200 lines of OAuth code. Trade-off: each master has to do a one-time share action; no programmatic onboarding.

**Brief-specified library/model versions are timestamps.** Anywhere the brief specifies a model string (e.g. Claude 3.5 Haiku, OpenAI Whisper) or a version pin, treat it as a starting hint. Verify the current production version via Context7 before pinning in `requirements.txt`.

---

# 3. Production Configuration [filled]

## 3.1 Required environment variables

Loaded via `pydantic-settings` `BaseSettings` from `.env` locally and Railway env vars in production.

```
# Telegram
BOT_TOKEN=                              # from @BotFather
WEBHOOK_SECRET=                         # any random 32+ char string, used as X-Telegram-Bot-Api-Secret-Token
WEBHOOK_BASE_URL=                       # https://<your-app>.up.railway.app (production only; auto-set by Railway)
OWNER_TELEGRAM_CHAT_ID=                 # negative int for group, positive for DM
ADMIN_TELEGRAM_IDS=                     # comma-separated telegram user IDs allowed to /admin commands

# Google
GOOGLE_SERVICE_ACCOUNT_PATH=/app/secrets/credentials.json   # mounted in Railway
GOOGLE_SHEET_ID=                        # the ID from the Sheet URL
GOOGLE_CALENDAR_DEFAULT_TZ=Europe/Kyiv

# Groq (for WOW 3 voice input via Whisper-Large-v3-turbo; permanent free tier, no CC required)
GROQ_API_KEY=

# Mode
MODE=polling                            # polling (local dev) | webhook (production)
WEB_HOST=0.0.0.0
WEB_PORT=8080

# Scheduler
SCHEDULER_DB_PATH=/app/data/scheduler.db
SCHEDULER_TIMEZONE=Europe/Kyiv

# Logging
LOG_LEVEL=INFO
```

## 3.2 Persistent volume

Railway must mount a persistent volume at `/app/data` for the SQLite scheduler database. Without it, every redeploy wipes all scheduled reminders. Reminders for the next 24 hours get lost on each deploy if persistence is broken.

Volume size: 1 GB is far more than needed; pick the smallest available tier.

## 3.3 Webhook secret

The `WEBHOOK_SECRET` env var must be set in production. aiogram's `SimpleRequestHandler` validates incoming requests by comparing this secret to the `X-Telegram-Bot-Api-Secret-Token` header that Telegram includes (Telegram echoes back whatever secret was set in `setWebhook`). Without this, any third party who discovers the webhook URL can POST fake updates and forge user actions.

Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"` once and store in Railway env vars.

## 3.4 Healthcheck endpoint

The aiohttp app must expose `GET /health` returning `200 OK` with body `{"status": "ok"}`. Railway uses this to determine whether a deploy succeeded and to restart on failure. Implementation: a simple aiohttp route added in `main.py` alongside the Telegram webhook handler.

## 3.5 Graceful shutdown

The bot must handle SIGTERM cleanly:
- Stop accepting new Telegram updates
- Wait for in-flight handlers to complete (with a reasonable timeout, e.g. 30s)
- Shut down the scheduler (`await scheduler.stop()`)
- Close gspread / Calendar service objects
- Close aiohttp session

aiogram's `Dispatcher` + aiohttp's `web.run_app` handle most of this; the operator-side responsibility is to register the scheduler shutdown in the `on_shutdown` startup hook.

## 3.6 Error logging

All uncaught exceptions in handlers route to `bot/handlers/errors.py` via aiogram's error handler. Each error: log to stdout (Railway log aggregation) with full traceback, write a sanitized row to the `_errors` Sheet tab, and DM the owner via Telegram with a short summary. Payload sanitization: any field whose name matches `/token|key|password|secret|credential/i` is replaced with `[REDACTED]` before logging.

## 3.7 Rate-limit hygiene

Telegram Bot API limits: 30 messages/second globally, 1 message/second per chat. When iterating over many bookings (e.g. nightly reminder sweep), use `asyncio.sleep(0.05)` between sends to stay under the cap. Google APIs: gspread has implicit rate limits; for bulk writes use `worksheet.batch_update()` instead of repeated single-cell writes.

---

# 4. MCP Setup [filled]

## 4.1 `.mcp.json` in project root

**Template (committed to repo, lives in `project_specs.md` as the reference):**

```json
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": ["-y", "@upstash/context7-mcp"]
    }
  }
}
```

No n8n-MCP for this project — there is no n8n instance.

**Windows operator-side override (carried from P1 learnings, not committed):**

The version that works on this operator's Windows machine has two adjustments:
- `npx` causes a 30-second MCP startup timeout because each invocation re-downloads the package. Install the MCP server globally first (`npm install -g @upstash/context7-mcp`), then point `.mcp.json` at the installed `.cmd` shim directly (typically `C:\Users\<user>\AppData\Roaming\npm\context7-mcp.cmd`, with `args: []`).
- A TLS-intercepting cert chain on this machine breaks both `npm install` and the Node-based MCP runtime. While installing: `npm config set strict-ssl false`, then restore to `true`. At MCP runtime: add `"NODE_TLS_REJECT_UNAUTHORIZED": "0"` to the server's `env` block.

Any secret-bearing values in `.mcp.json` (this project has none today, but Project 3 may add them) must be inlined directly — Claude Code's `${VAR}` substitution resolves from shell env, not from `.env`, and PowerShell does not auto-export `.env`. Solution: inline the secret, add `.mcp.json` to `.gitignore`, keep the template above as the documented reference.

## 4.2 Context7 usage policy

Call Context7 before writing code that touches: aiogram (FSM, handlers, dispatcher, webhook setup), APScheduler 4 (any trigger, jobstore, lifecycle method), gspread (auth, batch operations), google-api-python-client (Calendar event creation, freebusy query, scope strings), groq (audio transcription, async client init, current Whisper model identifiers), pydantic-settings (any new field type or validator).

Do not call Context7 for: standard library, well-stabilized small libraries (aiosqlite basic usage, asyncio primitives), or things you've already verified earlier in the same conversation and have an active reference for.

When in doubt, query. Cost of an unnecessary query: small. Cost of writing against a phantom API: real bugs and wasted operator time.

---

# 5. Development Workflow [filled]

## 5.1 Local development

The bot supports two modes selectable via `MODE` env var:

- **`MODE=polling`** for local dev. Bot connects out to Telegram via long polling. No webhook URL needed. Run via `python -m bot.main`.
- **`MODE=webhook`** for production on Railway. Bot starts an aiohttp server on `WEB_PORT`, registers webhook via `bot.set_webhook(url=WEBHOOK_BASE_URL+"/telegram/webhook", secret_token=WEBHOOK_SECRET)` in the `on_startup` hook.

Local dev requires a `.env` file with at minimum `BOT_TOKEN` (a separate "dev" bot from BotFather is recommended — keep one bot for prod, another for staging tests).

## 5.2 Test pipeline

```bash
# format + lint
ruff check . --fix
ruff format .

# typecheck
mypy bot/

# tests
pytest -v

# manual smoke
MODE=polling python -m bot.main
```

These run locally before every push. `pyproject.toml` configures ruff and mypy strict mode.

## 5.3 Railway deploy

Push to GitHub main → Railway auto-deploys from the Dockerfile. The healthcheck at `/health` determines deploy success. Watch logs via `railway logs --follow` or in Railway dashboard.

First-time deploy requires:
- Connect repo to Railway
- Add persistent volume mounted at `/app/data`
- Upload `credentials.json` as a Railway secret file mounted at `/app/secrets/credentials.json`
- Set all env vars from 3.1
- Set `WEBHOOK_BASE_URL` to the Railway-provided public domain

---

# 6. Architecture Overview [filled]

The bot is a single Python process. Inside the process:

1. **aiohttp web server** (production) hosts two routes: `/telegram/webhook` (receives updates from Telegram) and `/health` (Railway healthcheck)
2. **aiogram Dispatcher** processes updates routed from the webhook receiver; in dev/polling mode it connects directly to Telegram
3. **Router stack** under the Dispatcher: `start_router`, `booking_router`, `my_bookings_router`, `admin_router`, `errors_router`
4. **APScheduler AsyncScheduler** runs in the same event loop, with SQLite-backed jobstore persisting through restarts
5. **Service layer** wraps external APIs: `services.sheets`, `services.calendar`, `services.whisper`, all sync libraries wrapped with `asyncio.to_thread`

State flow for a new booking:
1. User taps inline button → Telegram → webhook receiver → Dispatcher → matching handler in `booking.py`
2. Handler reads FSM state, advances state, writes data via `FSMContext.update_data(...)`
3. At confirmation step: handler calls `services.sheets.append_booking(...)` (which `await to_thread(...)`), `services.calendar.create_event(...)` (same pattern), `services.scheduler.schedule_reminders(booking_id, datetime_start)`
4. Owner gets notification via direct Telegram send to `OWNER_TELEGRAM_CHAT_ID`
5. FSM cleared, user sees "✅ Записаны на ..." with cancel button

Error flow: any unhandled exception in a handler routes to `errors_router` → logged + Sheets `_errors` + DM to owner. The user sees a generic "Что-то пошло не так, попробуйте позже."

---

# 7. Data Model [filled]

Google Sheet with **five tabs** (brief lists four; we add `_errors`).

## 7.1 Sheet `services`

| Col | Name | Type | Notes |
|---|---|---|---|
| A | id | string | Stable slug, e.g. `haircut-30` |
| B | name | string | Display name, e.g. `Стрижка (30 мин)` |
| C | duration_min | int | Used for slot interval calculation |
| D | price | int | UAH; for display only |
| E | master_ids | CSV | Empty = any master can perform this service |
| F | is_active | bool | TRUE to show in selection, FALSE to hide |

## 7.2 Sheet `masters`

| Col | Name | Type | Notes |
|---|---|---|---|
| A | id | string | Stable slug |
| B | name | string | Display name |
| C | telegram_id | int | For sending notifications |
| D | calendar_id | string | Google Calendar ID — e.g. `master.name@gmail.com` |
| E | work_hours | string | `HH:MM-HH:MM`, e.g. `10:00-19:00` |
| F | work_days | CSV ints | ISO weekday — Monday=1, Sunday=7. e.g. `1,2,3,4,5,6` |
| G | is_active | bool | TRUE to show in selection |

## 7.3 Sheet `bookings`

| Col | Name | Type | Notes |
|---|---|---|---|
| A | id | string | UUID generated on create |
| B | client_telegram_id | int | For DM notifications |
| C | client_name | string | From form or Whisper transcription |
| D | client_phone | string | Normalized to +380... |
| E | service_id | string | FK to `services.id` |
| F | master_id | string | FK to `masters.id` |
| G | datetime_start | ISO datetime | TZ: Europe/Kyiv, stored as ISO with offset |
| H | datetime_end | ISO datetime | datetime_start + service.duration_min |
| I | status | enum | confirmed / cancelled / completed / no_show |
| J | reminder_24_sent | bool | Idempotency flag for the 24-hour reminder |
| K | reminder_1_sent | bool | Idempotency flag for the 1-hour reminder |
| L | created_at | ISO datetime | Server-side timestamp on create |
| M | cancelled_at | ISO datetime, nullable | When the cancellation happened |
| N | calendar_event_id | string, nullable | Google Calendar event ID; needed to delete on cancellation |
| O | visit_count_snapshot | int | Visit count at time of booking; used for VIP check (WOW 2) |

## 7.4 Sheet `blackouts`

Date overrides — holidays, master vacations.

| Col | Name | Type | Notes |
|---|---|---|---|
| A | master_id | string or `*` | `*` = applies to all masters |
| B | date | ISO date | YYYY-MM-DD |
| C | reason | string | Free-text, for owner reference |

## 7.5 Sheet `_errors`

| Col | Name | Type |
|---|---|---|
| A | timestamp | ISO datetime |
| B | handler | string — module.function name |
| C | user_id | int — telegram user who triggered |
| D | error_text | string — exception message + first 500 chars of stack |
| E | payload | JSON string — sanitized FSM data |

---

# 8. FSM Design [filled]

`StatesGroup` for the booking flow lives in `bot/states.py`:

```python
from aiogram.fsm.state import State, StatesGroup

class Booking(StatesGroup):
    choosing_service = State()      # step 1
    choosing_master = State()       # step 2 (skipped if service has single master)
    choosing_date = State()         # step 3 — 14-day calendar
    choosing_slot = State()         # step 4 — time slots for chosen date+master
    entering_contact = State()      # step 5 — name + phone OR voice OR "Share contact"
    confirming = State()            # step 6 — final yes/no
```

State transitions and the data carried in `FSMContext.update_data` are detailed in section 12 below (TBD via Prompt 4).

`MemoryStorage` is the default for dev. For production, **RedisStorage is the recommended upgrade** if user sessions need to survive bot restarts (Context7-verified pattern). For v1 portfolio build, `MemoryStorage` is acceptable — booking flow takes ≤2 minutes for most users; bot restart mid-flow is rare. Trade-off documented; upgrade path is one config change.

`callback_data` schema uses aiogram's `CallbackData` factory from `bot/callbacks.py`:

```python
from aiogram.filters.callback_data import CallbackData

class ServiceCB(CallbackData, prefix="svc"):
    service_id: str

class MasterCB(CallbackData, prefix="mst"):
    master_id: str

class DateCB(CallbackData, prefix="dt"):
    iso_date: str   # YYYY-MM-DD

class SlotCB(CallbackData, prefix="sl"):
    iso_datetime: str   # full datetime with TZ

class BookingActionCB(CallbackData, prefix="ba"):
    booking_id: str
    action: str   # confirm | cancel | reschedule
```

Never build callback_data with raw f-strings on user-controllable values — use the factory.

---

# 9. Integration Rules [filled, Context7-verified]

## 9.1 gspread

Auth via service account file:
```python
gc = gspread.service_account(filename=settings.google_service_account_path)
sh = gc.open_by_key(settings.google_sheet_id)
worksheet = sh.worksheet('bookings')
```

All gspread calls are sync. In async handlers, wrap with `asyncio.to_thread`:
```python
row = await asyncio.to_thread(worksheet.row_values, 5)
await asyncio.to_thread(worksheet.append_row, [id, client_id, ...])
```

**Reading whole tabs as dicts (the v6 way):**
```python
records = await asyncio.to_thread(worksheet.get_all_records, head=1)
# records is list[dict[str, Any]] keyed by the row-1 header names
```
Do NOT use `worksheet.get_records()` — it was removed in gspread v6. For partial-range reads, use `worksheet.get(range)` and `gspread.utils.to_records(header, cells)`.

For multiple writes in one logical operation, use `worksheet.batch_update()` to minimize API calls and dodge rate limits.

The Sheet must be shared with the service-account email as **Editor**. Drive API + Sheets API must be enabled in the Google Cloud project.

## 9.2 Google Calendar

Auth via the same service account:
```python
from googleapiclient.discovery import build
from google.oauth2 import service_account

creds = service_account.Credentials.from_service_account_file(
    settings.google_service_account_path,
    scopes=['https://www.googleapis.com/auth/calendar']
)
service = build('calendar', 'v3', credentials=creds)
```

Each master shares their personal Google Calendar with the service-account email (Make changes to events permission). The service then reads/writes events on each master's `calendar_id`.

Create event:
```python
event_body = {
    'summary': f'{client_name} — {service_name}',
    'start': {'dateTime': iso_start, 'timeZone': 'Europe/Kyiv'},
    'end': {'dateTime': iso_end, 'timeZone': 'Europe/Kyiv'},
    'description': f'Client: {client_phone}\nBooking ID: {booking_id}',
}
event = service.events().insert(calendarId=master_calendar_id, body=event_body).execute()
return event['id']   # save to bookings.calendar_event_id
```

Check availability (WOW 1):
```python
freebusy = service.freebusy().query(body={
    'timeMin': iso_start_of_day,
    'timeMax': iso_end_of_day,
    'items': [{'id': master_calendar_id}]
}).execute()
busy_intervals = freebusy['calendars'][master_calendar_id]['busy']
```

All calls are sync; wrap with `to_thread`. Cache freebusy results for ~60 seconds per master per day to avoid quota hammering during slot picking.

## 9.3 APScheduler 4

Initialization in `bot/services/scheduler.py`:
```python
from sqlalchemy.ext.asyncio import create_async_engine
from apscheduler import AsyncScheduler, ConflictPolicy
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore
from apscheduler.serializers.cbor import CBORSerializer
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger

engine = create_async_engine(f'sqlite+aiosqlite:///{settings.scheduler_db_path}')
data_store = SQLAlchemyDataStore(engine, serializer=CBORSerializer())
scheduler = AsyncScheduler(data_store)
```

Lifecycle integrated with aiogram startup/shutdown. Per Context7 (verified May 2026 against `/agronholm/apscheduler`), the canonical pattern is `async with scheduler:` enclosing the run window, with `start_in_background()` called inside that context. For an aiohttp app whose lifetime is the bot's lifetime, we enter the context once in `on_startup` and exit it in `on_shutdown`:

```python
async def on_startup(bot: Bot):
    await scheduler.__aenter__()           # opens the data_store, starts the event broker
    await scheduler.start_in_background()  # spawns the worker task on the current loop

async def on_shutdown(bot: Bot):
    await scheduler.stop()
    await scheduler.__aexit__(None, None, None)
```

Alternative (cleaner if `main.py` already manages app lifetime explicitly): wrap the entire `web.run_app(...)` call in `async with scheduler:`. Either way, **do not call `start_in_background()` outside of an active `AsyncScheduler` context** — the worker task will not be able to read/write the data store.

Schedule a one-time reminder:
```python
from apscheduler.triggers.date import DateTrigger
from datetime import datetime, timedelta

reminder_at = booking_start - timedelta(hours=24)
await scheduler.add_schedule(
    send_reminder,                      # the function to call
    trigger=DateTrigger(run_time=reminder_at),
    id=f'reminder_24_{booking_id}',
    args=(booking_id, 24),
    conflict_policy=ConflictPolicy.replace,
)
```

For the 1-hour reminder, same pattern with `run_time=booking_start - timedelta(hours=1)`.

For VIP daily check (WOW 2):
```python
from apscheduler.triggers.cron import CronTrigger

await scheduler.add_schedule(
    check_vip_promos,
    trigger=CronTrigger(hour=9, minute=0, timezone='Europe/Kyiv'),
    id='daily_vip_check',
    conflict_policy=ConflictPolicy.replace,
)
```

Cancellation flow: when a booking is cancelled, also remove the scheduled reminders:
```python
await scheduler.remove_schedule(f'reminder_24_{booking_id}')
await scheduler.remove_schedule(f'reminder_1_{booking_id}')
```

## 9.4 Groq Whisper (WOW 3)

`AsyncGroq` client initialization, single instance reused:
```python
from groq import AsyncGroq
client = AsyncGroq(api_key=settings.groq_api_key.get_secret_value())
```

Transcribe voice file:
```python
voice_file = await bot.download(file=message.voice.file_id)
# voice_file is a BytesIO object per aiogram 3.27
transcription = await client.audio.transcriptions.create(
    model='whisper-large-v3-turbo',
    file=('voice.ogg', voice_file.read(), 'audio/ogg'),
    language='ru',
    response_format='text',
)
# response_format='text' returns a string per Context7 (/groq/groq-python)
client_name = str(transcription).strip()
```

Note: Telegram voice messages are OGG/OPUS format. Groq's Whisper endpoint accepts OGG directly; no transcoding needed. The `file` parameter accepts `Path`, raw `bytes`, or a `(filename, contents, mimetype)` tuple — we use the tuple form so we can pass in-memory bytes from `bot.download()` without a temp file.

**Model choice:** `whisper-large-v3-turbo` is the best price-to-performance pick for short name clips (per Groq docs). For maximum accuracy on noisy audio, `whisper-large-v3` is slightly better but slower; we don't need it for name input.

**File size limit:** Telegram voice messages are typically <1 MB for short clips. Groq's hard limit is 25 MB on free tier, 100 MB on dev tier. For name input specifically, enforce 1 MB at our handler layer (anything longer is suspicious and probably not just a name).

**Cost:** $0 on Groq's free tier. The free tier has Audio-Seconds-per-Hour (ASH) and Audio-Seconds-per-Day (ASD) quotas applied at the organization level — easily covers portfolio-demo traffic. **Note:** Groq bills a minimum of 10 s per request even on shorter clips, but at $0 on free tier this is irrelevant.

**Why Groq over OpenAI's whisper-1:** see §2.1 for the full rationale. Short version: free tier without credit card, newer Whisper v3 architecture (better UA/RU), identical API shape.

## 9.5 Slot calculation logic

Pure function in `bot/services/slots.py`. Inputs: master, date, service duration. Outputs: list of available datetimes.

```
For a given (master, date, service):
1. Read master.work_hours and master.work_days. If date's weekday not in work_days → return empty.
2. Read blackouts. If (master_id, date) in blackouts → return empty.
3. Build candidate slots: from work_hours.start to work_hours.end, in steps of service.duration_min.
4. Read all bookings for (master_id, date) where status='confirmed'. Mark candidate slots that overlap with any confirmed booking as occupied.
5. (WOW 1) Read freebusy from Google Calendar for (master.calendar_id, date). Mark candidate slots that overlap with any Calendar busy interval as occupied.
6. Return non-occupied slots, sorted ascending.
```

This function is pure (no I/O) once the bookings and freebusy results are passed in. Sheets and Calendar reads happen in the handler that calls this; the function takes already-loaded data. This keeps it unit-testable.

## 9.6 Phone normalization

Ukrainian phones come in many forms: `+380501234567`, `380501234567`, `0501234567`, `50 123 45 67`, `(050) 123-45-67`. Normalize to `+380XXXXXXXXX`. Regex:

```python
import re

def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r'\D', '', raw)
    if digits.startswith('380') and len(digits) == 12:
        return f'+{digits}'
    if digits.startswith('80') and len(digits) == 11:
        return f'+3{digits}'
    if digits.startswith('0') and len(digits) == 10:
        return f'+38{digits}'
    if len(digits) == 9:
        return f'+380{digits}'
    return None  # caller should re-prompt
```

If `normalize_phone` returns None, the booking handler asks the user to re-enter the phone.

---

# 10. Module-by-module Design [filled, Prompt 1]

Per-file design. Top-level docstring summary, exports, key dependencies, non-obvious notes. All third-party import paths verified against Context7 (`/websites/aiogram_dev_en_v3_27_0`, `/agronholm/apscheduler`, `/groq/groq-python`) during Prompt 1, or carried from `learnings.md` Context7-verified entries (gspread, google-api-python-client, pydantic-settings).

Two files are added beyond the CLAUDE.md Project Structure list: `bot/handlers/reminders.py` and `bot/handlers/vip.py`. Reason: the CLAUDE.md constraint "Never define an APScheduler-scheduled callable inside another function — every scheduled function lives at module scope in `bot/handlers/reminders.py` or `bot/handlers/vip.py`" requires both modules to exist. See OQ-3.

## 10.1 Core

### `bot/main.py`

**Purpose:** Entry point. Initializes `Bot`, `Dispatcher`, the `AsyncScheduler`, includes all routers, switches between polling (dev) and webhook + aiohttp (prod) based on `MODE`, registers lifecycle hooks.

**Exports:** `async def on_startup(bot: Bot)`, `async def on_shutdown(bot: Bot)`, `def main()`.

**Key dependencies:** `aiohttp.web`; from `aiogram`: `Bot`, `Dispatcher`; `aiogram.client.default.DefaultBotProperties`; `aiogram.enums.ParseMode`; `aiogram.fsm.storage.memory.MemoryStorage`; `aiogram.webhook.aiohttp_server.{SimpleRequestHandler, setup_application}`. All routers from `bot.handlers.*`. `bot.services.scheduler.scheduler`. `bot.config.settings`.

**Design notes:**
- `Bot(token=settings.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))` — pattern verified in aiogram 3.27 FSM example.
- Polling branch: `await dp.start_polling(bot)`. Webhook branch: build `web.Application()`, register `SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=settings.webhook_secret.get_secret_value()).register(app, path='/telegram/webhook')`, `setup_application(app, dp, bot=bot)`, `web.run_app(app, host=settings.web_host, port=settings.web_port)`.
- Healthcheck `app.router.add_get('/health', lambda r: web.json_response({'status': 'ok'}))` added in webhook mode only (Railway requirement §3.4).
- Scheduler lifecycle: enter `scheduler.__aenter__()` then `scheduler.start_in_background()` in `on_startup`; in `on_shutdown` call `scheduler.stop()` then `scheduler.__aexit__(None, None, None)`. The `on_startup` hook also calls `bot.set_webhook(url=settings.webhook_base_url+'/telegram/webhook', secret_token=...)` in webhook mode.
- No module-level state — everything constructed inside `main()` so tests can re-enter the entry without import side-effects.

### `bot/config.py`

**Purpose:** Single source of truth for runtime configuration. pydantic-settings v2 `BaseSettings` reads `.env` locally and Railway env vars in prod. Typed access for every variable in §3.1.

**Exports:** `class Settings(BaseSettings)`, module-level singleton `settings = Settings()`.

**Key dependencies:** `pydantic_settings.{BaseSettings, SettingsConfigDict}`, `pydantic.SecretStr`, `pathlib.Path`, `typing.Literal`.

**Design notes:**
- `model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', case_sensitive=False, extra='ignore')`. Switched from `extra='forbid'` (spec §3.1) to `extra='ignore'` during Prompt 2: Windows pip-install pulls a long list of env vars that have no business in `Settings`, and `forbid` would surface them as crash-on-startup. `ignore` is safe — unknown env vars are still inert (env source only reads vars matching field names).
- Secrets typed `SecretStr`: `bot_token`, `webhook_secret`, `groq_api_key`. Access via `.get_secret_value()` only at the API-call site (never logged).
- `admin_telegram_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)` with a `field_validator(mode='before')` that splits the CSV string into `list[int]`. The `NoDecode` annotation (pydantic-settings ≥ 2.7) is mandatory — without it the env source tries `json.loads("1,2,3")` and raises `JSONDecodeError` before the validator can run.
- `mode: Literal['polling', 'webhook']` for compile-time-safe branching in `main.py`.
- Path fields (`google_service_account_path`, `scheduler_db_path`) typed as `pathlib.Path`.
- `BaseSettings` import path is `pydantic_settings`, not `pydantic` — the v1 import is a frequent silent ImportError trap (learnings.md `#pydantic`).
- Module-level singleton `settings = Settings()  # type: ignore[call-arg]` — mypy doesn't know pydantic-settings reads required fields from env, so the no-arg call looks invalid; the ignore is local and well-scoped (only one call site).

### `bot/states.py`

**Purpose:** FSM state declarations. Holds only the booking `StatesGroup`; no logic.

**Exports:** `class Booking(StatesGroup)` with members `choosing_service`, `choosing_master`, `choosing_date`, `choosing_slot`, `entering_contact`, `confirming` (see §8).

**Key dependencies:** `aiogram.fsm.state.{State, StatesGroup}`.

**Design notes:** Cancellation, admin commands, reminders, VIP — all stateless or driven by external triggers (cron, scheduled date). No further StatesGroup planned for v1; if added later, split per group or keep in this file — decision deferred until needed.

### `bot/callbacks.py`

**Purpose:** Schema-typed `CallbackData` factories. Replaces raw f-string callback_data with parsed/validated objects (CLAUDE.md constraint).

**Exports:** `ServiceCB`, `MasterCB`, `DateCB`, `SlotCB`, `BookingActionCB` (fields per §8).

**Key dependencies:** `aiogram.filters.callback_data.CallbackData`.

**Design notes:**
- Field types restricted to `str | int | bool | float | Decimal | Fraction | UUID | Enum | IntEnum` per aiogram 3.27 docs (learnings.md `#aiogram`).
- Prefixes short (2-3 chars) to leave headroom under Telegram's 64-byte callback_data limit.
- Usage: build → `Factory(...).pack()` in keyboards; route → `@router.callback_query(Factory.filter(F.field == ...))` in handlers.

## 10.2 Handlers

### `bot/handlers/start.py`

**Purpose:** `/start` command + main reply-keyboard menu. First touchpoint for every user.

**Exports:** `start_router: Router`, `async def cmd_start(message: Message, state: FSMContext)`.

**Key dependencies:** `aiogram.Router`, `aiogram.filters.CommandStart`, `aiogram.types.Message`, `aiogram.fsm.context.FSMContext`, `bot.keyboards.reply.main_menu_kb`, `bot.config.settings`.

**Design notes:** Defensively calls `await state.clear()` before sending the menu (covers `/start` mid-FSM). `main_menu_kb` receives `is_admin = message.from_user.id in settings.admin_telegram_ids` so the admin row is rendered conditionally.

### `bot/handlers/booking.py`

**Purpose:** End-to-end booking FSM (§8 states). Drives the user from service selection to confirmation. The critical-section slot-check + booking-insert lives here.

**Exports:** `booking_router: Router`, one handler per (state, callback factory) pair: `on_service_pick`, `on_master_pick`, `on_date_pick`, `on_slot_pick`, `on_contact_entered`, `on_voice_received`, `on_confirm`, `on_back`, `on_cancel_flow`.

**Key dependencies:** `aiogram.Router`, `aiogram.F`, `aiogram.fsm.context.FSMContext`, `aiogram.types.{Message, CallbackQuery, Contact}`, `bot.states.Booking`, `bot.callbacks.*`, `bot.keyboards.inline.*`, `bot.keyboards.reply.share_contact_kb`, `bot.services.{sheets, calendar, scheduler, slots, whisper}`, plus `re` for phone normalization (§9.6).

**Design notes:**
- Each state handler: read FSM via `state.get_data()`, validate, transition via `state.set_state(...)`, persist via `state.update_data(...)`.
- Slot re-validation: at `on_slot_pick`, re-fetch available slots and verify chosen is still free. On miss → message "Цей слот вже зайнято, оберіть інший" and re-render keyboard. Same re-validation inside `bot.services.sheets.append_booking` as the final safety net (CLAUDE.md "Never double-book a slot" constraint).
- Confirm step is the only write site. Order: (1) `sheets.append_booking(...)` → on success (2) `calendar.create_event(...)` → store returned event id back to Sheet via `sheets.update_booking_field(booking_id, 'calendar_event_id', ...)` → (3) `scheduler.schedule_reminders(booking_id, datetime_start)` → (4) owner DM → (5) `state.clear()`. Failure at (2)–(4) routes through errors_router; the Sheet row remains with `calendar_event_id` null → manual cleanup recipe documented in §11 during Prompt 4.
- Voice path: `@booking_router.message(Booking.entering_contact, F.voice)`. Download via `await bot.download(message.voice.file_id)` (returns `BinaryIO`); reject if size > 1 MB; pass bytes + `language='ru'` to `whisper.transcribe`; show "Розпізнано: {name}. Підтвердити?" with Yes/Edit inline buttons.

### `bot/handlers/my_bookings.py`

**Purpose:** User-facing "Мої записи" view + per-booking cancel button.

**Exports:** `my_bookings_router: Router`, `async def cmd_my_bookings(...)`, `async def on_cancel_booking(query: CallbackQuery, callback_data: BookingActionCB)`.

**Key dependencies:** `aiogram.Router`, `aiogram.types.{Message, CallbackQuery}`, `bot.callbacks.BookingActionCB`, `bot.services.{sheets, calendar, scheduler}`.

**Design notes:** Filter `bookings` on `client_telegram_id == user.id AND status == 'confirmed' AND datetime_start > now()`. Cancellation order: (1) `sheets.update_booking_field` set status + cancelled_at → (2) `calendar.delete_event(...)` → (3) `scheduler.cancel_reminders(booking_id)` → (4) optional DM to master. Reminders are removed BEFORE the user sees confirmation, eliminating the "cancelled booking gets a reminder" window (idempotency, learnings.md `#idempotency`).

### `bot/handlers/admin.py`

**Purpose:** `/today`, `/week`, `/stats`, `/export`. Gated by `settings.admin_telegram_ids`.

**Exports:** `admin_router: Router`, `cmd_today`, `cmd_week`, `cmd_stats`, `cmd_export`.

**Key dependencies:** `aiogram.Router`, `aiogram.filters.Command`, `aiogram.types.{Message, BufferedInputFile}`, `aiogram.F`, `bot.config.settings`, `bot.services.sheets`. Plus stdlib `csv`, `io`, `datetime`.

**Design notes:**
- Gate as router-level filter: `admin_router.message.filter(F.from_user.id.in_(settings.admin_telegram_ids))`. Non-admin commands fall through silently (no "you're not admin" reply — avoids confirming the command exists to non-admins).
- `/export` builds CSV in-memory (`io.StringIO`) and sends via `BufferedInputFile` — no filesystem write.

### `bot/handlers/errors.py`

**Purpose:** Global error handler. Catches any unhandled exception in the dispatcher chain, logs traceback, writes a sanitized row to Sheet `_errors`, DMs the owner.

**Exports:** `errors_router: Router`, `async def global_error_handler(event: ErrorEvent)`.

**Key dependencies:** `aiogram.Router`, `aiogram.types.ErrorEvent`, `bot.config.settings`, `bot.services.sheets`. Plus stdlib `logging`, `re`, `json`, `traceback`.

**Design notes:**
- Sanitization regex: any dict key matching `/token|key|password|secret|credential/i` is replaced with `[REDACTED]` before JSON-serialization into the `payload` column.
- Owner DM is best-effort — if it fails, log via stdlib `logging` only; do NOT re-raise (would loop the error handler).
- Per CLAUDE.md "Never silently swallow exceptions": only the genuinely-unexpected go here. User-side incomplete input (bad phone, empty Whisper result) is handled in-handler with a friendly message — never reaches this router. Learnings.md `#error-handling`.
- Registered LAST in the dispatcher so unrelated specific handlers get first crack.

### `bot/handlers/reminders.py`

**Purpose:** Module-scope callable for APScheduler 4 reminder jobs. Module scope is **mandatory** — `SQLAlchemyDataStore` + `CBORSerializer` serializes the callable by full dotted path, and a lambda / closure / nested def cannot be re-resolved after a restart (CLAUDE.md constraint).

**Exports:** `async def send_reminder(booking_id: str, hours_before: int) -> None`.

**Key dependencies:** `aiogram.Bot`, `aiogram.client.default.DefaultBotProperties`, `aiogram.enums.ParseMode`, `bot.services.sheets`, `bot.config.settings`. Plus stdlib `logging`.

**Design notes:**
- Importable as `bot.handlers.reminders.send_reminder` — this is the string APScheduler stores and re-imports on fire.
- Idempotency (write-after-success, learnings.md `#idempotency`): re-read the booking; if `status != 'confirmed'` or `reminder_{N}_sent` already set → return early. Send DM → on Telegram 200, flip the `reminder_{N}_sent` flag in Sheets. If DM fails, flag stays unset → next fire retries.
- Bot lifecycle inside callback: see OQ-4. Default approach is a short-lived `Bot` per call, closed via `await bot.session.close()` in `finally`. Confirm during Prompt 6.

### `bot/handlers/vip.py`

**Purpose:** Module-scope callable for the daily VIP cron sweep. Same module-scope rule as reminders.py.

**Exports:** `async def check_vip_promos() -> None`.

**Key dependencies:** same as `reminders.py`.

**Design notes:** Body filled during Prompt 8 (§16). At Prompt 6 this is a stub returning immediately — just enough that `scheduler.register_daily_jobs()` can reference an importable symbol from start.

## 10.3 Keyboards

### `bot/keyboards/inline.py`

**Purpose:** Builders for every inline keyboard. Pure functions: input → `InlineKeyboardMarkup`. No I/O.

**Exports:** `kb_services(services)`, `kb_masters(masters)`, `kb_dates(start: date, days: int = 14)`, `kb_slots(slots: list[datetime])`, `kb_confirm(booking_id: str)`, `kb_booking_actions(booking_id: str)`, `kb_back()`.

**Key dependencies:** `aiogram.types.{InlineKeyboardButton, InlineKeyboardMarkup}`, `bot.callbacks.*`.

**Design notes:** `kb_dates` is 7-col × 2-row (14 days from today). `kb_slots` is 3-col, ascending. Every keyboard ends with a Back button using a reserved `BookingActionCB(booking_id='_', action='back')` so any state can subscribe.

### `bot/keyboards/reply.py`

**Purpose:** Reply keyboards: main menu and "Поділитися контактом".

**Exports:** `main_menu_kb(is_admin: bool = False)`, `share_contact_kb()`.

**Key dependencies:** `aiogram.types.{KeyboardButton, ReplyKeyboardMarkup}`.

**Design notes:** `share_contact_kb` uses `KeyboardButton(text='📱 Поділитися контактом', request_contact=True)` — Telegram returns the phone via `message.contact.phone_number` without retyping (auth gate via Telegram's UI confirmation popup).

## 10.4 Services (external API wrappers)

### `bot/services/sheets.py`

**Purpose:** All gspread access for the five tabs. Every call wrapped with `asyncio.to_thread`. Encode/decode lives here; handlers stay ignorant of column positions.

**Exports:** `async def list_services()`, `async def list_masters()`, `async def list_blackouts(date_)`, `async def list_bookings_for_master_on(master_id, date_)`, `async def list_user_upcoming_bookings(client_id)`, `async def append_booking(row)`, `async def update_booking_field(booking_id, field, value)`, `async def append_error_row(row)`, `async def get_visit_count(client_id)`.

**Key dependencies:** `gspread`, `gspread.utils.to_records`, `asyncio.to_thread`, `bot.config.settings`. Plus stdlib `datetime`, `uuid`.

**Design notes:**
- Module-level lazy singletons: `gc`, plus 5 worksheet handles (`_ws_services`, `_ws_masters`, `_ws_bookings`, `_ws_blackouts`, `_ws_errors`). Open once on first call (~200 ms gspread cold start), reuse forever.
- All reads use `worksheet.get_all_records(head=1)` — `get_records()` was removed in gspread v6 (learnings.md `#gspread`). For partial-range reads use `worksheet.get(range)` + `gspread.utils.to_records(header, cells)`.
- Bulk writes via `worksheet.batch_update()` (§3.7 rate-limit hygiene).
- `append_booking` re-reads `bookings` for the target (master, date) immediately before insert, re-validates the slot, and raises `SlotTakenError` on race — the booking handler catches it and re-renders slots. This is the transactional consistency guarantee (CLAUDE.md constraint). The race window remains a few hundred ms; for v1 portfolio scale this is acceptable; if traffic grows, add an in-memory lock per master keyed on `(master_id, date_)` inside this module.

### `bot/services/calendar.py`

**Purpose:** Google Calendar v3 wrapper — create/delete events, query freebusy (WOW 1). Sync API → `to_thread`-wrapped.

**Exports:** `async def create_event(calendar_id, summary, start, end, description) -> str`, `async def delete_event(calendar_id, event_id) -> None`, `async def get_busy_intervals(calendar_id, start, end) -> list[tuple[datetime, datetime]]`.

**Key dependencies:** `googleapiclient.discovery.build`, `google.oauth2.service_account.Credentials`, `asyncio.to_thread`, `bot.config.settings`. Plus stdlib `datetime`.

**Design notes:**
- Credentials loaded once at module import; scopes `['https://www.googleapis.com/auth/calendar']`.
- `service = build('calendar', 'v3', credentials=creds, cache_discovery=False)` — `cache_discovery=False` silences the file-cache warning on systems without a writable file cache.
- Per-`(calendar_id, day)` 60-second TTL cache for freebusy results (small in-memory dict, mtime-stamped) — meets §15 DoD "removing the manual event makes slots available within 60 seconds".
- All datetimes serialized to RFC 3339 with the `Europe/Kyiv` offset (per `settings.google_calendar_default_tz`).

### `bot/services/scheduler.py`

**Purpose:** APScheduler 4 lifecycle + helpers (`schedule_reminders`, `cancel_reminders`, `register_daily_jobs`).

**Exports:** `scheduler: AsyncScheduler` (module singleton), `async def schedule_reminders(booking_id, datetime_start)`, `async def cancel_reminders(booking_id)`, `async def register_daily_jobs()`.

**Key dependencies:** `from apscheduler import AsyncScheduler, ConflictPolicy`; `apscheduler.datastores.sqlalchemy.SQLAlchemyDataStore`; `apscheduler.serializers.cbor.CBORSerializer`; `apscheduler.triggers.date.DateTrigger`; `apscheduler.triggers.cron.CronTrigger`; `sqlalchemy.ext.asyncio.create_async_engine`; `bot.handlers.reminders.send_reminder`; `bot.handlers.vip.check_vip_promos`; `bot.config.settings`. Plus stdlib `datetime`, `logging`.

**Design notes:**
- Engine: `create_async_engine(f'sqlite+aiosqlite:///{settings.scheduler_db_path}')`. DataStore: `SQLAlchemyDataStore(engine, serializer=CBORSerializer())` (CBOR per Context7 recommendation — wide type support, secure).
- Scheduler instance created at module import; **not** entered. `__aenter__` happens inside `bot.main.on_startup` (needs an active event loop).
- `schedule_reminders` adds two `DateTrigger` jobs with IDs `reminder_24_{booking_id}` and `reminder_1_{booking_id}`, `conflict_policy=ConflictPolicy.replace`. If `datetime_start - 24h` is in the past (same-day booking <24h out), skip that one and log info.
- `cancel_reminders` calls `await scheduler.remove_schedule(...)` for both IDs; swallow missing-schedule errors (already-fired is benign).
- `register_daily_jobs` adds the VIP `CronTrigger(hour=9, minute=0, timezone='Europe/Kyiv')` with id `daily_vip_check`, `conflict_policy=ConflictPolicy.replace`. Idempotent — safe to call on every startup.

### `bot/services/whisper.py`

**Purpose:** Groq Whisper async wrapper. Transcribes voice file bytes to text (WOW 3).

**Exports:** `async def transcribe(file_bytes: bytes, language: str = 'ru', mimetype: str = 'audio/ogg', filename: str = 'voice.ogg') -> str`.

**Key dependencies:** `groq.AsyncGroq`, `bot.config.settings`.

**Design notes:**
- Module singleton: `_client = AsyncGroq(api_key=settings.groq_api_key.get_secret_value())`.
- Call shape verified via Context7 (`/groq/groq-python`):
  ```
  await _client.audio.transcriptions.create(
      model='whisper-large-v3-turbo',
      file=(filename, file_bytes, mimetype),
      language=language,
      response_format='text',
  )
  ```
  Tuple-form `file` accepts in-memory bytes without temp file (`(filename, contents, mimetype)`).
- `response_format='text'` returns plain string — `str(result).strip()` is the final value.
- 1 MB file size cap enforced in the calling handler (§9.4) before calling this function.
- Failures (429, transcription empty, API down) raise to caller; caller falls back to text input and logs to `_errors`.

### `bot/services/slots.py`

**Purpose:** Pure functions for slot availability — fully unit-testable. Inputs: already-loaded master config, date, service, bookings, busy intervals. Output: list of available datetimes.

**Exports:** `def calculate_available_slots(master, date_, service, bookings, busy_intervals) -> list[datetime]`. Internal: `_build_candidates(...)`, `_overlap(...)`.

**Key dependencies:** stdlib `datetime` only. Optionally `zoneinfo.ZoneInfo` for timezone work.

**Design notes:**
- Algorithm per §9.5: weekday/blackout gate → candidates from `work_hours.start` to `work_hours.end` in `service.duration_min` steps → exclude overlap with confirmed bookings and busy intervals.
- Overlap: `slot_end > existing_start AND slot_start < existing_end`.
- No I/O — caller (`booking.py`) loads bookings + freebusy and passes in. Keeps this module pure and trivially testable.
- Past-slot filtering: optional `now` parameter (default `None` = no filter); when set, slots with `start <= now` are excluded. Caller passes `datetime.now(tz)` only when displaying for today.

## 10.5 Tests

### `tests/test_slots.py`

**Purpose:** Pure-function tests for `bot.services.slots`. Covers every branch in §19.

**Exports:** pytest-discovered test functions.

**Key dependencies:** `pytest`, `bot.services.slots`, fixture imports from `conftest.py`. No `pytest-asyncio` (pure sync).

**Design notes:** Targets — outside work hours → empty; blackout day → empty; fully booked → empty; partial booking → correct gaps; Calendar busy → exclude overlapping slots; past-slot filtering when `now` passed.

### `tests/test_states.py`

**Purpose:** FSM transition tests for the booking flow. Drives a mocked `FSMContext` step-by-step.

**Exports:** async test functions.

**Key dependencies:** `pytest`, `pytest-asyncio`, `aiogram.fsm.context.FSMContext`, `aiogram.fsm.storage.memory.MemoryStorage`, `bot.states.Booking`.

**Design notes:** Build `MemoryStorage()` + a `StorageKey(bot_id=0, chat_id=1, user_id=1)` to construct `FSMContext` without a real Bot. One test per transition pair; one test for the happy-path completion. Side effects (sheets/calendar) explicitly NOT mocked here — per §19, those are manual-smoke only.

### `tests/conftest.py`

**Purpose:** Shared pytest fixtures: sample `Service`, `Master`, `Booking` dicts; an in-memory FSM storage; helpers for fake aiogram `Message` / `CallbackQuery`.

**Exports:** pytest fixtures (`sample_master`, `sample_service`, `sample_bookings`, `memory_storage`, `fsm_context`, etc.).

**Key dependencies:** `pytest`, `pytest-asyncio`, `aiogram.fsm.storage.memory.MemoryStorage`. Nothing networked: no `gspread`, no `googleapiclient`, no `groq`.

**Design notes:** Async fixtures via `@pytest_asyncio.fixture`. Tests never touch real env — fixtures provide fully-constructed records, not loaded-from-Sheets.

## 10.6 Final signatures (Prompt 3 reconciliation) [filled]

This subsection is authoritative for the services layer as implemented in Prompt 3. Where it disagrees with §10.4 prose above (which was written in Prompt 1 before some method names were nailed down in the Prompt 3 user prompt), the prose is the design intent; this subsection records what actually shipped.

### Models — `bot/models.py` (NEW)

Domain models live in their own module rather than inline in `sheets.py`. Keeps the storage layer free of validation logic and lets `tests/test_slots.py` import typed models without pulling in gspread.

Pydantic v2 `BaseModel` subclasses:
- `Service` — frozen; `from_row(dict)`.
- `Master` — frozen; `from_row(dict)`, `parse_work_hours() -> (start_h, start_m, end_h, end_m)`.
- `Blackout` — frozen; `from_row(dict)`. `master_id == "*"` means "applies to all masters".
- `Booking` — mutable (status flips during lifecycle); `from_row(dict)` and `to_row() -> list[Any]` in column order matching §7.3.

Bool/CSV helpers (`_parse_bool`, `_csv_strs`, `_csv_ints`) are module-private.

### `bot/services/sheets.py` — `class SheetsService`

Constructor takes no args; reads paths from `bot.config.settings`, opens gspread service-account client, caches the 5 worksheet handles. **NOT** instantiated at module level — tests of pure modules import without needing credentials.

| Method | Signature | Notes |
|---|---|---|
| `load_services` | `() -> list[Service]` | renamed from §10.4 `list_services` (verb consistency) |
| `load_masters` | `() -> list[Master]` | renamed from `list_masters` |
| `load_blackouts_for_date` | `(d: date) -> list[Blackout]` | renamed from `load_blackouts(date_)` |
| `load_bookings_for_master_date` | `(master_id: str, d: date) -> list[Booking]` | renamed from `list_bookings_for_master_on` |
| `load_all_bookings_for_client` | `(client_telegram_id: int) -> list[Booking]` | unchanged |
| `append_booking` | `(booking: Booking) -> None` | takes model, not dict |
| `update_booking_status` | `(booking_id: str, status: str, **fields: Any) -> None` | replaces `update_booking_field`; `**fields` covers `cancelled_at`, `calendar_event_id`, etc. |
| `set_reminder_sent_flag` | `(booking_id: str, kind: int) -> None` | new per Prompt 3 user prompt; `kind ∈ {1, 24}` |
| `log_error` | `(handler: str, user_id: int, error_text: str, payload: dict) -> None` | renamed from `append_error_row`; payload sanitized via redact regex |

`get_visit_count` (mentioned in §10.4) **deferred to Prompt 8 (WOW 2)** — not needed by Prompts 3-7.

`gspread.utils.ValueInputOption.user_entered` enum passed for typed calls — bare `"USER_ENTERED"` string raised `incompatible type` under mypy strict even though both are accepted at runtime (gspread v6 ships PEP 561 type info inline).

### `bot/services/calendar.py` — `class CalendarService`

Constructor takes no args; loads service-account creds once; `build('calendar', 'v3', credentials=..., cache_discovery=False)`.

| Method | Signature | Notes |
|---|---|---|
| `create_event` | `(master_calendar_id: str, booking: Booking) -> str` | takes Booking model; returns event_id; invalidates freebusy cache for that day |
| `delete_event` | `(master_calendar_id: str, event_id: str) -> None` | unchanged |
| `query_busy_intervals` | `(master_calendar_id: str, d: date) -> list[tuple[datetime, datetime]]` | renamed from `get_busy_intervals`; 60s in-memory TTL cache; output tz-converted to `settings.google_calendar_default_tz` and made tz-naive |

`service_account.Credentials.from_service_account_file` is untyped in google-auth's published stubs → carries `# type: ignore[no-untyped-call]` on that one call site.

### `bot/services/scheduler.py` — module-level

| Export | Signature | Notes |
|---|---|---|
| `scheduler` | `AsyncScheduler` | created at import (no I/O until `__aenter__`); lifecycle in `bot/main.py` |
| `schedule_reminder` | `(booking_id: str, fire_at: datetime, kind: int) -> None` | renamed from `schedule_reminders` — caller invokes twice (24h, 1h) instead of one-call-does-both. ID format `reminder_{kind}h_{booking_id}` |
| `cancel_reminders` | `(booking_id: str) -> None` | unchanged; loops both kinds; broad `except Exception` since APScheduler 4 alpha doesn't export a stable lookup-error class (verified via Context7) |
| `schedule_daily_job` | `(job_id: str, callback: Awaitable, hour: int, minute: int) -> None` | renamed from `register_daily_jobs`; takes the callback explicitly so this module doesn't have to hardcode VIP-specific logic |

Callable for reminders is imported as `from bot.handlers.reminders import send_reminder` — module-scope, dotted-path-resolvable per CBOR serializer requirement.

### `bot/services/slots.py` — pure function

`calculate_available_slots(master, d, service, confirmed_bookings, blackouts, calendar_busy_intervals=()) -> list[datetime]`. Renamed two args from §10.4: `bookings → confirmed_bookings` (also filtered by `status == "confirmed"` defensively, so the name reflects post-filter semantics), `busy_intervals → calendar_busy_intervals` (clarifies the source).

### `bot/services/phone.py` (NEW)

`normalize_phone(raw: str) -> str | None` per §9.6. Pure regex. Added as its own module (not in original §10.4) per Prompt 3 user prompt — fits next to `slots.py` since both are pure utilities used by handlers.

### `bot/handlers/reminders.py` & `bot/handlers/vip.py` (STUBS in Prompt 3)

Both created as module-scope stubs returning early with a TODO log. Required to exist so `bot/services/scheduler.py` can import them by dotted path at module load. Bodies filled in Prompt 6 (reminders) and Prompt 8 (vip).

---

# 11. Booking FSM Flow [filled, Prompt 4]

## 11.1 State transitions

Six states (`bot.states.Booking`), driven by callback_query handlers in `bot/handlers/booking.py`. Each forward transition writes to `FSMContext`; back transitions selectively drop keys to allow re-edit without losing earlier choices.

| From state | Trigger | To state | FSM data after |
|---|---|---|---|
| `None` (main menu) | Reply text `"📅 Записатися"` | `choosing_service` | `{}` |
| `choosing_service` | `ServiceCB(service_id=X)` (1 master eligible) | `choosing_date` | `{service_id, master_id}` |
| `choosing_service` | `ServiceCB(service_id=X)` (2+ masters) | `choosing_master` | `{service_id}` |
| `choosing_master` | `MasterCB(master_id=Y)` | `choosing_date` | `{service_id, master_id}` |
| `choosing_date` | `DateCB(iso_date=…)` | `choosing_slot` | `{service_id, master_id, iso_date}` |
| `choosing_slot` | `SlotCB(time_hhmm=N)` | `entering_contact` | `{service_id, master_id, iso_date, iso_datetime}` |
| `entering_contact` (sub-step 1) | text message, `client_name` ∉ data | `entering_contact` | `+ client_name` |
| `entering_contact` (sub-step 2) | text message or `F.contact` | `confirming` (via `_show_confirmation`) | `+ client_phone` |
| `confirming` | `NavCB(action="confirm")` race-passes | `None` (cleared) | atomic write done; FSM cleared |
| `confirming` | `NavCB(action="confirm")` race-fails | `choosing_slot` | `{...} - iso_datetime` (and slot kb re-rendered) |
| any | `NavCB(action="cancel")` or `/cancel` | `None` | `{}` |
| any | `NavCB(action="back")` | previous state | selected keys dropped (table below) |

**Back navigation rules (drop on transition):**

| From | To | Keys dropped |
|---|---|---|
| `choosing_master` | `choosing_service` | (none; service still in data — user just re-picks) |
| `choosing_date` | `choosing_master` or `choosing_service` if single master | (none) |
| `choosing_slot` | `choosing_date` | (none) |
| `entering_contact` | `choosing_slot` | `client_name`, `client_phone`, `iso_datetime` |
| `confirming` | `entering_contact` | `client_phone` (keep `client_name`) |

## 11.2 Per-step messages (RU, OQ-2)

| State | Bot message | Keyboard |
|---|---|---|
| `choosing_service` | `Выберите услугу:` | inline list of `{name} · {duration_min} хв · {price} грн`, 1/row, + Cancel row |
| `choosing_master` | `Выберите мастера:` | inline list of master names, 1/row, + Back + Cancel row |
| `choosing_date` | `Выберите дату:` | 2×7 grid (14 days); unavailable cells use combining-strike + `NavCB(noop_date)`; + Back + Cancel row |
| `choosing_slot` | `Выберите время:` | header `—— До обіду ——` / `—— Після обіду ——` (noop) + 3/row time buttons; empty state → `На цю дату вільних слотів немає` + `← Інша дата` |
| `entering_contact` (sub 1) | `Как вас зовут? Напишите имя текстом.` | reply keyboard removed |
| `entering_contact` (sub 2) | `Оставьте номер телефона. Можно вручную или через кнопку «Поделиться контактом».` | reply keyboard with `📱 Поделиться контактом` (request_contact=True, one_time) |
| `confirming` | `Подтвердите запись: …` (multi-line summary with service/master/date/time/name/phone) | inline 2-button row: ✅ Так, підтвердити / ✖ Скасувати |

Race-condition message at confirm: `Этот слот только что заняли, выберите другой:` + fresh slot keyboard.

Other UX strings: `MSG_CANCELLED`, `MSG_NAME_TOO_SHORT`, `MSG_INVALID_PHONE`, `MSG_DAY_UNAVAILABLE` (toast on tap of striked day), `MSG_GENERIC_ERROR`, `MSG_NO_MASTERS`. All centralized at top of `bot/handlers/booking.py` for one-shot localization later.

## 11.3 Confirmation — atomic write order

Implemented in `bot/handlers/booking.py::on_confirm`. Each step must succeed before the next runs, except where flagged "best-effort":

1. **Race re-check.** `_compute_available_slots(...)` re-queries Sheet + Calendar fresh. If chosen `iso_datetime` ∉ available → set state back to `choosing_slot`, edit message to `MSG_SLOT_TAKEN` + fresh `build_slot_keyboard(...)`. STOP.
2. **Build Booking model.** `booking_id = uuid.uuid4()`, `client_telegram_id = query.from_user.id`, `status="confirmed"`, `created_at=now()`, `reminder_*_sent=False`.
3. **`sheets.append_booking(booking)`** — *blocking*. On failure → `MSG_GENERIC_ERROR`, return to main menu, clear state. STOP.
4. **`calendar.create_event(...)`** — *best effort*. On success: `sheets.update_booking_status(id, "confirmed", calendar_event_id=event_id)`. On failure: log to stdout + `sheets.log_error(...)` row + set `calendar_pending = MSG_CALENDAR_PENDING_NOTE` (appended to owner notif only).
5. **Reminders.** Loop `(24, 1)`: skip if `start - hours <= now()` (same-day < 1h). `schedule_reminder(booking_id, fire_at, kind)` — *best effort*; log on failure.
6. **User success message** — edit confirmation message into `MSG_SUCCESS_TEMPLATE` + `build_user_booking_cancel_keyboard(booking_id)` (single-button inline with `BookingActionCB(booking_id, "cancel")` — the cancellation handler lands in Prompt 5).
7. **Owner notification** — `await asyncio.sleep(0.05)` first (§3.7 rate-limit hygiene), then `bot.send_message(chat_id=settings.owner_telegram_chat_id, …)`. Best effort; log on failure.
8. **`state.clear()`**.

**Source-of-truth invariant:** the `bookings` Sheet row is committed at step 3. After that, **Calendar/reminder failures do not roll back the booking** — the row exists with `calendar_event_id=NULL` (filled by a manual retry / Prompt 7 reconciliation job if added). The user always sees a success message after step 3 succeeds; the owner sees the same plus the pending-calendar note when applicable.

## 11.4 Edge cases handled

- **`/cancel`** in any Booking state → `state.clear()` + main menu reply keyboard. No writes.
- **Tap on striked day** → `query.answer("Этот день недоступен")` toast; state unchanged.
- **Empty slot list for a date** → keyboard shows `На цю дату вільних слотів немає` + `← Інша дата` (NavCB back → state stays in `choosing_date`, message re-edited).
- **Invalid phone text** → `MSG_INVALID_PHONE`; FSM stays in `entering_contact`, sub-step still 2.
- **Name < 2 chars** → `MSG_NAME_TOO_SHORT`; FSM stays in `entering_contact`, sub-step still 1.
- **Share-contact before name** → use `contact.first_name` (or `"Клиент"`) as `client_name`, store phone, jump straight to confirmation.
- **Past slot on same-day booking** → filtered by `_compute_available_slots` (`s > now()` when `picked == today`).
- **Service with no eligible active masters** → `query.answer(MSG_NO_MASTERS, show_alert=True)` and stay in `choosing_service`.

**Definition of Done (Prompt 4):**
- ✅ Full booking takes ≤10 button taps in the happy path (1 reply menu tap + 5 inline picks + 2 text inputs + 1 confirm = 9)
- ✅ Each step has a Back button (returns to previous state, preserves data per table 11.1)
- ✅ Choosing an occupied slot shows an error and re-fetches available slots (`MSG_SLOT_TAKEN`)
- ✅ `/cancel` in any state returns the user to the main menu cleanly
- ✅ Confirmed booking writes one row to Sheets, creates one Calendar event (best-effort), schedules two reminders, sends owner notification

---

# 12. My Bookings + Cancellation [filled, Prompt 5]

`bot/handlers/my_bookings.py`. Routes the `"📋 Мої записи"` reply-button text to `cmd_my_bookings`; cancellation routes via `BookingActionCB(action="cancel")` to `on_cancel_booking`.

## 12.1 View

`cmd_my_bookings`: loads `sheets.load_all_bookings_for_client(user_id)` once, filters `status == "confirmed" AND datetime_start > now()`, sorts ascending. If empty → "У вас пока нет предстоящих записей." Otherwise renders **one message per booking** with the row template:

```
📅 {dd.mm.yyyy} в {HH:MM}
💇 {master_name}
📋 {service_name}
```

Each message has an inline `✖ Отменить` button (`BookingActionCB(booking_id, "cancel")`). Per-message is by design — the cancel handler can `edit_text` the same message in-place after a successful cancellation.

## 12.2 Cancellation invariants

**Order matters.** Side effects on external state run BEFORE the Sheet status flip. If a step before the flip fails, the row stays `confirmed` and the user can retry. Only step 3 is the canonical "officially cancelled" moment.

| Step | Action | On failure |
|---|---|---|
| 1 | `scheduler.cancel_reminders(booking_id)` | Log + continue; reminders re-fire idempotently check `status` before sending (Prompt 6) |
| 2 | `calendar.delete_event(master.calendar_id, calendar_event_id)` | If error mentions `404` / `not found` / `has been deleted` → treat as success; other errors log + continue |
| 3 | `sheets.update_booking_status(id, "cancelled", cancelled_at=now)` | **Hard fail**: reply `MSG_CANCEL_GENERIC_ERROR`, return; booking stays `confirmed` |
| 4 | `bot.send_message(chat_id=master.telegram_id, …)` if `telegram_id` set | Log + continue; non-blocking |
| 5 | `query.message.edit_text("✅ Запись отменена.")` | Log only; cancellation already succeeded |

Defense against forged callback_data: `on_cancel_booking` loads bookings filtered by `user_id == query.from_user.id`; a user can't cancel someone else's booking even if they craft the `BookingActionCB(booking_id=...)` payload.

This sequence is locked by `tests/test_cancellation_order.py::test_cancel_call_order_matches_invariant` — any future refactor that reorders the steps will fail that test.

**Definition of Done:**
- ✅ User sees only their own bookings (filtered by `client_telegram_id`)
- ✅ Cancellation frees the slot for re-booking (slot calculator excludes `status != 'confirmed'`)
- ✅ Cancelled reminders do NOT fire (Prompt 6 idempotency: reminder re-reads booking before sending)
- ✅ Master gets DM notification if `masters.telegram_id` is set (skipped silently otherwise)

---

# 13. Admin Commands [filled, Prompt 5]

`bot/handlers/admin.py`. Four commands gated by `AdminFilter` (custom `aiogram.filters.Filter` subclass). Non-admins typing any of these get a single short reply via a fallback handler. Routing order: admin-filtered handler matches first; non-admin falls through to the fallback.

## 13.1 `AdminFilter`

```python
class AdminFilter(Filter):
    def __init__(self, admin_ids: list[int] | None = None) -> None:
        self.admin_ids = admin_ids if admin_ids is not None else settings.admin_telegram_ids

    async def __call__(self, event: Message) -> bool:
        if event.from_user is None:
            return False
        return event.from_user.id in self.admin_ids
```

Constructor param `admin_ids` allows tests to bypass the `settings` singleton (`tests/test_admin_guard.py`).

## 13.2 Commands

| Cmd | Behavior | Message shape |
|---|---|---|
| `/today` | Group today's `status="confirmed"` bookings by `master_id`; one message per master | `📅 {master_name} — сегодня ({dd.mm.yyyy}):\n• {HH:MM} — {client_name} ({service_name}) 📞 {client_phone}\n…` |
| `/week` | Same shape, range = `[today, today + 7d)` | `📅 {master_name} — ближайшие 7 дней:\n• {dd.mm HH:MM} — {client_name} ({service_name})\n…` |
| `/stats` | Counts per `status` for current calendar month | One message with bullet counts of confirmed / cancelled / completed / no_show + total |
| `/export` | CSV of current month's bookings, sent as `BufferedInputFile`; follow-up inline `📦 Все записи` button re-runs with `all_time=True` | Document with caption `Экспорт за MM.YYYY (N записей)` |

Empty-state messages: "На сегодня (…) записей нет." / "На ближайшие 7 дней записей нет." Non-admin: "У вас нет прав на эту команду."

## 13.3 Implementation notes

- Single dispatcher handler `on_admin_command` switches on `cmd = message.text.split()[0].lstrip("/").lower()` to call `_do_today/_do_week/_do_stats/_do_export`. This keeps `Command(commands=_ADMIN_COMMANDS)` + `AdminFilter()` decoration in one place.
- `SheetsService.load_all_bookings()` (new in Prompt 5) reads all rows once; admin commands filter in Python rather than making N reads per master/day. Acceptable for SMB scale (≤ few thousand rows over a year).
- CSV uses `csv.writer` over `io.StringIO`; bytes prefixed with UTF-8 BOM (`﻿`) so Excel auto-detects encoding for Ukrainian/Russian names. Sent via `BufferedInputFile(file=bytes_, filename=f"bookings-{YYYY-MM}.csv")`.
- "Все записи" follow-up uses `NavCB(action="export_all")` (reuses existing factory) — handler re-checks admin status defensively (in case the user is no longer admin between message and tap).
- All 12 booking fields are exported (id, client_*, service_id, master_id, datetime_start/end, status, calendar_event_id, created_at, cancelled_at) — covers audit + import-into-Excel use cases.

**Definition of Done:**
- ✅ `/today /week /stats /export` work for users in `ADMIN_TELEGRAM_IDS`
- ✅ Non-admins get the short rejection reply and nothing else (no leak about which commands exist beyond the names already in `BotFather`-set command list)
- ✅ `/export` attachment opens cleanly in Excel/LibreOffice (BOM-prefixed UTF-8)
- ✅ `/export` "Все записи" button re-runs scope without a date filter

---

# 14. Reminders [filled, Prompt 6]

APScheduler 4 fires `bot.handlers.reminders.send_reminder(booking_id, hours_offset)` from a persisted `DateTrigger`. Two jobs per booking: 24h and 1h before `datetime_start`. Both are scheduled at confirmation time (`bot.handlers.booking.on_confirm` → `bot.services.scheduler.schedule_reminder`), removed at cancellation (`my_bookings.on_cancel_booking` → `cancel_reminders` as step 1 of the cancellation sequence).

## 14.1 send_reminder body (5-step order)

Inside `bot/handlers/reminders.py:send_reminder`:

1. **Load booking fresh.** `sheets.load_booking_by_id(booking_id)`. If `None` → log + return (booking row deleted; nothing to do).
2. **Status guard.** If `booking.status != "confirmed"` → log + return. Handles the race "cancelled between schedule and fire" even though cancellation also calls `cancel_reminders` first.
3. **Already-sent guard.** If `reminder_24_sent` (or `reminder_1_sent`, depending on `hours_offset`) is truthy → log + return. This is the belt-and-suspenders against duplicate fires after restart.
4. **Send DM.** `bot.send_message(chat_id=booking.client_telegram_id, text=...)`. Raises on Telegram error.
5. **Flip flag.** `sheets.set_reminder_sent_flag(booking_id, hours_offset)` — only after step 4 returns without exception.

If step 4 raises, the exception propagates to APScheduler's job worker (logs in stdout). Step 5 is skipped, so the flag stays unset. The next scheduled fire (or a manual re-schedule) will retry. If the flag flips but a duplicate fire happens (rare — e.g. two replicas running), the in-handler guard at step 3 skips.

## 14.2 Bot injection — module-level globals (not args)

APScheduler 4's `add_schedule(..., args=tuple)` requires CBOR-serializable args. `Bot` is not (open HTTP session, asyncio loop refs). Pattern:

```python
# bot/handlers/reminders.py
_bot: Bot | None = None
_sheets: SheetsService | None = None

def set_runtime(bot: Bot, sheets: SheetsService) -> None:
    global _bot, _sheets
    _bot = bot
    _sheets = sheets
```

`bot/main.py:on_startup` calls `set_runtime(bot, sheets)` **BEFORE** `scheduler.start_in_background()` — so an immediately-due reminder (within seconds of startup) can find both refs set. Defense-in-depth: `send_reminder` also returns early with an error log if either ref is None.

Alternative considered: pass refs via aiogram `dp["sheets"]` workflow_data into a closure factory. Rejected because the scheduled callable is `send_reminder` itself (the symbol APScheduler serializes), not a closure — and a closure isn't module-level-importable.

## 14.3 Reminder text templates (RU per OQ-2)

```
MSG_REMINDER_24H_TEMPLATE = (
    "⏰ Напоминание: завтра в {time_str} у вас запись на «{service_name}» "
    "к мастеру {master_name}."
)
MSG_REMINDER_1H_TEMPLATE = (
    "🔔 Через час — запись «{service_name}» у мастера {master_name}."
)
```

`time_str = booking.datetime_start.strftime("%H:%M")`. Both templates centralized at top of `reminders.py` for one-shot localization (OQ-2 revisit).

## 14.4 Scheduling at booking confirmation

`bot.services.scheduler.schedule_reminder(booking_id, fire_at, kind)`:

```python
await scheduler.add_schedule(
    send_reminder,                                    # module-level ref
    DateTrigger(run_time=fire_at),
    id=f"reminder_{kind}h_{booking_id}",
    args=(booking_id, kind),                          # CBOR-safe (str + int)
    conflict_policy=ConflictPolicy.replace,           # idempotent re-schedule
)
```

The booking handler loops `(24, 1)` and skips any kind whose `fire_at <= now()` (e.g. same-day booking with <1h lead time → no 1h reminder).

## 14.5 Cancellation removes schedules

`bot.services.scheduler.cancel_reminders(booking_id)` loops both kinds, calls `scheduler.remove_schedule(sid)` for each, swallows the lookup error if the schedule was already fired/never created. Cancellation handler (Prompt 5) invokes this as **step 1** of the 5-step sequence — schedules are gone BEFORE the Sheet `status` flips to `cancelled`, so the race window where a reminder fires for a freshly-cancelled booking is essentially zero. The status-guard at step 2 of `send_reminder` catches any residual race.

## 14.6 APScheduler 4 alpha known quirks

- `ScheduleLookupError` is **not** publicly exported from `apscheduler` in 4.0.0a6 — Context7 lookup confirms only `AsyncScheduler`, `ConflictPolicy`, triggers, datastores, serializers are exported. `cancel_reminders` catches broad `Exception` with a debug log; cancelling a non-existent schedule is benign.
- `DateTrigger(run_time=...)` accepts naive datetimes (Context7 example uses `datetime.now() + timedelta(...)`). Project convention is naive local-time (Europe/Kyiv assumed), no `tz=` arg.
- Same-process startup ordering: `__aenter__` must be inside an active event loop. Achieved by entering the context inside aiogram's `_on_startup` hook, which runs after `asyncio.run(_run_polling())` has created the loop.
- **CBORSerializer × cbor2 6.x is broken in 4.0.0a6.** Switched to `PickleSerializer` (Prompt 6 manual test discovery). Symptom: scheduler worker crashes on first poll with `AttributeError: 'bool' object has no attribute 'tag'` deep inside `cbor.deserialize`, raising `apscheduler.DeserializationError` and aborting the whole worker task. Root cause: `cbor2` 6.x changed the `_tag_hook` signature; alpha was tested against `cbor2` 5.x. Pickle is safe here (data store is self-written, no untrusted input) and provides identical guarantees for module-level callables. **Switching serializers makes existing rows unreadable** — wipe `data/scheduler.db*` after the swap. `cbor2` stays as a transitive dependency.

**Definition of Done:**
- ✅ Reminders fire at correct times (DateTrigger persists across restart via SQLite)
- ✅ Bot restart does NOT cause double-firing (idempotency: status guard + already-sent guard + write-after-success)
- ✅ Cancelled bookings do NOT receive reminders (cancel_reminders runs BEFORE the Sheet status flip; reminder's status-guard catches any race remnant)
- ✅ Failed sends propagate to APScheduler (logged in stdout), flag stays unset for retry
- ✅ Restart drill: schedule a reminder 5 min out, Ctrl+C the bot, restart, confirm fire still happens at the original time. Module-level `send_reminder` import path is stable across restarts.

---

# 15. WOW 1 — Google Calendar Two-Way Sync [filled, Prompt 7]

## 15.1 Behavior

Two directions:
1. **Bot → Calendar** (already): on every confirmed booking, `bot.services.calendar.CalendarService.create_event` writes a Calendar event on the master's calendar. Stored `event_id` lives in the Sheet row's `calendar_event_id` column for later deletion.
2. **Calendar → Bot** (this WOW): on every slot picker render, `CalendarService.query_busy_intervals(master.calendar_id, picked_date)` reads the master's freebusy for that day. Returned intervals are folded into `slots.calculate_available_slots`' busy set alongside confirmed bookings. A master who manually blocks time in their own Google Calendar (e.g. "Lunch 12:00–13:00") sees those slots automatically disappear from the bot's offering.

The Prompt 3 implementation wired the read end-to-end (`slots.py` accepts `calendar_busy_intervals`, `booking._compute_available_slots` calls `query_busy_intervals`). Prompt 7 fixed an edge-case time-window bug (UTC bounds → Kyiv bounds), added the explicit `timeZone` request field, and added regression tests for the cache.

## 15.2 freebusy request body

```python
day_start_local = datetime.combine(d, datetime.min.time()).replace(tzinfo=ZoneInfo("Europe/Kyiv"))
day_end_local = day_start_local + timedelta(days=1)
body = {
    "timeMin": day_start_local.isoformat(),   # RFC3339 with +03:00 offset (summer)
    "timeMax": day_end_local.isoformat(),
    "items": [{"id": master_calendar_id}],
    "timeZone": settings.google_calendar_default_tz,
}
```

**Day bounds in Europe/Kyiv, not UTC.** Earlier (Prompt 3) the bounds used `tzinfo=timezone.utc`, which for `d = 2026-05-20` sent `2026-05-20T00:00:00+00:00` = 03:00 Kyiv — events between 00:00–03:00 Kyiv on the requested date were missed (and 00:00–03:00 Kyiv of the next date were wrongly included). Not visible in v1 work hours (10:00–19:00) but a real correctness gap.

`timeZone` is optional per Google docs (controls response interpretation) — included for clarity and as defense against future API behavior changes.

## 15.3 freebusy response

Google Calendar API returns response intervals as **RFC3339 in UTC** (`Z` suffix) regardless of the `timeZone` request field. Parser:

```python
busy_raw = resp["calendars"][master_calendar_id].get("busy", [])
for b in busy_raw:
    start_utc = datetime.fromisoformat(str(b["start"]).replace("Z", "+00:00"))
    end_utc = datetime.fromisoformat(str(b["end"]).replace("Z", "+00:00"))
    start_local = start_utc.astimezone(self._local_tz).replace(tzinfo=None)
    end_local = end_utc.astimezone(self._local_tz).replace(tzinfo=None)
    intervals.append((start_local, end_local))
```

`fromisoformat` accepts `+00:00` directly in Python 3.11+. The `Z → +00:00` swap is defensive against future variants.

**Output is naive Europe/Kyiv** — matches the rest of the codebase. `Booking.datetime_start`, slot candidates, blackouts — all naive throughout. Switching to tz-aware in calendar alone would cascade `TypeError` through `slots.calculate_available_slots`' overlap check (`slot_end > existing_start AND slot_start < existing_end`).

## 15.4 Cache

- Key: `(master_calendar_id, iso_date)` tuple
- Value: `(monotonic_set_at, intervals)`
- TTL: 60 seconds via `time.monotonic()` (immune to wall-clock changes)
- Invalidation: explicit on `create_event` for that `(calendar_id, day)` — the just-written event would otherwise still appear absent in the next 60 sec window. No explicit invalidation on `delete_event` because the 60-sec staleness is acceptable per DoD.

## 15.5 Verification

Unit (`tests/test_calendar_cache.py`):
- `test_cache_hit_within_ttl` — call twice at 100s, 159s → API hit only once
- `test_cache_miss_after_ttl` — call at 100s, 161s → API hit twice
- `test_cache_keys_distinct_per_calendar_and_date` — different cal_id OR different date doesn't share cache
- `test_response_parsing_normalizes_to_naive_kyiv` — `12:00Z` becomes naive 15:00 Kyiv (DST)

Manual:
1. In Google Calendar under the master account, add event tomorrow 12:00–13:00 titled "Lunch"
2. In bot: `/start` → 📅 Записатися → pick service → pick master → tomorrow's date
3. Slot picker must NOT show 12:00 or 12:30 (assuming `service.duration_min = 30`)
4. Delete the event in Google Calendar
5. Wait 65 seconds (TTL 60s + buffer)
6. ← Назад to date → re-enter same date → 12:00 and 12:30 reappear

**Definition of Done:**
- ✅ Manual event "Lunch" 12:00-13:00 excludes 12:00 and 12:30 slots in bot
- ✅ Removing the manual event makes slots available again within 60 seconds (cache TTL)
- ✅ Cache TTL behavior locked by `tests/test_calendar_cache.py`
- ✅ Day-bounds bug fixed: events 00:00-03:00 Kyiv on the queried date are no longer missed

---

# 16. WOW 2 — Automatic VIP Status [filled, Prompt 8]

## 16.1 Behavior

A daily cron at **09:00 Europe/Kyiv** scans bookings for clients who satisfy ALL of:
1. Have **≥5 bookings with `status='completed'`** (lifetime visits, across all masters/services).
2. Have **at least one `status='confirmed'` booking in the next 7 days** — limits the audience to active clients who'll actually use the promo.
3. Have **not previously received the VIP DM** (idempotency, see §16.2).

Each qualifying client receives one DM containing the static promo code `SUPERVIP`. Their telegram ID is then appended to the `_vip_sent` sheet — once present, they're skipped on every future run.

Wiring: `bot/handlers/vip.py::check_vip_promos`, scheduled in `bot.main:_on_startup` via `await scheduler.schedule_daily_job("daily_vip_check", check_vip_promos, 9, 0)`. Re-registration on every restart is idempotent (`ConflictPolicy.replace` baked into `schedule_daily_job`).

## 16.2 Idempotency — OQ-0 resolution

**Decision:** new sheet **`_vip_sent`**, columns A=`client_telegram_id` (int), B=`sent_at` (ISO datetime).

**Why this over a `bookings.vip_message_sent_at` column:**
- VIP status is a property of the **client**, not of any single booking row. A `bookings.vip_sent_at` column would either need a "which row owns the flag?" rule (brittle), or duplication of the same timestamp across every row of that client (data-integrity headache on backfill / corrections).
- A small dedicated tab keeps the `bookings` row schema stable and makes "who got a VIP DM" a single `get_all_records` of a tiny sheet (one row per lifetime VIP client).
- Trade-off accepted: one extra Sheets read per daily run. At 1 call/day this is invisible relative to per-booking traffic.

`bot.services.sheets.SheetsService` exposes:
- `load_vip_sent() -> set[int]` — returns telegram IDs already notified.
- `append_vip_sent(client_telegram_id: int) -> None` — writes a new row with `now().isoformat()` as `sent_at`.

## 16.3 Candidate selection — pure helper

`bot.handlers.vip.select_vip_candidates(completed, upcoming, already_sent) -> list[int]`:
- `completed`: list of `Booking` with `status='completed'`
- `upcoming`: list of `Booking` with `status='confirmed'`, `datetime_start.date()` in `[today, today+7d]`
- `already_sent`: set of telegram IDs from `_vip_sent`

Algorithm:
1. `visits = Counter(b.client_telegram_id for b in completed)`
2. `upcoming_ids = {b.client_telegram_id for b in upcoming}`
3. Return `sorted({tid for tid in upcoming_ids if visits[tid] >= 5 and tid not in already_sent})`

Pure (no I/O). Tested in `tests/test_vip.py`.

## 16.4 VIP message template

```
⭐ {name}, вы наш VIP-клиент после 5 визитов! Промокод SUPERVIP на ваш следующий визит.
```

Russian only for v1 (consistent with reminder templates per OQ-2). `{name}` is `Booking.client_name` of the most recent completed visit for that client.

## 16.5 Rate-limit hygiene

`await asyncio.sleep(0.05)` between sends — keeps under Telegram's 30 msg/sec global cap when many candidates qualify on the same day.

Per-send failures (Telegram 403 / blocked-by-user / network blip) log and continue to the next candidate; the failed candidate is NOT marked sent → next daily run retries.

## 16.6 Manual setup (operator)

Create the `_vip_sent` worksheet in the same Google Sheet:
- Tab name: `_vip_sent` (leading underscore = "system" tab convention, like `_errors`).
- Row 1 headers: `client_telegram_id`, `sent_at`.
- Share permission: already covered by the service-account share on the spreadsheet.

If the tab doesn't exist when the bot starts, `SheetsService.__init__` raises `WorksheetNotFound` at boot — loud failure, immediately fixable.

## 16.7 Temporary admin command (Prompt 8 only)

`/run_vip` calls `check_vip_promos()` directly from the admin handler — for manual smoke testing the candidate-selection + DM flow without waiting for 09:00. **Removed in Prompt 10** (final cleanup).

## 16.8 Definition of Done

- A client with 5 `completed` bookings + 1 upcoming `confirmed` booking + NOT in `_vip_sent` receives exactly one DM with promo code `SUPERVIP`, and their ID is appended to `_vip_sent`.
- A client with the same shape but already in `_vip_sent` receives no DM (log line includes `"skipped K already-sent"`).
- A client with 4 `completed` + upcoming → no DM.
- A client with 5 `completed` + no upcoming in next 7 days → no DM.
- Daily cron runs at 09:00 Europe/Kyiv; re-registration on every restart is idempotent (`ConflictPolicy.replace`).
- `/run_vip` works for admins and is a no-op for non-admins.

---

# 17. WOW 3 — Voice Name Input [TBD via Prompt 9]

To be filled during Prompt 9. At the `entering_contact` state, the bot shows three options:
- Standard text input (typing name + phone)
- "📱 Поделиться контактом" reply keyboard button (Telegram's native contact share)
- "🎤 Голосом" inline button (this WOW)

Voice flow:
- User taps "🎤 Голосом"
- Bot prompts: "Запишите голосовое сообщение со своим именем"
- User records voice message
- Handler catches `message.voice`, downloads via `bot.download()`, transcribes via `services.whisper.transcribe(file_bytes, language='ru')` using Groq's `whisper-large-v3-turbo`
- Result inserted as `client_name`; bot shows: "Распознано: {name}. Подтвердить?" with Yes/Edit buttons

**Definition of Done:**
- Voice name input works in Russian and Ukrainian (Whisper Large v3 has materially better UA accuracy than v2 — verify with at least 3 Ukrainian name samples)
- Transcription latency <3 seconds for a 5-second clip (Groq is typically <1 s end-to-end thanks to their inference hardware)
- File size limit enforced (reject >1 MB at the handler before any API call)
- Failure (Groq API down, rate limit hit, transcription empty) falls back to text input gracefully — handler stays in `entering_contact` state, logs to `_errors`, shows friendly message
- Free-tier verification: zero charges accrued during the build and on the live demo Railway deploy (Groq dashboard "Usage" page confirms $0)

---

# 18. Quality Gates [filled]

Three checkpoints. None skipped.

## 18.1 Per-prompt gate

After every prompt that creates or modifies code:
- `ruff check .` passes (no warnings)
- `mypy bot/` passes (strict mode)
- `pytest -v` passes for any test files touching the changed surface
- Manual smoke test in polling mode: bot starts cleanly, the changed feature exercises without exception
- `project_specs.md` updated with any decisions made during the build
- Operator's manual user-facing test (described at the end of each prompt in `prompts.md`) passes

## 18.2 Pipeline gate (after Prompt 10)

End-to-end on production Railway deploy:
- Full booking flow completes in ≤10 taps
- Booking appears in Sheets within 2 seconds
- Calendar event created on master's calendar within 5 seconds
- Reminders fire at correct times (test with a near-future booking, e.g. 5 minutes ahead, lowering the offset temporarily)
- Cancellation removes Calendar event, scheduled reminders, frees the slot
- Owner receives Telegram notification within 2 seconds of booking
- Admin commands work for users in `ADMIN_TELEGRAM_IDS`, blocked for others
- Voice name input works (WOW 3)
- Manually-blocked Calendar time is excluded from slots (WOW 1)
- VIP check runs daily without error
- Error handler routes intentional errors to `_errors` Sheet and owner DM

## 18.3 Production readiness gate

Before linking the project from anywhere public:
- All env vars from 3.1 set in Railway
- Persistent volume mounted at `/app/data`, contains `scheduler.db` after first deploy
- `credentials.json` mounted at `/app/secrets/credentials.json` (Railway secret file)
- `WEBHOOK_SECRET` set, verified by sending a fake POST without the header → 401 expected
- `/health` returns 200 OK
- Graceful shutdown verified: redeploy mid-conversation, FSM data is lost (acceptable for v1 with MemoryStorage), but scheduled reminders survive
- One reminder restore drill: schedule a reminder, redeploy, verify it still fires
- README has the case-narrative section

---

# 19. Testing Strategy [filled]

**Pure function tests (highest value):**
- `slots.calculate_available_slots()` — covers all branches: outside work hours, blackout day, day fully booked, day partially booked with Calendar conflicts, normal day
- `phone.normalize_phone()` — covers all input formats listed in 9.6
- `services.sheets.parse_booking_row()` — round-trip test against a fixture row

**FSM state transition tests:**
- Mock `FSMContext`, drive through booking flow step by step, assert correct state at each step and correct data persisted

**No tests for:**
- Direct gspread/Calendar API calls (mocking is high effort, low signal — manual smoke covers it)
- Whisper transcription (depends on Groq; manual smoke)
- aiogram dispatcher internals

Tests live in `tests/` next to `bot/`. `pytest-asyncio` for async test functions. Fixtures in `conftest.py`.

---

# 20. Architecture Doc + README Structure [TBD via Prompt 10]

To be filled during Prompt 10. README covers: value prop, GIF demo, stack, architecture summary (Mermaid), three WOW features with screenshots, Definition of Done, competencies block. `docs/architecture.md` (optional, can fold into README) covers the deeper architectural decisions for a reviewer.

---

# 21. Open Questions / TBD

This section is maintained jointly. Claude Code adds questions encountered during planning or build that need operator input. The operator resolves them.

**OQ-0 [resolved in Prompt 8].** ~~Where does the VIP-already-notified guard live?~~ → **Decision:** new sheet `_vip_sent` (option b). Rationale: client-scoped state belongs in a client-scoped tab, not duplicated across booking rows. Full reasoning in §16.2.

**OQ-1 (seed).** Calendar event title format. The owner's calendar shows: `{client_name} — {service_name}`? Or include phone? The latter exposes PII in any view the master shares. Recommendation: client_name + service_name only; phone in `description`. Confirm with operator during Prompt 4.

**OQ-2 (seed).** Reminder DM language — Russian or Ukrainian, or detect from the client's Telegram `language_code`? For v1 keep Russian (most reliable Whisper language for this region), revisit if testers report friction. Document in §14.

**OQ-3 (Prompt 1).** `bot/handlers/reminders.py` and `bot/handlers/vip.py` are required by the CLAUDE.md constraint "Never define an APScheduler-scheduled callable inside another function — every scheduled function lives at module scope in `bot/handlers/reminders.py` or `bot/handlers/vip.py`", but those two files are not in CLAUDE.md → Project Structure. §10 documents them as added. **Recommendation:** update CLAUDE.md Project Structure to list both files explicitly so the structure section matches the constraint. Operator decides whether to amend CLAUDE.md (preferred) or leave the discrepancy and rely on the constraint as the source of truth.

**OQ-4 (Prompt 1, decide in Prompt 6).** Bot instance lifecycle inside APScheduler-fired callbacks (`send_reminder`, `check_vip_promos`). Two options: **(a)** short-lived `Bot` constructed inside each call and closed via `await bot.session.close()` in `finally` — safer against cross-event-loop bugs, ~10 ms overhead per fire; **(b)** shared module-level `Bot` constructed once and reused — faster, but requires the scheduler worker to share the dispatcher's event loop (true with APScheduler 4 `async with scheduler: ... start_in_background()` on the main loop). **Default:** option (a) in Prompt 6 implementation. **Trigger to revisit:** if reminder latency or per-fire cost becomes observable on Railway.

**OQ-5 (Prompt 1, decide in Prompt 2).** Exact `groq` SDK version pin for `pyproject.toml`. Context7 query against `/groq/groq-python` (May 2026) confirmed the API shape (`AsyncGroq`, `audio.transcriptions.create` with `whisper-large-v3-turbo`, file as tuple/Path/bytes) but did not surface a precise current version. `learnings.md` baseline = `0.13.0`. **Action before Prompt 2 pin:** run `Context7:resolve-library-id({libraryName: 'groq'})` and read the `Versions` block; pick latest stable that still exposes `audio.transcriptions.create` with the verified signature.

---

# 22. Build Retrospective [TBD via Prompt 10]

Filled at the end of Prompt 10 as one-paragraph reflections on:

- Biggest gotcha hit during the build
- Biggest time-saver discovered
- Library API surprises (APScheduler 4 is the obvious candidate)
- What to do differently on the next project

This section seeds the next project's planning.
