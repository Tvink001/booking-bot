# Project Overview

Build "Booking Bot" — a Telegram bot that lets a small-business customer book an appointment with a master (stylist, trainer, therapist) in under ten taps, and lets the business owner run the whole scheduling operation from Google Sheets as a lightweight CRM. The bot completely replaces a human "booking manager" for salons, barbershops, dance studios, and similar SMBs.

The bot speaks Russian and Ukrainian, runs on aiogram 3.x, stores bookings in Google Sheets, schedules reminders with APScheduler 4, and optionally syncs to Google Calendar two-way. Three WOW features distinguish it from a "basic" booking bot: Google Calendar two-way sync, automatic VIP status after five visits, and voice input for client name via Groq Whisper-Large-v3-turbo (free tier; OpenAI's Whisper was the original brief default but Context7 surfaced a better deal — full rationale in `project_specs.md` §2.1).

The technical specification lives in `project_specs.md`. Read it before any build step — it contains the FSM design, data model for all four Sheet tabs, integration patterns for each external API, the production-grade configuration, and the quality gates that decide when a build is done. `project_specs.md` is the single source of truth for technical decisions. Both you (Claude Code) and the operator update it as decisions get made during development.

`learnings.md` is the running log of patterns, gotchas, and reusable solutions discovered during the build. It grows over the project and seeds future projects. The operator maintains it.

---

# Required Toolchain

**Context7 MCP** is the primary tool for resolving any technical fact about a third-party library: exact class names, current API shapes, version-specific behavior, available scopes, response formats. Call `Context7:resolve-library-id` first to find the right library, then `Context7:query-docs` for the answer. The Python ecosystem moves fast — aiogram, APScheduler, gspread, google-api-python-client, groq, and pydantic-settings all have current versions that differ meaningfully from anything in the training data. Verify before writing code, not after a runtime error.

Use Context7 whenever you would otherwise rely on memory for a third-party API. The cost of an unnecessary query is small; the cost of writing code against an outdated API is real bugs and wasted operator time.

There is no n8n-MCP for this project. This is a Python codebase, not an n8n instance. Workflows are Python files, not JSON.

---

# Tech Stack

- **Language:** Python 3.11+ (3.12 acceptable)
- **Bot framework:** aiogram 3.26 stable (v3.27 latest; do not use v4 which is alpha)
- **Storage layer:** Google Sheets via gspread (sync) wrapped with `asyncio.to_thread`
- **Scheduler:** APScheduler 4.0+ with `AsyncScheduler` and `SQLAlchemyDataStore` on aiosqlite
- **Calendar integration:** google-api-python-client for Google Calendar API (sync, wrapped with `to_thread`)
- **AI voice input (WOW 3):** Groq Python SDK `AsyncGroq` for Whisper-Large-v3-turbo transcription (free tier, no credit card; replaces OpenAI per project_specs.md §2.1 rationale)
- **Config:** pydantic-settings v2 with `BaseSettings` and `SettingsConfigDict`
- **Web framework (webhook receiver):** aiohttp (comes with aiogram)
- **Deployment:** Railway (Dockerfile + persistent volume for SQLite jobstore)

Detailed integration rules for each library — credential setup, gotchas, async wrapping patterns, retry strategies — live in `project_specs.md` → Integration Rules.

---

# Constraints

These are absolute. Violation breaks the project. They are not negotiable.

- **Never commit secrets** — `.env`, `credentials.json` (service account), tokens, API keys. The `.gitignore` enforces this.
- **Never use synchronous I/O directly in async handlers.** gspread, googleapiclient, and any blocking library must be wrapped with `asyncio.to_thread()` (or run in a worker thread pool). A blocking call inside an async handler stalls the entire bot for every user.
- **Never let a single booking attempt double-book a slot.** Slot availability check and booking insert must be transactionally consistent — read availability, write booking, in a critical section. The exact mechanism depends on whether SQLite cache is used; document the chosen approach in `project_specs.md`.
- **Never silently swallow exceptions in handlers.** Every handler must either succeed, fail to the user with a clear message, or escalate to the error workflow. Aiogram's `errors_router` catches uncaught exceptions; route them to logging + Sheets `_errors` tab.
- **Never use plain f-strings to build callback_data** that includes user-controlled values. Use `CallbackData` factory from aiogram to enforce schema.
- **Never trust pre-existing assumptions about library APIs.** APScheduler 4 has a completely different API from 3.x (the brief still mentions 3.x). aiogram 3 has different syntax from aiogram 2. gspread v6 removed `get_records()`. Verify via Context7 before writing, especially for FSM state filters, scheduler triggers, Groq client initialization, and any Sheets read.
- **Never define an APScheduler-scheduled callable inside another function** (no lambdas, no closures, no nested defs). The `SQLAlchemyDataStore` + `CBORSerializer` serializes the callable reference; non-module-level callables cannot be re-resolved after a restart, and the job silently disappears. Every scheduled function lives at module scope in `bot/handlers/reminders.py` or `bot/handlers/vip.py`.

Infrastructure concerns (TLS, OS patches, automated DB backups) are Railway's responsibility — but the operator owns: env var management, persistent volume mount for SQLite, healthcheck endpoint configuration, webhook secret rotation. See `project_specs.md` → Production Configuration.

---

# Development Rules

**Rule 1: Always read first.** Before any action, read `CLAUDE.md`, `project_specs.md`, and `learnings.md`. If `project_specs.md` or `learnings.md` doesn't exist, create an empty version before doing anything else.

**Rule 2: Define before you build.** Before writing any non-trivial module (a handler, a service, a scheduler job), the relevant section of `project_specs.md` must be complete enough to build from. If it's incomplete or unclear, fill in what you can, list the remaining open questions, and wait for operator approval before writing code.

**Rule 3: Verify via Context7 before writing.** When writing code that touches a third-party library — aiogram, APScheduler, gspread, googleapiclient, groq, pydantic — call `Context7:query-docs` first to confirm the exact API. Especially for: aiogram FSM state declarations, scheduler trigger types, OAuth scopes, response object shapes. Do not write from memory if the library has had a major version bump in the last two years (aiogram 2→3, APScheduler 3→4, openai 0→1→2 as an instructive analogue even though we use groq now, pydantic 1→2).

**Rule 4: Look before you create.** Before adding a new module, list the existing structure (`view` on the project root). Reuse existing services, keyboards, states. Do not create a parallel `services2/` folder when `services/` already exists. Do not create new top-level folders without asking.

**Rule 5: Test before you respond.** After every code change that affects behavior, run the full local pipeline and report each step's outcome:
```powershell
# Windows PowerShell (operator's primary shell)
ruff check .
ruff format . --check
mypy bot/
pytest -v
$env:MODE="polling"; python -m bot.main      # smoke; Ctrl+C after /start round-trip
```
For Railway-deployed changes: trigger a redeploy and tail logs via `railway logs --follow`. Never say "done" without a confirmed-working test path. If a test fails, do not move forward — fix in place, re-run, and only then continue.

**Rule 6: Capture decisions in `project_specs.md`.** During every build, decisions get made that weren't in the spec — final FSM state names, exact slot-availability algorithm, retry backoff curve for gspread, voice-input file size limits. Update `project_specs.md` with these decisions as they happen, before the build is declared done. Tell the operator what you added so they can review and approve.

**Core Rule:** Do exactly what's asked. Nothing more, nothing less. If unclear, ask. If a test fails, fix in place and re-test — do not move forward with a failing module.

---

# How to Respond

Explain like you're talking to a Python engineer who knows the basics but doesn't have the current API of every library memorized. No jargon dumps. No walls of text.

For every response, structure as:

- **What I just did** — plain English, one paragraph
- **Context7 lookups I made** — list each `resolve-library-id` / `query-docs` call with one-line purpose
- **Files I created or modified** — list paths
- **What I added to `project_specs.md`** — short list of decisions captured, if any
- **What you need to do** — numbered steps for the operator (set env var, run local test, redeploy, etc.)
- **Why** — one sentence per non-obvious decision
- **Next step** — one clear action
- **Errors, if any** — show traceback or test output, what was diagnosed, exact fix applied

For external setup steps the operator handles (Google Cloud Console, BotFather, Railway, Groq Console), walk the exact menu path and explain what each setting does in one sentence. Be concise.

Never paste full file contents inline in responses if the file exceeds ~30 lines. Reference by path and let the operator open the file directly.

---

# Project Structure

```
booking-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py                     # entry point: bot, dispatcher, scheduler lifecycle, aiohttp app
│   ├── config.py                   # pydantic-settings BaseSettings
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py                # /start, main menu
│   │   ├── booking.py              # booking FSM (service → master → date → slot → contact → confirm)
│   │   ├── my_bookings.py          # view + cancel
│   │   ├── admin.py                # /today /week /stats /export
│   │   └── errors.py               # error handler routed from dispatcher
│   ├── keyboards/
│   │   ├── __init__.py
│   │   ├── inline.py               # calendar grid, slot picker, service picker, master picker
│   │   └── reply.py                # main menu, "Share contact" button
│   ├── services/
│   │   ├── __init__.py
│   │   ├── sheets.py               # gspread wrapper, all calls via to_thread
│   │   ├── calendar.py             # Google Calendar wrapper
│   │   ├── scheduler.py            # APScheduler 4 AsyncScheduler with SQLAlchemyDataStore
│   │   ├── whisper.py              # voice transcription via Groq (Whisper-Large-v3-turbo)
│   │   └── slots.py                # slot availability algorithm
│   ├── states.py                   # FSM StatesGroup definitions
│   └── callbacks.py                # CallbackData factory classes
├── tests/
│   ├── test_slots.py               # pure-function tests for slot calculator
│   ├── test_states.py              # FSM transition tests
│   └── conftest.py
├── data/
│   └── scheduler.db                # APScheduler SQLite jobstore (mounted volume on Railway)
├── Dockerfile
├── railway.toml
├── pyproject.toml                  # dependencies, ruff, mypy, pytest config
├── .env.example
├── .gitignore                      # excludes .env, credentials.json, data/, *.log
├── .mcp.json                       # Context7 MCP server config
├── README.md
├── CLAUDE.md                       # this file
├── project_specs.md
└── learnings.md
```

**Organization rules:**
- One handler module per top-level feature. Don't combine unrelated flows.
- Services are thin wrappers over external APIs. Business logic lives in handlers or in pure helpers (e.g. `slots.py`).
- Function-node-equivalent rule: any single function over 40 lines is a refactor signal. Split or extract.
- Don't create new top-level folders without asking.
- `data/` is mounted as a persistent volume on Railway; never put non-persistent state there.

---

# Linked Files — What's Where

`project_specs.md` is the technical brain of the project. FSM design, data models, integration rules, production configuration, quality gates, deployment recipe — everything technical lives there. It comes partially filled before development starts (with what's clear from the brief and from Context7-verified library facts) and grows during development as decisions get made. Both you and the operator write to it.

`learnings.md` is the running log of project-specific knowledge: gotchas discovered, libraries that behaved unexpectedly, async wrapping patterns that worked, regex patterns for Ukrainian/Russian phone normalization, Whisper accuracy notes. The operator maintains it. You can suggest additions when reporting after a prompt; the operator decides what to encode.

`README.md` is the public face of the project, written by you in the final prompt.

---

# Secrets & Safety

Tokens, API keys, and service-account JSON never appear in code or in committed config files. All secrets live in environment variables loaded via pydantic-settings, or — for `credentials.json` — in a Railway-mounted secret file path. The `.gitignore` excludes `.env`, `credentials.json`, `data/`, and `*.log`; do not bypass.

The error handler in `bot/handlers/errors.py` must sanitize any payload that gets logged to the `_errors` Sheet tab. Token strings, credential values, and user phone numbers should be redacted before persistence. Pattern: redact any field whose name matches `/token|key|password|secret|credential/i`.

Webhook validation: aiogram's `SimpleRequestHandler` accepts a `secret_token` that Telegram includes in the `X-Telegram-Bot-Api-Secret-Token` header. This must be set in production — without it, any third party can POST fake updates to your webhook URL.

---

# Scope

Build only what's in `project_specs.md`. Features ship in order: core booking FSM → cancellation → admin commands → reminders → WOW features (Calendar sync → VIP status → voice input). Do not parallelize. If unclear, ask the operator before starting.

Explicitly out of scope for v1: payment processing (Stripe / LiqPay), multi-language UI beyond Russian/Ukrainian, multi-tenant support (one bot = one business), web dashboard for the owner (the owner uses Sheets directly).

---

# Operator environment notes

The operator runs Windows 10 + PowerShell as the primary shell. Bash is available via the project's tooling but should not be assumed. When emitting shell commands in responses, use PowerShell syntax (`$env:VAR="..."`, backtick line continuation). When emitting `.env` examples, use the `KEY=value` format that pydantic-settings reads — PowerShell does not auto-export those values to the current shell session, so for ad-hoc local runs the operator either sets the var inline (`$env:MODE="polling"; python -m bot.main`) or uses a `.env` file that pydantic-settings loads via `SettingsConfigDict(env_file='.env')`.
