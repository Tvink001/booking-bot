# Learnings — Project 2 (Booking Bot)

Running log of project-specific patterns, gotchas, and reusable solutions.

**Format:** dated entry, 3–10 lines, tagged by domain. Tags I use: `#aiogram`, `#apscheduler`, `#gspread`, `#calendar`, `#whisper`, `#pydantic`, `#async`, `#context7`, `#mcp`, `#railway`, `#windows`, `#debugging`, `#idempotency`, `#portfolio-polish`. Grep-friendly so future projects can pull patterns by tag (`grep "#async" learnings.md`).

**Maintenance:** operator-side discipline. Claude Code reads this file via Rule 1 on every prompt but does not write to it directly — it surfaces suggested entries at the end of each prompt report; operator decides what to encode.

---

## 2026-05 — Cross-project seeds carried over from Project 1 (Lead Automation)

These entries were promoted from P1 because the underlying lesson generalizes beyond n8n. Each one cost real debug time in P1; encoding here prevents paying that cost again in P2.

### Brief-specified library/model versions are timestamps, not specs `#context7`

In P1 the brief said "Claude-3.5 Haiku"; the build shipped on `claude-haiku-4-5` after Context7 confirmed the current alias. Same pattern hits here: the brief mentions APScheduler with v3 syntax, aiogram with no version, "Whisper" without a model string. Treat every version-shaped string in the brief as a starting hint, not a requirement. **Run Context7 before pinning anything in `pyproject.toml`.**

### `.mcp.json` on Windows: inline secrets, gitignore the file, install MCP servers globally `#mcp` `#windows`

Three sub-lessons from P1 that all apply here:
1. **No `${VAR}` substitution on Windows PowerShell** — Claude Code's `.mcp.json` `${VAR}` syntax resolves from shell env, not `.env`. PowerShell does not auto-export `.env`. Solution: paste real values into `.mcp.json` directly, add `.mcp.json` to `.gitignore`, document the template in `project_specs.md`.
2. **`npx` causes 30 s MCP startup timeout** — `npx` downloads fresh on each start, exceeding the MCP startup window. Install the MCP package globally first (`npm install -g <pkg>`) and point `.mcp.json` at the installed binary's `.cmd` shim.
3. **TLS cert chain interception breaks both npm and Node-based MCP runtime** — Symptom: `UNABLE_TO_VERIFY_LEAF_SIGNATURE` on install, silent "no response" once running. Two fixes: `npm config set strict-ssl false` while installing (restore after), plus `"NODE_TLS_REJECT_UNAUTHORIZED": "0"` in the MCP server's `env` block in `.mcp.json`.

For P2 the only MCP server is Context7, so the surface area is smaller — but the install + secrets discipline is identical.

### Idempotent "fire-once-and-only-once" pattern: side effect, then guard-write `#idempotency` `#apscheduler`

The pattern that worked in P1 (`reminder_sent_at` guard column on each lead row) translates straight to P2's APScheduler reminders and VIP daily check:
1. Read candidate records.
2. Filter to those WITHOUT the guard set.
3. Fire the side effect (DM, Calendar write, whatever).
4. **Only after the side effect succeeds**, write the guard column with a timestamp.

If step 3 fails, step 4 doesn't run → next tick retries. If it succeeds, guard set → next tick skips. No external state store needed; transient failures (network blip, rate limit) self-heal. Applies to: `bookings.reminder_24_sent`, `bookings.reminder_1_sent`, the VIP "already-notified" column, and any future "send digest / nudge user" job.

### Don't throw on partial / incomplete user-side data — the error chain will spam you `#error-handling`

In P1, the Sheets Trigger's `anyUpdate` event fired during cell-by-cell typing and produced rows with most columns empty. Throwing from the validator wired the error workflow (WF03) into a sender-of-noise — the operator's inbox filled with "missing field" emails for every keystroke. Fix in P1: silently `return []` for incomplete items. **Same discipline applies in P2:** if Whisper returns gibberish, if the user sends a non-voice file when voice was requested, if a Sheets read returns a half-edited blackout row — log + show a friendly user message, but do NOT raise to the global error handler. The error handler is for genuinely unexpected bugs, not for users mid-flow.

### "One-item-from-many" bug pattern: pick a batching strategy explicitly `#async`

In P1, a chain that used `$('Trigger').first()` silently dropped N-1 items when the trigger fired with N events at once. Python analogue: any handler that processes a list but writes/reads using `data[0]` will silently drop trailing items if the upstream ever delivers a batch. Two safe patterns for this project:
- **Iterate explicitly** — `for booking in bookings: ...` with awaitable side effects sequenced via `await asyncio.gather()` or a plain `for` loop if rate limits matter.
- **Single-item-per-call by design** — APScheduler fires one job per scheduled time; aiogram dispatches one Update per call. Don't try to fan out inside a handler unless the requirement specifically demands it.

The hidden hazard: aiogram's `bot.send_message(...)` inside a loop without `await asyncio.sleep(0.05)` hits the 30-msg/sec global Telegram limit and silently 429s a subset.

---

## 2026-05 — Seed entries (Context7-verified during pre-build research)

### aiogram 3.27 is the current stable as of May 2026 `#aiogram` `#context7`

Refreshed via Context7 lookup against `/websites/aiogram_dev_en_v3_27_0` (9054 snippets, Source Reputation High). Previous note said "3.26 stable, 3.27 latest" — that was a half-step behind. Pin `aiogram==3.27.0` in `pyproject.toml`. The v3.x dev branch (`/websites/aiogram_dev_en_dev-3_x`) is the actively maintained docs source; older 3.25 / 3.23 examples in tutorials may use earlier filter syntax.

### APScheduler 4 — major API rewrite vs ТЗ `#apscheduler`

The brief still references v3 syntax (`SQLAlchemyJobStore`, `scheduler.add_job`). APScheduler 4 has a fundamentally different API, **verified via Context7 against `/agronholm/apscheduler`**:
- `AsyncIOScheduler` → `AsyncScheduler` (canonical import: `from apscheduler import AsyncScheduler`)
- `SQLAlchemyJobStore` → `SQLAlchemyDataStore` (import: `from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore`)
- `scheduler.add_job(func, ...)` → `await scheduler.add_schedule(func, trigger, id=..., conflict_policy=ConflictPolicy.replace)`
- Sync-by-default → async-by-default (`async with AsyncScheduler(data_store) as scheduler:` then `await scheduler.start_in_background()`)
- Serializer arg: `SQLAlchemyDataStore(engine, serializer=CBORSerializer())` — CBOR is the recommended choice (wide type support, secure)
- Triggers: `from apscheduler.triggers.date import DateTrigger`, `from apscheduler.triggers.cron import CronTrigger`, `from apscheduler.triggers.interval import IntervalTrigger`

Implication: any tutorial older than ~2 years uses v3 and will not work in this codebase. Claude Code must Context7-verify before writing scheduler code each time.

### Async wrapping pattern for sync I/O libraries `#async` `#gspread` `#calendar`

gspread and google-api-python-client are sync. In async handlers, never call them directly — wrap with `asyncio.to_thread`:
```python
row = await asyncio.to_thread(worksheet.row_values, 5)
event = await asyncio.to_thread(
    lambda: service.events().insert(calendarId=cal_id, body=body).execute()
)
```
Direct sync call inside an async handler stalls the entire bot's event loop for every user. This is the single most common production bug in async Python bots.

### gspread v6 dropped `get_records()` — use `get_all_records()` instead `#gspread` `#context7`

Context7 surfaced this from the gspread `README.md` migration note: `Worksheet.get_records()` is removed in gspread v6. Use `Worksheet.get_all_records(head=1)` for full sheets; for partial-range record extraction, fetch the cells via `worksheet.get(...)` and use `gspread.utils.to_records(header, cells)`. Any tutorial or AI-generated code that calls `get_records()` is targeting pre-v6 API and will raise `AttributeError`.

### gspread_asyncio is not the answer `#gspread` `#context7`

Considered using `gspread_asyncio` (the async wrapper) instead of sync gspread + `to_thread`. Context7 reveals: 7 code snippets, benchmark score 45 (compare gspread itself: 239 snippets, score 82). Low maintenance signal. Sync gspread + `to_thread` is the idiomatic and well-supported choice for May 2026.

### pydantic-settings v2 import path `#pydantic`

In pydantic v2, settings split into a separate package:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict  # not pydantic
from pydantic import SecretStr  # still in pydantic
```
Common mistake: importing `BaseSettings` from `pydantic` (v1 path) — silent ImportError at startup. `model_config = SettingsConfigDict(env_file='.env', case_sensitive=False, extra='forbid')` is the canonical config shape. `env_prefix='APP_'` and `env_nested_delimiter='__'` are available if you want nested sub-models.

### aiogram 3.x webhook setup pattern `#aiogram`

Verified against Context7 (`/websites/aiogram_dev_en_v3_27_0`, official `webhook.html` page). Production webhook uses aiohttp under the hood. Canonical shape:
```python
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

app = web.Application()
SimpleRequestHandler(
    dispatcher=dp,
    bot=bot,
    secret_token=WEBHOOK_SECRET,
).register(app, path=WEBHOOK_PATH)
setup_application(app, dp, bot=bot)
```
Plus a hook registered via `dp.startup.register(on_startup)` that calls `bot.set_webhook(url=BASE_WEBHOOK_URL + WEBHOOK_PATH, secret_token=WEBHOOK_SECRET)`. The `secret_token` is Telegram's mechanism to authenticate that the POST really came from them, via the `X-Telegram-Bot-Api-Secret-Token` header.

### CallbackData factory: pack vs filter `#aiogram`

Verified pattern from aiogram 3.27 docs:
```python
class MyCallback(CallbackData, prefix="my"):
    foo: str
    bar: int

# In keyboard:
button = InlineKeyboardButton(text="...", callback_data=MyCallback(foo="x", bar=1).pack())

# In router:
@router.callback_query(MyCallback.filter(F.foo == "demo"))
async def handler(query: CallbackQuery, callback_data: MyCallback):
    print(callback_data.bar)
```
Supported field types: `str, int, bool, float, Decimal, Fraction, UUID, Enum (string), IntEnum (integer)`. **Never build callback_data with raw f-strings** on user-controllable values — use the factory.

### Calendar auth simplification vs ТЗ `#calendar`

Brief specifies "service account + OAuth for masters." Full OAuth per master is ~200 LOC of consent screen, redirect, token refresh handling. Replaced with: each master shares their personal calendar with the service-account email (Make changes to events permission). Same auth shape as Sheets, no OAuth flow. Trade-off: one-time manual share by each master. Verified API shape via Context7 (`/googleapis/google-api-python-client`): `service_account.Credentials.from_service_account_file(path, scopes=['https://www.googleapis.com/auth/calendar'])` → `build('calendar', 'v3', credentials=creds)`.

### Groq Whisper instead of OpenAI — better model, $0, drop-in replacement `#whisper` `#groq` `#context7`

For Project 2's WOW 3 (voice name input) we use **Groq's** Whisper endpoint, not OpenAI's. Three reasons surfaced by Context7 in May 2026:
1. **Cost.** OpenAI's `whisper-1` is $0.006/min and OpenAI's "Free" rate-limit tier is officially "Not supported" for API access (the $5 onboarding credit is a marketing perk, not a documented policy — may or may not exist for a given account, expires in ~3 months, requires CC). Groq has a permanent free tier with audio-seconds-per-day quotas that easily cover a portfolio demo bot.
2. **Better model.** OpenAI's `whisper-1` is Whisper v2 architecture. Groq runs `whisper-large-v3` and `whisper-large-v3-turbo` — the v3 generation with materially better multilingual accuracy (Ukrainian/Russian benefit notably).
3. **API compatibility.** Groq exposes the OpenAI-compatible audio endpoint. The Python SDK signature is identical in shape:
   ```python
   from groq import AsyncGroq
   client = AsyncGroq(api_key=settings.groq_api_key.get_secret_value())
   transcription = await client.audio.transcriptions.create(
       model="whisper-large-v3-turbo",
       file=("voice.ogg", voice_bytes, "audio/ogg"),
       language="ru",
       response_format="text",
   )
   ```
   File can be a `Path`, raw `bytes`, or a `(filename, contents, mimetype)` tuple. Telegram voice messages are OGG/OPUS — Groq accepts OGG natively, no transcoding needed.

**Groq free-tier constraints:** file ≤25 MB (free) / ≤100 MB (dev), audio downsampled to 16 kHz mono server-side, **billed for a minimum of 10 s** even on shorter clips (but billing is $0 on free tier, so irrelevant for portfolio). Rate limits measured as RPM, RPD, Tokens-Per-Day, **Audio-Seconds-per-Hour** (ASH), Audio-Seconds-per-Day (ASD); applied at organization level.

For name-input use case enforce **1 MB** file cap at our handler layer regardless of the 25 MB API limit (anything bigger than a name is suspicious).

Library version: `groq==0.13.0` baseline; re-verify via Context7 (`/groq/groq-python`) before pinning in `pyproject.toml`.

### Library version pin policy `#context7`

Brief-specified versions are timestamps, not specs. Re-verify current stable via Context7 before pinning in `pyproject.toml`. Verified May 2026 baseline:
- aiogram: **3.27** stable (3.x dev branch active; v4.x alpha — do not use)
- APScheduler: **4.0+** (significant new API vs 3.x)
- gspread: **6.x** (`get_records()` removed; use `get_all_records()`)
- groq: **0.13.x** (`AsyncGroq`, OpenAI-compatible `audio.transcriptions.create`) — **replaces OpenAI for WOW 3, free tier, Whisper-Large-v3-turbo model**
- pydantic / pydantic-settings: **v2** (BaseSettings moved to `pydantic_settings`)
- google-api-python-client: **2.x** (`from googleapiclient.discovery import build`)
- google-auth: **2.x** (`from google.oauth2 import service_account`)

Note: `openai` SDK is intentionally NOT in this project. We considered it for Whisper, but Groq gives the same API surface with a permanently free tier and a newer Whisper model — see the Whisper entry above for the full rationale.

---

_(Entries below this line are added as the build progresses. Use `/ce-compound` (operator-side) to encode new entries after each completed prompt.)_
