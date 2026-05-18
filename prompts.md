# Project 2 — Booking Bot: Prompt Sequence

Sequential prompts for Claude Code. Each prompt is one atomic build unit: Claude Code reads context, writes Python code, runs tests, and reports back. Each prompt depends on the previous — never run them out of order. If a prompt fails its test step, fix in place and only then move on.

---

## How this file works

**Claude Code's side (inside each prompt):**
- Reads `CLAUDE.md`, `project_specs.md`, `learnings.md`
- Verifies third-party library APIs via Context7 before writing code (per CLAUDE.md Rule 3)
- Writes Python modules via `create_file` / `str_replace`
- Runs `ruff`, `mypy`, `pytest`, manual smoke tests
- Updates `project_specs.md` with decisions made during the build
- Reports back: files changed, what was added to the spec, manual test instructions for the operator

**Operator's side (between prompts):**
- Plan, review, and encode learnings using your own tooling — Claude Code is unaware of this layer
- Manage external setup (Google Cloud Console, BotFather, Railway) when Claude Code asks
- Run the manual user-facing tests described at the end of each prompt
- Approve `project_specs.md` updates before moving to the next prompt

**Prerequisite:** Step 0 external setup is complete and `CLAUDE.md` + `project_specs.md` + `learnings.md` exist in project root.

---

## Step 0 — External setup (manual, in browser)

Browser tabs only. Do these first. Each step's output (URL, ID, token) lands either in your Railway env vars or in a local `.env` file — never in committed code.

1. **Google Cloud Console** → new project → APIs & Services → Enable APIs and Services → enable **Google Sheets API**, **Google Drive API**, **Google Calendar API** (three separate enables). Then IAM & Admin → Service Accounts → Create Service Account → Keys → Add Key → Create new key → JSON → save the downloaded file as `credentials.json` outside this repo (e.g. `C:\Users\Admin\secrets\booking-bot\credentials.json`). Copy the service-account email — looks like `bot-sheets@<project-id>.iam.gserviceaccount.com`.

2. **Google Sheet** named `booking-bot-prod` → File → Share → add the service-account email as **Editor** → create five tabs renamed: `services`, `masters`, `bookings`, `blackouts`, `_errors`. Column schemas in `project_specs.md` §7. Seed at least: 2 rows in `services` (one short like `haircut-30` 30 min, one long like `dance-60` 60 min), 1 row in `masters` with your own Google Calendar ID as `calendar_id`. Save the Sheet ID from the URL (the long string between `/d/` and `/edit`).

3. **Each master's Google Calendar** → google.com/calendar → settings (gear icon) → Settings for my calendars → pick the calendar → Share with specific people or groups → Add people → paste service-account email → permission **"Make changes to events"** → Send. Note the master's calendar ID — usually their Gmail address; for non-primary calendars it's under "Integrate calendar".

4. **Telegram BotFather** → `/newbot` → bot username → save token to a note. Repeat once more for a separate **dev** bot — same token format, separate identity. Keep prod bot for Railway, dev bot for local polling-mode tests.

5. **Telegram private group "Booking Notifications"** → create group → add the prod bot → promote bot to admin → message `@getmyidbot` in the group → save the negative `chat_id` it prints as `OWNER_TELEGRAM_CHAT_ID`. Also message `@getmyidbot` privately to grab your personal Telegram user ID (positive int) for `ADMIN_TELEGRAM_IDS`.

6. **Groq Console** → `https://console.groq.com` → Sign Up via Google / GitHub / email (no credit card required for free tier) → API Keys → Create API Key → name it "booking-bot-prod" → save the `gsk_...` value. Groq's free tier permanently includes the Whisper endpoint with Audio-Seconds-per-Day quotas that easily cover demo traffic. (Optional now; required by Prompt 9 for WOW 3.)

   *Note:* We use Groq, not OpenAI, for Whisper. Rationale in `project_specs.md` §2.1: OpenAI's free tier is "Not supported" for API per their own docs (the $5 onboarding credit is a marketing perk, not a documented policy, and requires CC); Groq runs the newer Whisper-Large-v3 model on a permanently free tier. Same API shape, drop-in replacement.

7. **Railway** → New Project → Deploy from GitHub repo → link the booking-bot repo. Then in the project:
   - **Add Persistent Volume** → mount path `/app/data` → size 1 GB (smallest tier).
   - **Upload credentials.json as Secret File** → mount path `/app/secrets/credentials.json`.
   - **Set all env vars** listed in §3.1 of `project_specs.md`. Minimum required for Prompt 2's first deploy:
     ```
     BOT_TOKEN=<prod bot token from step 4>
     WEBHOOK_SECRET=<output of step 8>
     OWNER_TELEGRAM_CHAT_ID=<negative int from step 5>
     ADMIN_TELEGRAM_IDS=<your positive int from step 5>
     GOOGLE_SERVICE_ACCOUNT_PATH=/app/secrets/credentials.json
     GOOGLE_SHEET_ID=<long ID from step 2>
     GOOGLE_CALENDAR_DEFAULT_TZ=Europe/Kyiv
     GROQ_API_KEY=<gsk_... from step 6 — placeholder OK if WOW 3 not yet built>
     MODE=webhook
     WEB_HOST=0.0.0.0
     WEB_PORT=8080
     SCHEDULER_DB_PATH=/app/data/scheduler.db
     SCHEDULER_TIMEZONE=Europe/Kyiv
     LOG_LEVEL=INFO
     ```
     `WEBHOOK_BASE_URL` is set once Railway assigns a public domain — fill it in after the first deploy.
   - **Do not deploy yet** — the first deploy happens at the end of Prompt 2 after the Dockerfile exists.

8. **Generate webhook secret** in your local shell (PowerShell):
   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   Save the output as `WEBHOOK_SECRET` in Railway env vars.

9. **Create `.mcp.json`** in your project root with the Context7 MCP server configured. **Template** (committed to repo as reference):
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
   **Windows operator-side override (from P1 learnings — not committed; add `.mcp.json` to `.gitignore`):**
   ```json
   {
     "mcpServers": {
       "context7": {
         "command": "C:\\Users\\Admin\\AppData\\Roaming\\npm\\context7-mcp.cmd",
         "args": [],
         "env": { "NODE_TLS_REJECT_UNAUTHORIZED": "0" }
       }
     }
   }
   ```
   Install the MCP server globally first so the cmd shim above exists:
   ```powershell
   npm config set strict-ssl false
   npm install -g @upstash/context7-mcp
   npm config set strict-ssl true
   ```

10. **Smoke-test Context7 connectivity** before Prompt 1. In Claude Code, ask:
    > "Run Context7:resolve-library-id for `aiogram`."
    
    Expect a result block listing `/aiogram/aiogram` and a few mirror docs. If you get "No response" or a timeout, the MCP server isn't reachable — fix per the Windows override in step 9 before running Prompt 1.

Keep all credentials in a temporary password manager until they're in Railway or in your local `.env`. **None of these go into committed code.**

---

## Prompt 1 — Planning: complete `project_specs.md`

```
Read CLAUDE.md, project_specs.md, learnings.md (create empty learnings.md
if missing).

I've already filled the parts of project_specs.md that are clear before
development starts and Context7-verifiable: product summary, tech stack
with version rationale, deviations from brief (notably APScheduler 4 vs 3),
production configuration, MCP setup, development workflow, architecture
overview, data model for all 5 Sheet tabs, FSM design at the StatesGroup
level, integration rules for every external API, quality gates, testing
strategy. Read what's there before adding to it — do not duplicate.

Complete the remaining sections of project_specs.md marked [TBD via
Prompt 1]:

- Section 10 (Module-by-module design) — for every file listed in
  CLAUDE.md → Project Structure, write: top-level docstring summary,
  list of exported names, key dependencies (imports), any non-obvious
  design notes. One short paragraph per file.

Context7 lookups required before completing Section 10 (use these exact
library IDs, no resolve step needed):
- /websites/aiogram_dev_en_v3_27_0  → confirm: Bot, Dispatcher, Router;
  aiogram.fsm.state (State, StatesGroup); aiogram.fsm.context (FSMContext);
  aiogram.fsm.storage.memory (MemoryStorage); aiogram.filters.callback_data
  (CallbackData); aiogram.webhook.aiohttp_server (SimpleRequestHandler,
  setup_application); aiogram.client.default (DefaultBotProperties);
  aiogram.enums (ParseMode); aiogram.types (InlineKeyboardButton,
  InlineKeyboardMarkup, CallbackQuery, Message)
- /agronholm/apscheduler → confirm: from apscheduler import AsyncScheduler,
  ConflictPolicy; apscheduler.datastores.sqlalchemy SQLAlchemyDataStore;
  apscheduler.serializers.cbor CBORSerializer; apscheduler.triggers.date
  DateTrigger; apscheduler.triggers.cron CronTrigger
- /pydantic/pydantic-settings → confirm: BaseSettings, SettingsConfigDict,
  env_file behavior; verify SecretStr import is still from pydantic
- /groq/groq-python → confirm: AsyncGroq client, audio.transcriptions.create
  signature (model, file as Path|bytes|tuple, language, response_format),
  current Whisper model identifiers (whisper-large-v3-turbo and
  whisper-large-v3 expected). Verify groq SDK version for pyproject pin.
- /burnash/gspread → confirm: service_account(filename=...), worksheet
  .append_row, get_all_records(head=1). Flag if get_records is referenced
  anywhere (must be removed — v6 dropped it).
- /googleapis/google-api-python-client → confirm: googleapiclient.discovery
  build; from google.oauth2 import service_account; events().insert,
  events().delete, freebusy().query body shape

For any import path you cannot confirm via Context7, list it in Open
Questions (Section 21) with the exact symbol and where you needed it.

Do NOT write code yet. This prompt only writes spec; Prompt 2 starts
scaffolding.

Report at end:
- bullet list of every file you touched in project_specs.md (section
  number + 1-line summary of what you added)
- the Open Questions you added or expanded
- the Context7 query IDs you actually ran (no IDs invented)

Wait for my approval before moving on.
```

**After this prompt:** I review the diff, answer Open Questions, approve.

---

## Prompt 2 — Scaffolding + minimal bot skeleton

```
Read CLAUDE.md, project_specs.md, learnings.md.

Create the file structure per CLAUDE.md → Project Structure. Use
create_file for each.

Files to create (exact paths, all relative to project root):

- pyproject.toml — start from this skeleton, then re-verify each
  dependency's latest stable via Context7 (use the library IDs listed
  in learnings.md "Library version pin policy") and bump if newer
  stable exists. Pin exact versions, no ranges.
  ```toml
  [project]
  name = "booking-bot"
  version = "0.1.0"
  requires-python = ">=3.11"
  dependencies = [
    "aiogram==3.27.0",
    "apscheduler==4.0.0",
    "sqlalchemy==2.0.36",
    "aiosqlite==0.20.0",
    "gspread==6.2.1",
    "google-api-python-client==2.151.0",
    "google-auth==2.36.0",
    "groq==0.13.0",
    "pydantic==2.9.2",
    "pydantic-settings==2.6.1",
    "aiohttp==3.10.10",
  ]

  [project.optional-dependencies]
  dev = [
    "ruff==0.7.0",
    "mypy==1.13.0",
    "pytest==8.3.3",
    "pytest-asyncio==0.24.0",
  ]

  [tool.ruff]
  line-length = 100
  [tool.ruff.lint]
  select = ["E", "F", "I", "W"]

  [tool.mypy]
  strict = true
  python_version = "3.11"

  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  testpaths = ["tests"]
  ```
  If Context7 says a newer stable exists for any library, bump and
  note the bump in your report. Do NOT downgrade to an older version
  to match a tutorial.

- Dockerfile — multi-stage Python 3.11-slim base, copy pyproject.toml
  first for layer caching, then `pip install -e .` (project root), then
  copy bot/, expose 8080, CMD `python -m bot.main`. Create directories
  `/app/data` and `/app/secrets` so the Railway volume mount and secret
  file mount have target paths to land into.

- railway.toml — healthcheck path `/health`, healthcheck timeout 30s,
  restart policy on-failure with maxRetries 3.

- .env.example — every variable from project_specs.md §3.1, with inline
  comments distinguishing "local-only", "production-only", and
  "both". Use `# ` for the comments. Include the WEBHOOK_BASE_URL=
  placeholder.

- .gitignore — include: `.env`, `credentials.json`, `data/`, `*.log`,
  `__pycache__/`, `.ruff_cache/`, `.mypy_cache/`, `.pytest_cache/`,
  `.mcp.json` (per P1 Windows learning), `*.egg-info/`, `dist/`,
  `build/`.

- .mcp.json — verify it exists from Step 0; leave as-is. Do NOT commit
  the Windows variant — only the template.

Then write the minimal bot skeleton that boots cleanly:
- bot/__init__.py — empty
- bot/config.py — pydantic-settings BaseSettings class with every
  env var from §3.1. Use `SecretStr` from pydantic for BOT_TOKEN,
  WEBHOOK_SECRET, GROQ_API_KEY. Validate via Context7
  (/pydantic/pydantic-settings) that `model_config = SettingsConfigDict
  (env_file='.env', case_sensitive=False, extra='forbid')` is current.
- bot/main.py — entry point. Two code paths gated by `settings.mode`:
  - "polling": `await dp.start_polling(bot)` after `bot.delete_webhook
    (drop_pending_updates=True)`.
  - "webhook": aiohttp web.Application with route POST
    /telegram/webhook (via SimpleRequestHandler with secret_token=
    settings.webhook_secret.get_secret_value()) and GET /health
    (returns `web.json_response({"status": "ok"})`). Register
    dp.startup.register(on_startup) where on_startup calls
    bot.set_webhook(url=BASE+PATH, secret_token=..., drop_pending_
    updates=True). Use setup_application(app, dp, bot=bot).
  Verify the exact webhook shape via Context7
  (/websites/aiogram_dev_en_v3_27_0). Do NOT trust memory; this is
  where AI most often writes outdated code.
- bot/handlers/__init__.py — empty
- bot/handlers/start.py — single Router (`start_router = Router()`)
  with @start_router.message(CommandStart()) handler that replies
  "Бот працює. Команди з'являться у наступних промптах." (placeholder).
  In main.py: `dp.include_router(start_router)`.
- tests/__init__.py — empty
- tests/conftest.py — minimal pytest fixtures, includes setting
  monkeypatch for env vars so test_config can construct Settings.
- tests/test_config.py — one test that asserts Settings() loads
  without error given a test .env.

Test pipeline (run all of these; report exit codes):
```powershell
ruff check .
ruff format . --check
mypy bot/
pytest -v
```
Then boot test (Claude Code: print exact PowerShell command for me
to run; do not try to run a long-lived process yourself):
```powershell
$env:MODE="polling"; $env:BOT_TOKEN="<dev bot token>"; python -m bot.main
```
Expectation: bot connects, no Python tracebacks, /start to the dev
bot returns the placeholder text.

Update project_specs.md with any decisions made (final pinned versions
if you bumped, Settings class structure, exact /health response shape).

Report at end:
- files created with paths
- Context7 queries you ran (library IDs)
- any version bumps from the skeleton above and why
- exit codes for ruff/mypy/pytest
- exact boot-test command for me to run

Manual test I'll run before approving move to Prompt 3:
- `pip install -e .[dev]`
- Copy .env.example to .env, fill in BOT_TOKEN with dev bot token
- `$env:MODE="polling"; python -m bot.main` → no errors, bot connects
- Send /start to the dev bot in Telegram → receive the placeholder text
- Then push to GitHub → trigger first Railway deploy → wait for
  Railway to show "Active" → curl https://<app>.up.railway.app/health
  → expect {"status": "ok"} with 200
```

---

## Prompt 3 — Services layer (sheets, calendar, scheduler — no business logic yet)

```
Read CLAUDE.md, project_specs.md, learnings.md.

Build the services/ layer per project_specs.md §9 (Integration Rules).
These are thin async wrappers over sync external APIs; no booking
business logic yet — that comes in Prompt 4.

Context7 lookups required before writing code (use these exact library
IDs):
- /burnash/gspread → service_account, worksheet.append_row,
  worksheet.batch_update, worksheet.get_all_records (NOT get_records
  — removed in v6, see learnings.md), worksheet.update
- /googleapis/google-api-python-client → discovery.build for
  calendar v3, service.events().insert(), service.events().delete(),
  service.freebusy().query() — body shape and response shape
- /agronholm/apscheduler → AsyncScheduler lifecycle (async with +
  start_in_background pattern from project_specs.md §9.3),
  SQLAlchemyDataStore with sqlite+aiosqlite engine, CBORSerializer,
  DateTrigger, CronTrigger, add_schedule with ConflictPolicy.replace,
  remove_schedule
- /websites/aiogram_dev_en_v3_27_0 → bot.download(file=...) return
  type (BytesIO vs file path) — important for Prompt 9

Modules to create:
- bot/services/__init__.py — empty
- bot/services/sheets.py — class SheetsService wrapping gspread.
  Methods (all async, all wrapping sync calls via asyncio.to_thread):
    load_services() -> list[Service]
    load_masters() -> list[Master]
    load_blackouts_for_date(d: date) -> list[Blackout]
    load_bookings_for_master_date(master_id: str, d: date) -> list[Booking]
    load_all_bookings_for_client(client_telegram_id: int) -> list[Booking]
    append_booking(booking: Booking) -> None
    update_booking_status(booking_id: str, status: str, **fields) -> None
    set_reminder_sent_flag(booking_id: str, kind: int) -> None  # kind ∈ {24, 1}
    log_error(handler: str, user_id: int, error_text: str, payload: dict) -> None
  Constructor receives the gspread client + settings; opens worksheets
  once in __init__. Use Pydantic models (dataclasses also fine) for
  Service/Master/Booking/Blackout — define them in this module or in
  a new bot/models.py if you prefer.

- bot/services/calendar.py — class CalendarService. Methods:
    create_event(master_calendar_id: str, booking: Booking) -> str
      (returns event_id)
    delete_event(master_calendar_id: str, event_id: str) -> None
    query_busy_intervals(master_calendar_id: str, d: date)
      -> list[tuple[datetime, datetime]]
      with 60-second per-(master_id, date) in-memory TTL cache;
      cache key = (master_calendar_id, d.isoformat()), TTL stored
      as monotonic timestamps.

- bot/services/scheduler.py — wraps APScheduler 4 AsyncScheduler.
  Module-level: create engine, data_store, scheduler (NOT started yet
  — main.py controls lifecycle). Exported functions:
    schedule_reminder(booking_id: str, fire_at: datetime, kind: int)
      → calls scheduler.add_schedule(send_reminder, DateTrigger(
        run_time=fire_at), id=f"reminder_{kind}h_{booking_id}",
        args=(booking_id, kind), conflict_policy=ConflictPolicy.replace)
    cancel_reminders(booking_id: str)
      → calls scheduler.remove_schedule for both ids; ignores
        ScheduleLookupError (already-cancelled is OK).
    schedule_daily_job(job_id: str, callback, hour: int, minute: int)
      → CronTrigger(hour=hour, minute=minute,
        timezone=settings.scheduler_timezone) with replace policy.
  send_reminder itself is defined in bot/handlers/reminders.py
  (Prompt 6) but the IMPORT PATH must be the symbol — never a lambda
  or closure (see CLAUDE.md constraints and project_specs.md §14).

- bot/services/slots.py — PURE FUNCTION (no I/O), unit-testable:
    calculate_available_slots(
      master: Master,
      d: date,
      service: Service,
      confirmed_bookings: list[Booking],
      blackouts: list[Blackout],
      calendar_busy_intervals: list[tuple[datetime, datetime]] = (),
    ) -> list[datetime]
  Algorithm per spec §9.5.

- bot/services/phone.py — normalize_phone(raw: str) -> str | None per
  spec §9.6. Pure function.

Wire scheduler lifecycle into bot/main.py:
- on_startup hook: `await scheduler.__aenter__()` then
  `await scheduler.start_in_background()` (per Context7-verified
  pattern in spec §9.3)
- on_shutdown hook: `await scheduler.stop()` then
  `await scheduler.__aexit__(None, None, None)`

Tests to write in tests/:
- test_slots.py — at least 6 cases per spec §19 (outside work hours,
  blackout day, fully booked, partially booked, calendar conflict,
  normal day with mix). Use pytest parametrize.
- test_phone.py — every input format from spec §9.6 (`+380501234567`,
  `380501234567`, `0501234567`, `50 123 45 67`, `(050) 123-45-67`)
  plus three rejection cases (empty, letters, too-short).

Test pipeline (run all; report exit codes):
```powershell
ruff check .
ruff format . --check
mypy bot/
pytest -v
```
Boot test (give me the exact command):
```powershell
$env:MODE="polling"; python -m bot.main
```
Expected: bot starts cleanly, no exceptions, scheduler logs a "started"
line, data/scheduler.db file appears on first run.

Update project_specs.md §10 with the final class signatures you
settled on for each service. If you renamed any method from the
list above, document the change and why.

Report at end:
- files created
- Context7 queries you ran (library IDs)
- pytest test count + pass/fail
- any departures from the spec (with one-line justification each)

Manual test I'll run:
- Run the bot locally with the polling command above
- Send /start → main menu still works (no regression)
- Confirm `data/scheduler.db` file appears on first run
- Confirm no exceptions in the logs
```

---

## Prompt 4 — Booking FSM (the main feature)

```
Read CLAUDE.md, project_specs.md, learnings.md.

Build the full booking FSM in bot/handlers/booking.py per project_specs.md
§8 (StatesGroup) and §11 (Booking FSM Flow — fill §11 as you build).

Context7 lookups required (use these exact library IDs):
- /websites/aiogram_dev_en_v3_27_0 — confirm:
  · State, StatesGroup syntax (fsm.state)
  · @router.message vs @router.callback_query decorator signatures
  · StateFilter usage in router filters
  · FSMContext methods: set_state, get_data, update_data, clear
  · CallbackData factory: pack() and filter() patterns
  · InlineKeyboardBuilder for building keyboards
  · CallbackQuery.answer(text=..., show_alert=...) for toast UX
- /mastergroosha/aiogram-3-guide — optional, Russian-language reference
  if you need a second opinion on a tricky FSM pattern

Modules to create / modify:
- bot/states.py — Booking StatesGroup per §8 (six states:
  choosing_service, choosing_master, choosing_date, choosing_slot,
  entering_contact, confirming)
- bot/callbacks.py — ServiceCB, MasterCB, DateCB, SlotCB,
  BookingActionCB per §8. Also a NavCB(action: str) for "back" /
  "cancel" buttons so we don't pollute the data factories.
- bot/keyboards/__init__.py — empty
- bot/keyboards/inline.py — builders, each returns
  InlineKeyboardMarkup:
    build_service_keyboard(services: list[Service])
    build_master_keyboard(masters: list[Master], service: Service)
    build_date_keyboard(start_date: date, master: Master,
      blackouts: list[Blackout]) — 14-day grid (2 rows × 7 cols);
      days outside master.work_days OR in blackouts render with
      striked label and a "dead" callback that triggers the toast
    build_slot_keyboard(slots: list[datetime]) — time buttons
      grouped by morning (<12:00) and afternoon (>=12:00) with a
      header row separator (a noop button "—— До обіду ——")
    build_confirm_keyboard() — Так / Скасувати
    build_back_button() — single Back button as a row
- bot/keyboards/reply.py — main_menu() with three buttons
  ("📅 Записатися", "📋 Мої записи", "❓ Допомога"), share_contact()
  with one button having request_contact=True
- bot/handlers/booking.py — handler per state, plus a /cancel command
  and a NavCB(action="back") handler that walks the state back one
  step preserving data. Use rate-limit-aware sleep (asyncio.sleep
  (0.05)) only around the owner-notification at confirmation, NOT
  for each user-facing reply.

- Update bot/handlers/start.py: when user taps "📅 Записатися" in the
  main menu, set state Booking.choosing_service and reply with
  build_service_keyboard(await sheets.load_services()).

UX details (memorize before writing):
- Calendar grid: 14 buttons in a 2×7 grid. Days outside master's
  work_days OR in blackouts get the strike label "̶1̶5̶" and a noop
  callback that on tap answers with .answer(text="Цей день
  недоступний", show_alert=False) — Telegram does NOT truly disable
  inline buttons; this is the convention.
- Slot keyboard: if calculate_available_slots returns []. show one
  "На цю дату вільних слотів немає" inline button (noop) and a
  separate "← Інша дата" back button row.
- All user-facing strings: Russian for v1 (project_specs.md OQ-2).
  Keep them centralized at the top of booking.py so localization is
  one search-and-replace.

Confirmation step (atomic from user's perspective):
1. Race-check: re-query slots fresh (don't trust FSM-cached
   availability), verify chosen slot is still free. If taken: show
   "Цей слот тільки що зайняли, оберіть інший" with build_slot_keyboard
   and return to Booking.choosing_slot.
2. booking_id = str(uuid.uuid4())
3. await sheets.append_booking(booking) — wait for success before next step
4. event_id = await calendar.create_event(master.calendar_id, booking)
   → await sheets.update_booking_status(booking.id,
   calendar_event_id=event_id) so the row carries the FK for cancellation.
5. await scheduler.schedule_reminder(booking.id, start - 24h, 24)
   and (booking.id, start - 1h, 1).
6. Send confirmation message to user with booking summary +
   "Скасувати запис" button (BookingActionCB(action="cancel")).
7. Send notification to OWNER_TELEGRAM_CHAT_ID with same summary.
8. await state.clear().

If step 3 fails: show generic error, do NOT proceed to 4-7.
If step 4 fails AFTER step 3 succeeded: mark the booking row with
status='confirmed' but calendar_event_id NULL; the owner notification
mentions "Calendar event will be created on next sync attempt"; log to
_errors. (Sheet write is the source of truth for billing/CRM; Calendar
write is a courtesy.)

Tests to write:
- tests/test_booking_states.py — FSM transition tests with mocked
  FSMContext, no Sheets/Calendar I/O. Walk from choosing_service →
  confirming, assert state and FSMContext data at each step.
- tests/test_keyboards.py — given fixture services/masters/dates,
  assert the keyboard structure (button count per row, callback_data
  shapes pack/unpack roundtrip).

Test pipeline:
```powershell
ruff check .; mypy bot/; pytest -v
```
Plus boot test: bot starts, full booking happy path against a real
test Sheet.

Update project_specs.md §11 with the final state transition table,
exact user-facing message per step, and FSMContext data shape per step.

Manual test I'll run:
- Full booking happy path: /start → "📅 Записатися" → pick service
  → pick master (if multi-master service) → pick date → pick slot
  → enter name (text) → enter phone → confirm → verify Sheet row,
  verify Calendar event, verify owner notification, verify
  scheduler.db gains rows for the two reminders.
- Edge cases:
  - /cancel mid-flow → returns to main menu, no Sheet row, FSM cleared
  - Back button at each step → previous state, partial data preserved
  - Pick a date with no available slots → friendly empty state with
    "← Інша дата" path back
  - Race: open two Telegram clients (phone + desktop), book the same
    slot from both → second attempt shows "слот зайняли" error and
    returns to slot picker
```

---

## Prompt 5 — My Bookings + Admin Commands

```
Read CLAUDE.md, project_specs.md, learnings.md.

Build view + cancel flows and admin commands per project_specs.md
§12 and §13.

Context7 lookups required:
- /websites/aiogram_dev_en_v3_27_0 — confirm:
  · BufferedInputFile for sending in-memory CSV as document
  · How to chain a custom filter (admin guard) with router decorators
  · CallbackQuery.answer(text=..., show_alert=True) for confirmation
    dialogs

Order-of-operations rule for cancellation (carried from project_specs.md
§14 — write-after-success pattern): the side effects that touch
external state come BEFORE the Sheet status flip. If a side effect
fails, the row stays 'confirmed' and the user can retry. Sequence:

1. scheduler.cancel_reminders(booking_id) — idempotent (ignores
   ScheduleLookupError); if it fails for non-lookup reasons, log
   and continue (next reminder fire will skip on status check)
2. calendar.delete_event(master.calendar_id, booking.calendar_event_id)
   — if 404, treat as already-deleted (success); other errors log
   and continue
3. sheets.update_booking_status(booking_id, status='cancelled',
   cancelled_at=now)  ← only now is the booking officially cancelled
4. Notify master via DM (if masters.telegram_id is set); failure here
   is non-blocking, just logs
5. Confirm to user with edited message ("Запис скасовано")

Modules to create:
- bot/handlers/my_bookings.py — handler for "📋 Мої записи" main-menu
  button. Lists user's upcoming bookings (status='confirmed',
  datetime_start > now). Each booking renders as one message (so the
  cancel button can edit its own message in place) with a
  BookingActionCB(action='cancel', booking_id=...) button.
- bot/handlers/admin.py — commands /today /week /stats /export, all
  gated by a custom filter `AdminFilter` that checks message.from_user.id
  in settings.admin_telegram_ids; non-admins get a single short reply
  "У вас немає прав на цю команду." and the handler returns.
  · /today — list today's confirmed bookings, grouped by master.id,
    one message per master with bullets.
  · /week — same shape for the next 7 days.
  · /stats — count of confirmed/cancelled/completed/no_show for the
    current calendar month, one summary message.
  · /export — generate CSV in memory of all bookings in the current
    month, send via BufferedInputFile(file=bytes_, filename=
    f"bookings-{YYYY-MM}.csv"); follow-up inline button "Усі записи"
    that re-runs with no date filter.

Tests:
- tests/test_admin_guard.py — assert AdminFilter returns False for a
  non-admin user_id, True for an admin user_id; assert the handler
  short-circuits when filter returns False (mock-based).
- tests/test_cancellation_order.py — mock SheetsService, CalendarService,
  scheduler; call the cancel handler; assert call order matches the
  sequence above. This is the most important test in the prompt —
  it locks in the write-after-success discipline.

Test pipeline:
```powershell
ruff check .; mypy bot/; pytest -v
```

Update project_specs.md §12 and §13 with final message templates and
exact admin command behaviors. Add a "Cancellation invariants" subsection
to §12 listing the order-of-operations rule above.

Manual test I'll run:
- Create a test booking (Prompt 4 flow), tap "📋 Мої записи" → see it
  → tap "Скасувати" → verify slot is freed (re-open booking flow on
  the same master+date → slot is back), Calendar event gone in Google
  Calendar, scheduler.db shows the two reminder rows removed
- /today, /week, /stats, /export as admin user → all return expected
  output. /export attachment opens cleanly in Excel/LibreOffice
- /today as non-admin user → "У вас немає прав на цю команду." reply
```

---

## Prompt 6 — Reminders (APScheduler 4)

```
Read CLAUDE.md, project_specs.md, learnings.md.

Wire APScheduler reminders per project_specs.md §14. The
write-after-success idempotency pattern and the importable-callable
constraint are HARD requirements — both are in CLAUDE.md constraints
and project_specs.md §14.

Context7 lookups required (use these exact library IDs):
- /agronholm/apscheduler — confirm:
  · DateTrigger run_time parameter shape (datetime aware vs naive;
    project uses Europe/Kyiv-aware datetimes throughout)
  · ConflictPolicy.replace behavior on add_schedule with existing id
  · How to pass args/kwargs to the scheduled callable
  · Behavior when the serialized callable cannot be re-resolved
    after restart (silent drop vs error)
  · remove_schedule and the exception raised when id not found
    (ScheduleLookupError or similar)

Modules to modify / create:
- bot/services/scheduler.py — flesh out schedule_reminder(),
  cancel_reminders() that you stubbed in Prompt 3. Pull
  send_reminder via `from bot.handlers.reminders import send_reminder`
  at module top so it's a stable importable reference.
- bot/handlers/reminders.py — NEW. Module-level function
  `async def send_reminder(booking_id: str, hours_offset: int) -> None`.
  Steps (order matters):
    1. Load booking from Sheets via sheets.load_booking_by_id
       (add this method if missing)
    2. If status != 'confirmed' → log "skip cancelled" and return
    3. If the corresponding reminder_X_sent flag is already truthy
       → log "skip already sent" and return
    4. Send DM to booking.client_telegram_id via bot.send_message
       with the reminder text (see template below)
    5. ONLY after the DM succeeds (no exception), call
       sheets.set_reminder_sent_flag(booking_id, hours_offset)
    6. If the DM fails, propagate the exception so APScheduler logs
       it; the unflipped flag means a manual retry / next cron tick
       can pick it up
  The Bot instance: pass it via APScheduler's `args=(booking_id,
  hours_offset)` is insufficient because Bot is not serializable.
  Instead, store Bot at module level in bot/handlers/reminders.py
  (set from main.py's startup), so send_reminder can read it from
  the module global. Document this in project_specs.md §14.
  Reminder text template (Russian for v1, see OQ-2):
    24h: "⏰ Нагадування: завтра в {time} у вас запис на «{service}»
           до майстра {master}. Адреса: ..."
     1h: "🔔 Через годину — запис «{service}» у майстра {master}."
  Keep template constants at module top.

- bot/handlers/booking.py — at the confirmation step (after the
  Sheet write + Calendar create succeed), call
  `await scheduler.schedule_reminder(booking.id, start - timedelta
  (hours=24), 24)` and the 1h equivalent. If schedule_reminder
  itself raises, log to _errors but still confirm to the user
  (the reminder is a nice-to-have; the booking is the contract).

- bot/handlers/my_bookings.py — cancellation already calls
  scheduler.cancel_reminders FIRST per Prompt 5; verify it.

Critical (repeated for emphasis): send_reminder MUST live at module
scope in bot/handlers/reminders.py. No lambdas, no closures, no
nested defs. The CBOR serializer in APScheduler 4's data store
serializes the reference; non-module-level callables cannot be
re-resolved after restart and the job silently disappears.

Tests:
- tests/test_reminders.py — using mocks for Sheets and Bot:
  · test confirmed booking → DM sent + flag flipped
  · test cancelled booking → no DM, no flag change
  · test already-sent flag → no DM, no flag change
  · test DM raises → flag NOT flipped (assert), exception
    propagates out (assert with pytest.raises)

Test pipeline:
```powershell
ruff check .; mypy bot/; pytest -v
```

Update project_specs.md §14 with: the exact reminder text template,
the Bot-injection mechanism (module-level global vs alternative),
and any open questions.

Manual test I'll run:
- Temporarily change the reminder offset in bot/handlers/booking.py
  to `timedelta(minutes=5)` for both reminders so they fire 5 and
  ~4 minutes after a fresh booking
- Create a fresh booking via the FSM
- Wait → verify the 5-min reminder DM arrives
- Create another booking, then immediately Ctrl+C the bot, wait
  10 seconds, restart it
- Wait until the 5-min mark → verify the reminder STILL fires after
  restart (this proves persistence + module-level callable resolution)
- Create a third booking, cancel it via "📋 Мої записи" within the
  5-min window → verify the reminder does NOT fire
- Restore the real offsets (24h / 1h) before moving on
```

---

## Prompt 7 — WOW 1: Google Calendar Two-Way Sync

```
Read CLAUDE.md, project_specs.md, learnings.md.

Add the Calendar freebusy read into the slot calculator per
project_specs.md §15.

Context7 lookups required (use these exact library IDs):
- /googleapis/google-api-python-client — confirm:
  · service.freebusy().query() request body shape — fields:
    timeMin, timeMax (both RFC3339 strings), items (list of
    {id: calendar_id} dicts), timeZone (optional)
  · Response shape — calendars[<id>]['busy'] is list of
    {start: RFC3339, end: RFC3339} dicts
  · Whether RFC3339 from API is always UTC ('Z' suffix) or carries
    the original timezone — affects datetime.fromisoformat parsing

Modules to modify:
- bot/services/calendar.py — implement query_busy_intervals(
    master_calendar_id: str, d: date
  ) -> list[tuple[datetime, datetime]]
  Wrapping pattern:
    cache_key = (master_calendar_id, d.isoformat())
    if cache_key in cache and monotonic() - cache[cache_key].ts < 60:
        return cache[cache_key].intervals
    time_min, time_max = day_bounds_in_kyiv(d)
    body = {
      "timeMin": time_min.isoformat(),
      "timeMax": time_max.isoformat(),
      "items": [{"id": master_calendar_id}],
      "timeZone": settings.google_calendar_default_tz,
    }
    resp = await asyncio.to_thread(
      lambda: service.freebusy().query(body=body).execute()
    )
    busy = resp["calendars"][master_calendar_id].get("busy", [])
    intervals = [
      (parse_rfc3339(b["start"]), parse_rfc3339(b["end"]))
      for b in busy
    ]
    cache[cache_key] = CacheEntry(intervals, monotonic())
    return intervals
  parse_rfc3339 = datetime.fromisoformat after .replace("Z", "+00:00").
  Result intervals must be timezone-aware in Europe/Kyiv (convert
  from UTC if necessary) so they compare correctly to slot times.
- bot/handlers/booking.py — in the date-selected → slot-listing step,
  call calendar.query_busy_intervals and pass to
  slots.calculate_available_slots's calendar_busy_intervals param.

No new tests strictly needed — test_slots.py already covers the
"calendar conflict" case via the parameter. But add one integration-
style test that mocks the calendar service and asserts the cache TTL
behavior (hit + miss after 61 seconds).

Test pipeline:
```powershell
ruff check .; mypy bot/; pytest -v
```

Update project_specs.md §15 with the exact body shape used and the
RFC3339 parsing decision (UTC normalization vs preserve original tz).

Manual test I'll run:
- In Google Calendar (the master's calendar), add a manual event
  tomorrow 12:00-13:00 titled "Lunch"
- Go through booking flow for that master, that date
- Verify 12:00 and 12:30 slots are NOT in the list (assuming
  service.duration_min divides into the hour cleanly)
- Delete the calendar event
- Wait 65 seconds (cache TTL = 60s + buffer)
- Re-enter the date in the booking flow → 12:00 and 12:30 are back
```

---

## Prompt 8 — WOW 2: Automatic VIP Status

```
Read CLAUDE.md, project_specs.md, learnings.md.

Implement the daily VIP check per project_specs.md §16. Resolve
OQ-0 (idempotency mechanism — column vs sheet) before writing code
and document the decision in §16.

Context7 lookups required:
- /agronholm/apscheduler — confirm:
  · CronTrigger(hour=9, minute=0, timezone='Europe/Kyiv') param shape
  · Register-at-startup pattern with conflict_policy=ConflictPolicy
    .replace so re-registration on each bot restart is safe

Idempotency decision (resolve OQ-0):
Recommended: new sheet `_vip_sent` with columns A=client_telegram_id
(int), B=sent_at (ISO datetime). Reason: keeps `bookings` row schema
stable (no per-client column that requires backfill on existing rows),
makes the "who got a VIP DM" question one cheap read of a small sheet.
Trade-off accepted: one extra Sheets API call per check_vip_promos
run. If the operator overrides this in favor of a `bookings.vip_sent_at`
column, encode that and skip creating the sheet.

Modules to modify / create:
- bot/services/sheets.py — add load_vip_sent() -> set[int]
  (returns telegram IDs that already got the VIP DM) and
  append_vip_sent(client_telegram_id: int) -> None. Plus add an
  _vip_sent sheet tab to the operator's manual setup checklist (I
  will add it before running this prompt).
- bot/services/scheduler.py — schedule_daily_job is already in place
  from Prompt 3; in main.py on_startup, call:
    `await scheduler.schedule_daily_job("daily_vip_check",
       check_vip_promos, 9, 0)`
  with conflict_policy=replace (already the default in your
  schedule_daily_job wrapper if you followed Prompt 3 spec).
- bot/handlers/vip.py — NEW. Module-level
  `async def check_vip_promos() -> None`. Steps:
    1. completed = await sheets.load_completed_bookings()
       (group by client_telegram_id, count visits per client)
    2. upcoming_clients = clients with status='confirmed' booking
       in next 7 days
    3. already_sent = await sheets.load_vip_sent()
    4. candidates = clients where visits >= 5 AND client_telegram_id
       in upcoming_clients AND client_telegram_id not in already_sent
    5. For each candidate: await bot.send_message(client_telegram_id,
       VIP_MESSAGE_TEMPLATE.format(name=...)) with
       await asyncio.sleep(0.05) between sends (Telegram global rate
       limit); on success call append_vip_sent(client_telegram_id)
    6. Log a summary line: "VIP check: scanned N completed, candidates
       M, sent K, skipped J already-sent"
  VIP_MESSAGE_TEMPLATE constant at module top, Russian for v1:
  "⭐ {name}, вы наш VIP-клиент после 5 визитов! Промокод SUPERVIP
   на ваш следующий визит."
  Bot instance: same module-level injection pattern as
  bot/handlers/reminders.py.

Tests:
- tests/test_vip.py — pure logic test of the candidate-selection
  function. Extract the candidate-selection into a pure helper
  (e.g. `select_vip_candidates(completed: list[Booking], upcoming:
  list[Booking], already_sent: set[int]) -> list[int]`) so it's
  testable without mocking I/O. Cases:
  · client with 4 completed + upcoming → not a candidate
  · client with 5 completed + upcoming + not already-sent → candidate
  · client with 5 completed + upcoming + already-sent → skipped
  · client with 5 completed + NO upcoming → skipped

Test pipeline:
```powershell
ruff check .; mypy bot/; pytest -v
```

Update project_specs.md §16 with the decision (sheet vs column),
the exact VIP_MESSAGE_TEMPLATE wording, and the candidate-selection
algorithm. Resolve OQ-0 in §21.

Manual test I'll run:
- Mark 5 bookings as status='completed' for my own telegram_id, with
  a 6th upcoming booking in the next 7 days
- Add a temporary admin command `/run_vip` that calls check_vip_promos
  directly (you'll remove it before Prompt 10)
- Run /run_vip → I get the VIP DM
- Run /run_vip again → I do NOT get a duplicate; the log line shows
  "skipped 1 already-sent"
```

---

## Prompt 9 — WOW 3: Voice Name Input

```
Read CLAUDE.md, project_specs.md, learnings.md.

Add voice transcription to the contact-entry FSM state per
project_specs.md §17. We use Groq (not OpenAI) for Whisper — see
project_specs.md §2.1 and §9.4 for rationale (permanent free tier,
newer Whisper-Large-v3-turbo model, identical API shape).

Context7 lookups required:
- /groq/groq-python — confirm:
  · AsyncGroq client init shape (api_key handling — SecretStr
    .get_secret_value() at the call site)
  · client.audio.transcriptions.create signature: model, file
    (accepts Path, raw bytes, OR a (filename, contents, mimetype)
    tuple), language, response_format
  · Current Whisper model identifier — whisper-large-v3-turbo
    expected as of May 2026. If a newer model is listed (v4, etc.),
    flag in Open Questions before swapping.
  · Verify current groq SDK version against the pin in pyproject.toml
    from Prompt 2
- /websites/console_groq → optional, for rate-limit confirmation
  (free tier audio-seconds-per-day quota)
- /websites/aiogram_dev_en_v3_27_0 — confirm:
  · bot.download(file=...) — returns BytesIO (file-like)
  · message.voice attribute shape (file_id, duration, file_size)

Modules to create / modify:
- bot/services/whisper.py — NEW. class WhisperService:
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncGroq(
            api_key=settings.groq_api_key.get_secret_value()
        )
    async def transcribe(self, file_bytes: bytes,
                          filename: str = "voice.ogg",
                          language: str = "ru") -> str:
        resp = await self._client.audio.transcriptions.create(
            model="whisper-large-v3-turbo",
            file=(filename, file_bytes, "audio/ogg"),
            language=language,
            response_format="text",
        )
        # response_format="text" returns a string per Context7
        return str(resp).strip()
  (The class name "WhisperService" stays — it's the right name for
  the responsibility regardless of which provider hosts the model.)
- bot/handlers/booking.py — at the entering_contact state, add a
  third option alongside the existing text/share-contact: a
  "🎤 Голосом" inline button. On tap: edit the prompt to
  "Запишіть голосове повідомлення з вашим іменем" and stay in
  Booking.entering_contact. Add a new handler matching
  StateFilter(Booking.entering_contact) and F.voice. Steps:
    1. If message.voice.file_size > 1_000_000 (1 MB): reply
       "Файл занадто великий, спробуйте ще раз або введіть текстом"
       and return (stay in state)
    2. file_obj = await bot.download(message.voice.file_id)
       (file_obj is BytesIO per Context7)
    3. file_bytes = file_obj.read()
    4. try: name = await whisper.transcribe(file_bytes,
         language='ru')  except Exception as e: log to _errors,
         reply "Не вдалося розпізнати, введіть ім'я текстом",
         stay in state, return.
    5. If not name or len(name) > 50: reply "Не вдалося розпізнати
       чисто, спробуйте ще раз або введіть текстом", stay in state
    6. Show "Розпізнано: {name}. Підтвердити?" with two inline
       buttons: ✅ Підтвердити (advances to phone step with
       update_data(name=name)) and ✏️ Редагувати (reverts to text
       prompt, stays in state)

Validation summary:
- Reject voice files > 1 MB at the handler level
- On Whisper API error or empty/too-long transcription: friendly
  message, stay in state, do NOT throw (per learnings.md "Don't
  throw on partial / incomplete user-side data")
- The error handler routes only TRULY unexpected exceptions to
  _errors; transcription failures are user-flow events

Tests:
- tests/test_whisper.py — mock AsyncGroq client, verify:
  · transcribe passes the right model ("whisper-large-v3-turbo"),
    language, response_format
  · transcribe strips whitespace from the response
  · transcribe propagates exceptions from the SDK (so callers can
    handle them)
  · file tuple shape matches (filename, bytes, "audio/ogg")

Test pipeline:
```powershell
ruff check .; mypy bot/; pytest -v
```

Update project_specs.md §17 with: confirmed Whisper model identifier
(in case Groq released v4 since the spec was drafted), the exact 1 MB
limit rationale, the fallback message wording, the error-routing
decision (stay in state, do not raise to error handler).

Manual test I'll run:
- /start → "📅 Записатися" → walk to entering_contact step
- Tap "🎤 Голосом", record voice message saying my name
- Verify "Розпізнано: ..." appears, tap ✅ Підтвердити, finish booking,
  verify the name landed in Sheets correctly
- Edge cases:
  · Record a long ramble instead of a name → either rejected by the
    50-char length check or accepted and editable
  · Send a >1MB voice (long recording) → "файл занадто великий" reply
  · Temporarily set GROQ_API_KEY=gsk_bogus in Railway env (or local
    .env) → restart bot → fallback to text input works, _errors gets
    one row, owner gets one DM
  · Restore real GROQ_API_KEY after test
- After all tests: open Groq Console → Usage page → verify total
  charges this period = $0 (free tier confirmed working as expected)
```

---

## Prompt 10 — Deploy + README + final QA

```
Read CLAUDE.md, project_specs.md, learnings.md.

Three deliverables. No new feature code unless QA reveals a bug.

DELIVERABLE A — docs/architecture.md (NEW). Portfolio-grade
architectural overview, NOT a setup guide. ~300-500 words plus one
Mermaid system diagram. Sections:
- Why a Telegram bot (vs WhatsApp / web form)
- Why Sheets-as-CRM (cost zero, owner already knows the tool)
- Why APScheduler 4 (restart-safe; brief said v3, we explain why we
  ignored that — Context7-verified API rewrite)
- Why service-account calendar sharing (vs OAuth flow per master)
- Idempotency strategy (write-after-success, three guard mechanisms:
  reminder flags, VIP-sent tracking, status-before-side-effect ordering)
- AI as enhancement layer (Whisper is a UX nicety, not a hard
  dependency — the bot still works if the API goes down)
- Error handling chain (handler raises → errors_router → log +
  _errors sheet + owner DM, sanitized)
- Git as the disaster-recovery mechanism (workflow JSON committed;
  this project's code is the single source of truth)

DELIVERABLE B — README.md per project_specs.md §20:
- H1 + one-line value prop ("Telegram bot that replaces the
  booking-manager role for SMB salons / barbershops / studios.")
- Live demo: embedded GIF (I record after this prompt; you specify
  what 30-second sequence to capture — be explicit)
- Stack badges (Python 3.11, aiogram 3.27, APScheduler 4, Railway,
  Google Sheets API, Google Calendar API, Groq Whisper-Large-v3)
- Architecture: Mermaid system diagram (same one as
  docs/architecture.md, embedded inline)
- Three WOW features — one row each, with a one-line description and
  a screenshot placeholder filename (I capture after deploy is green)
- Project structure tree (pull from CLAUDE.md verbatim)
- Case narrative — problem (SMB manual booking is overhead), key
  architectural decisions (one paragraph each, link to
  docs/architecture.md for the deep dive), result
- Competencies block: Async Python, Aiogram FSM, External API
  Integration, Scheduling & Idempotency, AI Integration

DELIVERABLE C — final QA gate per project_specs.md §18.

Execute every item in §18.2 (Pipeline gate) and §18.3 (Production
readiness gate). For each item: confirm working with one-sentence
evidence (e.g. "booking flow ≤10 taps confirmed via test booking
2026-XX-XX at HH:MM, screenshot at docs/screenshots/...") OR report
failure with diagnosis. Use Context7 if any failure investigation
requires checking library behavior.

Specific drills to run during QA (these are the spec's hardest gates):
- Restart-survival drill: schedule a reminder 5 min out, redeploy
  via Railway, confirm reminder still fires
- Race-condition drill: two clients book the same slot within ~1 sec
  of each other; second attempt MUST show "slot taken" error
- Cancellation invariants drill: cancel a booking with a pending
  reminder; verify scheduler.db row gone, Calendar event gone, slot
  returns to availability list within 60 seconds (cache TTL)
- Webhook security drill: curl -X POST https://<app>/telegram/webhook
  WITHOUT the X-Telegram-Bot-Api-Secret-Token header → expect 401
- _health drill: curl https://<app>/health → expect 200 OK with
  {"status": "ok"}
- Voice fallback drill: temporarily revoke GROQ_API_KEY (set to
  gsk_bogus), restart, walk through voice-input flow → expect
  graceful fallback to text input + one row in _errors
- Free-tier verification drill: open Groq Console → Usage page →
  confirm total cost for the project's lifetime = $0 (proves we're
  inside the free tier; if non-zero, investigate which call escaped
  the free quota)

Update project_specs.md §22 (Build Retrospective) with:
- Biggest gotcha hit during the build
- Biggest time-saver discovered
- Library API surprises (APScheduler 4 lifecycle, gspread v6's
  removed get_records, anything else)
- What to do differently on Project 3

Report at end:
- list of every QA item with pass/fail/sentence-of-evidence
- list of every file created or substantially modified in this prompt
- the exact next operator action (record demo GIF, push to public
  repo, share link)

Manual test I'll run:
- Final end-to-end on production Railway: book a slot, get reminders
  (with temporarily reduced offsets), cancel, verify everything from
  §18.2 in real time
- Push to public GitHub repo, verify rendering on github.com
  (Mermaid diagram renders, GIF plays inline, badges resolve)
```

---

## Closing notes

- Prompts 1–6 are strictly linear; do not parallelize.
- Prompts 7, 8, 9 each touch existing modules in sequence — also linear.
- Prompt 10 is the final gate.
- Skipping the test pipeline at any prompt creates compounding debt. Run `ruff check . ; mypy bot/ ; pytest -v` every time — it's five minutes.

**Between every prompt, do three things on the operator's side, in this order:**
1. **Review what Claude Code reported.** Open the files it claims to have changed; spot-check that the actual change matches the report. Trust but verify — Claude's summary describes intent, not necessarily content.
2. **Run the manual user-facing test** described at the end of the prompt. The test pipeline (ruff/mypy/pytest) verifies code correctness; the manual test verifies feature correctness. Both must pass.
3. **Encode any new learnings into `learnings.md`** (or via your `/ce-compound` tooling). One short entry per surprise. Tag with the appropriate hashtag so future projects can grep.

**Only then move to the next prompt.**

If a manual test fails: do NOT move to the next prompt. Tell Claude Code what failed (the exact symptom, the exact reproduction step). Let it diagnose via Context7 + traceback + targeted code reading, fix in place, re-run both the test pipeline and the manual test. Only then continue.

**Claude Code's response shape on every prompt** (per CLAUDE.md → How to Respond): "What I just did", "Context7 lookups I made", "Files I created or modified", "What I added to project_specs.md", "What you need to do" (numbered operator actions), "Why" (one-sentence justification per non-obvious decision), "Next step", "Errors, if any". If a response skips any of these sections, push back — it's the structured contract for keeping the build legible.
