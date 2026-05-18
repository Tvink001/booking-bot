# Проект 2 — Полный пайплайн разработки

Этот документ — операторский. Он отвечает на четыре вопроса: что строить, в каком порядке, с каким временным бюджетом, против каких quality gates. Прочитай целиком один раз перед стартом — окупится многократно.

Документ не дублирует технические детали. Они живут в двух других файлах:
- `CLAUDE.md` — свод правил, который Claude Code читает на каждом промпте
- `project_specs.md` — техническая спецификация: архитектура, узлы, интеграционные правила, production-конфигурация, quality gates. И ты, и Claude Code пишете в него по ходу разработки.

`prompts.md` содержит атомарную последовательность промптов. `learnings.md` ты ведёшь сам — туда записываются gotchas и переиспользуемые паттерны.

---

## Что ты строишь

Telegram-бот для записи и бронирования. Клиент проходит сценарий: выбор услуги → выбор мастера → выбор даты → выбор слота → ввод имени и телефона → подтверждение. За ≤10 нажатий получает запись с напоминаниями за 24 часа и за 1 час. Владелец видит всё в Google Sheets как лёгкую CRM, получает уведомление в личный чат, использует админ-команды `/today /week /stats /export`.

Три WOW-фичи, отличающие от «базового» бота:
1. Google Calendar двусторонняя синхронизация — занятость, которую мастер заблокировал вручную в календаре, автоматически исключается из доступных слотов
2. Автоматический VIP-статус — клиент после 5 завершённых визитов получает ⭐ маркер и промокод на 6-й визит
3. Голосовой ввод имени — на шаге ввода контакта клиент может надиктовать имя голосом, Groq Whisper-Large-v3-turbo транскрибирует (бесплатный tier; обоснование замены OpenAI на Groq — в `project_specs.md` §2.1 и в разделе ниже)

Полный технический брейкдаун — в `project_specs.md` секции 6–17.

---

## Стек одним взглядом

Python 3.11+ — aiogram 3.27 (current stable per Context7 May 2026) — APScheduler 4 (мажорное расхождение с ТЗ, обоснованное) — gspread v6 sync через `asyncio.to_thread` (внимание: `get_records()` удалён в v6, использовать `get_all_records()`) — google-api-python-client для Calendar — **Groq Whisper-Large-v3-turbo** для WOW 3 (вместо OpenAI: бесплатный tier без CC, более новая модель v3 — детали ниже) — pydantic-settings v2 для конфига — Railway с Dockerfile и persistent volume для SQLite jobstore.

Все версии подтверждены через Context7 в мае 2026 и зафиксированы в `project_specs.md` секции 2 с обоснованиями. Полная таблица технологий — там же.

---

## Главное расхождение с ТЗ — APScheduler 4 вместо 3.x

Этот пункт критичен и стоит понять до старта. ТЗ написано с расчётом на APScheduler 3.x (упоминается `SQLAlchemyJobStore`, что является v3 API). С тех пор вышел APScheduler 4 с **полностью переписанным API**. Различия:

| Старый API (ТЗ, v3) | Новый API (мы используем, v4) |
|---|---|
| `AsyncIOScheduler` | `AsyncScheduler` |
| `SQLAlchemyJobStore` | `SQLAlchemyDataStore` |
| `scheduler.add_job(func, ...)` | `await scheduler.add_schedule(func, trigger, ...)` |
| `scheduler.start()` | `async with AsyncScheduler(...) as scheduler:` или `start_in_background()` |
| `BackgroundScheduler` | `start_in_background()` |
| Pickled job state | CBOR сериализатор (рекомендуется) |

Это значит, что любой туториал по APScheduler в интернете старше года скорее всего использует v3 API и **не будет работать в нашем коде**. Claude Code на каждом промпте, касающемся scheduler'а, обязан верифицировать API через Context7.

Та же осторожность нужна для aiogram (2→3 был major bump с полностью новым API), pydantic (1→2), openai (0→1→2). В `project_specs.md` секция 2.2 явно перечислены все эти расхождения от ТЗ — Claude Code их читает и помнит.

---

## Архитектурное упрощение OAuth → Calendar Sharing

ТЗ упоминает «service account + OAuth для мастеров» для Google Calendar. Полный OAuth flow для каждого мастера требует consent screen, redirect URL, persistent token storage, refresh token handling — около 200 строк кода. Я заменил это на более простую модель: каждый мастер шарит свой Google Calendar с email сервис-аккаунта (Calendar Settings → Share with specific people → email сервис-аккаунта → "Make changes to events"). Service account затем читает и пишет события на каждом календаре без OAuth.

Trade-off: каждому мастеру нужно сделать однократное действие шаринга. Зато никакой OAuth-инфраструктуры, проще онбординг для портфолио, та же модель аутентификации, что и для Sheets.

Это решение задокументировано в `project_specs.md` секция 2.2.

---

## Архитектурное упрощение OpenAI → Groq для Whisper

ТЗ упоминает OpenAI Whisper для WOW 3. Перед стартом сделан Context7-чек (май 2026) и обнаружено два факта, которые перевернули решение:

1. **OpenAI "Free" tier официально "Not supported" для API** (их собственная таблица rate limits). "$5 onboarding credit" — это маркетинговая ачивка, не задокументированная политика. Может быть, может не быть, требует CC, истекает за ~3 месяца. Для портфолио-проекта, который должен жить без биллинга, это неподходящая база.
2. **Groq хостит Whisper-Large-v3 и v3-turbo на постоянно бесплатном tier** с ASH/ASD (audio-seconds-per-hour/day) квотами, легко покрывающими демо-трафик. И эта модель **новее** OpenAI's `whisper-1` (которая v2), с заметно лучшей точностью на украинском и русском.
3. **API идентичен.** Groq экспонирует OpenAI-совместимый эндпоинт `/openai/v1/audio/transcriptions`. Python SDK `groq` имеет `AsyncGroq` с тем же `client.audio.transcriptions.create(...)`. Свап обратно на OpenAI — это 3 строки кода, если когда-то понадобится.

Trade-off: операторская часть Step 0 теперь регистрация на console.groq.com вместо platform.openai.com — нулевая разница по времени, но вместо обещания "потом, может быть, заплатишь" получаешь "никогда не заплатишь".

Решение задокументировано в `project_specs.md` секциях 2.1 и 9.4, в `learnings.md` отдельной seed-entry, в `prompts.md` Step 0 #6 и Промпте 9.

---

## Таймлайн — реалистичные оценки

Полная сборка занимает ~28 часов фокусной работы. При 8 часах/день — четыре рабочих дня (одна неделя с rest day по четвергу).

| Стадия | Работа | Часы |
|---|---|---|
| 0 | External setup (GCP, BotFather, Railway, Groq, MCP config) | 1.5 |
| 1 | Дополнение `project_specs.md` через диалог с Claude Code (Промпт 1) | 2 |
| 2 | Файловый scaffold + минимальный bot skeleton (Промпт 2) | 3 |
| 3 | Services layer без бизнес-логики (Промпт 3) | 4 |
| 4 | Booking FSM — ядро (Промпт 4) | 5 |
| 5 | My Bookings + Admin (Промпт 5) | 3 |
| 6 | Reminders через APScheduler 4 (Промпт 6) | 3 |
| 7 | WOW 1 — Google Calendar two-way sync (Промпт 7) | 1.5 |
| 8 | WOW 2 — Automatic VIP status (Промпт 8) | 2 |
| 9 | WOW 3 — Voice name input через Whisper (Промпт 9) | 1.5 |
| 10 | README + GIF + final QA + retrospective (Промпт 10) | 2.5 |

Slip-day buffer заложен. Если Стадия 4 (FSM-ядро) займёт 7 часов вместо 5 из-за aiogram-нюансов — итог всё ещё ложится в пять дней. Если ты на День 6 не закончил Стадию 10 — режь WOW-фичи, а не таймлайн (worst-case можно отшиппить с одной WOW из трёх, и проект всё ещё валиден как кейс).

Этот проект **значимо больше П1** по часам: 28 vs 22. Причины: Python codebase с unit-тестами против Cloud-managed n8n, FSM логика без визуального UI-инструмента для отладки, две API-интеграции с auth flow (Sheets и Calendar — vs одна в П1), и три WOW-фичи имеют существенные требования к реализации (Calendar freebusy с кешем, VIP daily check, Whisper async wrapper).

---

## Поэтапная разбивка

Каждая стадия мапится на один промпт в `prompts.md`. Здесь — что происходит на operator-side, на чём обычно спотыкаются.

**Стадия 0 — External setup.** Браузерные манипуляции + GCP project + Sheet + 5 вкладок + минимум один тестовый мастер шарит свой календарь с сервис-аккаунтом + Railway проект + persistent volume + credentials.json как secret file + `.mcp.json` с Context7 MCP. На Windows + PowerShell важно: (а) установить MCP-сервер глобально через `npm install -g @upstash/context7-mcp` и указать в `.mcp.json` путь к установленному `.cmd`-шиму, иначе `npx` даст 30 s timeout; (б) если корпоративная TLS-инспекция режет npm/Node trafiк — `npm config set strict-ssl false` на время установки + `"NODE_TLS_REJECT_UNAUTHORIZED": "0"` в env-блоке `.mcp.json`; (в) `.mcp.json` с секретами добавить в `.gitignore` — Claude Code `${VAR}` не резолвится из `.env` на Windows. Полная инструкция в `project_specs.md` §4.1. Готово когда: тестовая запись в `services` и `masters` вкладках Sheet есть, один мастер шарит календарь, Railway проект существует с persistent volume и credentials secret file, `.mcp.json` создан, **смоук-тест `Context7:resolve-library-id` для `aiogram` возвращает результат** (а не timeout).

**Стадия 1 — Планирование.** Ты приносишь `project_specs.md` с заполненными секциями `[filled]` (включая три seed-entries в Open Questions: OQ-0 для VIP-idempotency-стратегии, OQ-1 для формата Calendar event title, OQ-2 для языка reminder DM). Claude Code в Промпте 1 дозаполняет секции `[TBD via Prompt 1]` — главное это секция 10 (Module-by-module Design). Использует Context7 для верификации каждого import path по списку библиотечных ID в самом промпте. Если что-то не подтверждается через Context7 — добавляется в Open Questions. Ты ревьюишь, отвечаешь, аппрувишь. Готово когда: секция 10 полная, Open Questions имеет твои ответы на все четыре пункта (OQ-0..2 + любые новые).

**Стадия 2 — Scaffold + минимальный bot skeleton.** pyproject.toml, Dockerfile, railway.toml, `.env.example`, `.gitignore`. Плюс `bot/main.py` с polling/webhook режимами, `bot/config.py` с pydantic-settings, минимальный `/start` handler. Первый Railway deploy после этой стадии (Dockerfile уже есть). Готово когда: бот стартует локально через `MODE=polling python -m bot.main`, отвечает на `/start`. После push в GitHub → Railway деплой → `/health` возвращает 200.

**Стадия 3 — Services layer.** Тонкие async wrapper'ы над sync API. SheetsService, CalendarService, SchedulerService (АPScheduler 4 lifecycle), pure-функция calculate_available_slots, phone normalizer. Все sync gspread/googleapiclient вызовы через `asyncio.to_thread`. Это самая «техническая» стадия — много раз будешь вызывать Context7 для верификации API. Самая частая ошибка здесь — забыть `to_thread` в каком-то async handler'е, что блокирует event loop для всех пользователей одновременно. Готово когда: все services создаются без ошибок при старте бота, scheduler.db файл появляется, unit-тесты для slots.py и phone.py зелёные.

**Стадия 4 — Booking FSM.** Самая длинная стадия — ядро продукта. Полный FSM с шестью состояниями, callback_data factories, inline-клавиатуры для каждого шага (включая 14-дневную календарную сетку), confirmation step с race-check'ом для двойной записи на один слот. Это место где Claude Code может застрять — aiogram 3.x синтаксис существенно отличается от 2.x, и AI training data часто содержит микс. Бюджет 5 часов, принимай что может быть 7. Готово когда: полная запись от `/start` до confirmation работает, race-condition на двойную запись правильно обрабатывается, отмена сохраняет данные при возврате назад.

**Стадия 5 — My Bookings + Admin.** Просмотр и отмена записей пользователем, плюс четыре админ-команды. На отмене: освободить слот, удалить Calendar event, отменить scheduled reminders, уведомить мастера. Готово когда: цикл «создать → отменить → создать на тот же слот» работает (слот реально освобождается); админ-команды работают для admin user IDs и блокируются для остальных.

**Стадия 6 — Reminders через APScheduler 4.** Скедулинг напоминаний за 24 часа и за 1 час при создании записи; отмена при cancellation; **критичная проверка restart-survival** — пересоздание бота не должно терять scheduled reminders, потому что SQLAlchemyDataStore их сохраняет. Самая важная проверка здесь — что функция `send_reminder` импортируется по полному пути (не lambda, не closure), иначе CBOR-сериализатор APScheduler 4 не сможет её сохранить. Готово когда: reminder за 5 минут до тестового booking'а срабатывает; restart бота между schedule'ом и fire не теряет reminder; cancelled booking не получает reminder.

**Стадия 7 — WOW 1: Calendar two-way sync.** Самая короткая WOW-фича. Добавить freebusy query в slot calculator, плюс 60-секундный TTL cache per (master, date). Готово когда: ручное добавление события в Google Calendar мастера исключает соответствующие слоты из бота; удаление события возвращает слоты через минуту.

**Стадия 8 — WOW 2: Automatic VIP status.** Daily CronTrigger на 09:00 Europe/Kyiv. Сканирует клиентов с 5+ completed визитами, у которых есть upcoming booking в следующие 7 дней, шлёт VIP DM с промокодом — один раз на клиента (idempotency через флаг). Решение «новый column в bookings или отдельный sheet `_vip_sent`» принимается Claude Code в ходе разработки и фиксируется в `project_specs.md`. Готово когда: тестовый клиент с 5 completed visits получает VIP DM ровно один раз.

**Стадия 9 — WOW 3: Voice name input.** AsyncGroq client + Whisper-Large-v3-turbo (бесплатный tier, без CC). Aiogram `bot.download()` для voice message, передача в `client.audio.transcriptions.create(model="whisper-large-v3-turbo", file=(name, bytes, "audio/ogg"), language="ru", response_format="text")`. Лимит файла 1 МБ на handler-уровне (Groq позволяет 25 МБ, но имя клиента не может быть длиннее). Fallback на текстовый ввод при ошибке API. Готово когда: голосовой ввод имени работает на русском и украинском, fallback при API ошибке корректен, Groq Console показывает $0 charges по итогам всех тестов.

**Стадия 10 — README + final QA.** README с GIF, Mermaid-диаграммой, тремя WOW-фичами, case narrative, competencies блоком. Финальный прогон pipeline gate + production readiness gate из `project_specs.md` секции 18. Build retrospective в секции 22. Готово когда: репозиторий публичный, README корректно рендерится на GitHub, все pipeline и production gates зелёные.

---

## Quality gates — кратко

Формальные критерии живут в `project_specs.md` секция 18. Здесь — operator-side discipline:

**Per-prompt gate.** После каждого промпта: `ruff check .` чистый, `mypy bot/` чистый, `pytest -v` зелёный для затронутых тестов, manual smoke в polling режиме без exception'ов, `project_specs.md` обновлён с решениями принятыми в ходе сборки, твой manual test (описан в конце каждого промпта в `prompts.md`) прошёл.

**Pipeline gate (после Промпта 10).** Полный end-to-end на production Railway deploy. Полный booking flow ≤10 нажатий, запись в Sheet ≤2 сек, Calendar event ≤5 сек, reminders срабатывают, отмена освобождает слот и удаляет Calendar event и scheduled reminders, owner notification, admin команды работают для admin/блокируются для остальных, все три WOW-фичи работают, error handler ловит намеренные ошибки.

**Production readiness gate.** Все env vars в Railway, persistent volume mounted в `/app/data` с scheduler.db, credentials.json mounted в `/app/secrets/`, `WEBHOOK_SECRET` верифицирован (POST без header → 401), `/health` возвращает 200, graceful shutdown работает, restart-survival drill для одного reminder'а пройден, README имеет case narrative.

Если хоть один гейт красный — не двигайся. Это и есть дисциплина.

---

## Дисциплина процесса

**Context7 — это не опциональный спидбамп.** В П1 он был полезен для уточнения. В П2 он критичен. Python ecosystem движется быстрее, чем n8n-узлы — каждая мажорная версия библиотек ломает API. Claude Code должен звать Context7 перед каждым нетривиальным касанием третьих библиотек. Если ты замечаешь, что Claude Code пишет код для aiogram/APScheduler/groq/pydantic без предварительного Context7 lookup — это red flag, попроси перепроверить.

**Async wrapping pattern.** Самая частая категория багов в этом проекте — забытый `to_thread` для sync gspread или googleapiclient вызова. Один такой пропуск делает бот неотзывчивым для всех под нагрузкой. Code review в твоей голове на каждый сервис: «нет ли здесь sync I/O в async функции?»

**`learnings.md` — твоя долгосрочная память.** Каждая запись 3–10 строк, датированная, тегированная (`#aiogram`, `#apscheduler`, `#gspread`, `#calendar`, `#whisper`, `#pydantic`, `#debugging`, `#context7`). Когда Проект 3 столкнётся с той же async wrapping issue, `grep "#aiogram" learnings.md` — твой shortcut.

**`project_specs.md` растёт по ходу.** Каждая стадия добавляет в спеку реальные решения — финальный регекс нормализации телефона, точный текст ошибки слота, конкретный prompt для Whisper, выбранная стратегия idempotency для VIP проверки. К концу проекта `project_specs.md` — это living документ, который становится семенем для Проекта 3.

**Для Проекта 3** первое, что Claude Code читает — полный `learnings.md` Проекта 1 и Проекта 2. Уроки компаундируются. К Проекту 6 у тебя мастер-набор: проверенные паттерны async wrapping'а, шаблоны FSM, верифицированные через Context7 import paths, проверенные idempotency патерны.

Это loop, который превращает 28-часовой второй build в 18-часовой третий в 10-часовой шестой.

---

## Когда вещи ломаются

Реалистичные failure modes для P2. Каждый — это будущая запись в `learnings.md`.

**«Бот зависает под нагрузкой / handlers перестают отвечать».** Почти всегда — забытый `to_thread` где-то в services. Один sync gspread call в async handler'е блокирует event loop полностью. Найди через grep'ы: где gspread / googleapiclient / любая sync I/O вызывается напрямую из async функции. Обернуть в `await asyncio.to_thread(...)`.

**«APScheduler не восстанавливает reminders после рестарта».** Три возможные причины:
1. Persistent volume не примонтирован — `data/scheduler.db` пересоздаётся каждый деплой
2. Функция-callable обёрнута в lambda/closure/local function — CBOR serializer не может её десериализовать после рестарта. Решение: вынести в module-level функцию с импорт-доступным путём
3. `conflict_policy=ConflictPolicy.replace` не передан — попытка re-schedule даёт ошибку и тихо пропускает

**«Telegram-callback ничего не делает / кнопка не реагирует».** Aiogram 3.x: callback'и обрабатываются `@router.callback_query`, не `@router.message`. Также убедись что `CallbackData` factory правильно используется в фильтре: `MasterCB.filter()` а не `F.data.startswith("mst:")`.

**«FSM-state теряется между сообщениями».** Самая частая причина: разные routers инстанцируются с разными `Dispatcher` или storage. Должен быть один dispatcher, один storage, все routers через `dp.include_router(...)`. MemoryStorage очищается при рестарте бота — это ожидаемое поведение для v1, для production рассмотри RedisStorage (см. `project_specs.md` секция 8).

**«Whisper возвращает gibberish или пустую строку».** Проверь: voice message не пустой, файл реально загружается через `bot.download()` (не путь к файлу!), `language='ru'` или `'uk'` передаётся в `transcriptions.create`, модель указана как `whisper-large-v3-turbo` (не `whisper-1` — это OpenAI-наследие в куске закешированного knowledge у AI). Whisper-v3 на украинском заметно лучше v2, но если всё равно плохо для конкретного диалекта — фолбэк на `language='ru'` и принять компромисс. Если ошибка `401 Unauthorized` — проверь, что `GROQ_API_KEY` (не `OPENAI_API_KEY`) задан и валиден в Railway env.

**«Slot calculator возвращает занятые слоты как доступные».** Проверь что bookings filter включает `status='confirmed'` (не все), и что timezone везде согласованы (Europe/Kyiv в `_config`, в Calendar events, в datetime сравнениях). Mixing naive vs aware datetimes — частая причина 1-часового сдвига и неправильных слотов.

**«Pydantic Settings не подхватывает .env переменные».** В pydantic v2 + pydantic-settings v2: `BaseSettings` импортируется из `pydantic_settings`, не из `pydantic`. `model_config = SettingsConfigDict(env_file='.env')` обязательно. Если field имеет alias через `Field(alias=...)`, читается по alias'у, не по имени поля. Также: PowerShell не экспортирует `.env` в текущий shell автоматически — для ручных запусков либо `$env:VAR="..."` inline перед командой, либо положиться на `SettingsConfigDict(env_file='.env')`.

**«`AttributeError: 'Worksheet' object has no attribute 'get_records'`».** gspread v6 удалил `get_records()`. Замена: `worksheet.get_all_records(head=1)` для всей таблицы. Для частичного диапазона — `worksheet.get(range)` + `gspread.utils.to_records(header, cells)`. Любой туториал или AI-сгенерированный код, ссылающийся на `get_records()`, целит в pre-v6 API. Урок проверен через Context7 (`/burnash/gspread` README) — записан в `learnings.md` как seed entry от мая 2026.

**«Railway deploy завершается успешно, но бот не отвечает».** Проверь: `MODE=webhook` установлен в env vars? `WEBHOOK_BASE_URL` указывает на правильный Railway public domain? `WEBHOOK_SECRET` совпадает с тем что Telegram использует? `bot.set_webhook()` действительно вызывается в `on_startup`? Test: `curl -X POST https://<your-app>/telegram/webhook` без secret header → должно вернуть 401 (валидно), что подтверждает что endpoint работает.

Каждый из этих failure modes должен попасть в `learnings.md` с тегом `#debugging` после фикса. В следующем проекте `grep "#debugging" learnings.md` — твой шорткат к фиксам, которые ты уже знаешь.

---

## После Стадии 10 — что дальше

Портфолио-кейс живой. Три действия:

**Обнови портфолио-сайт.** Project card для П2 рядом с П1. Зеркаль README: value prop, GIF, competencies блок. Покажи разнообразие технологий между П1 (low-code n8n) и П2 (full-code Python) — это сигнал что ты не one-trick pony.

**Напиши Freelancehunt proposal template для booking botов.** Опираясь на reference проекты из ТЗ (1617411 студия танцев, 1260079 процедуры, 1584623 салон красоты, 929705 переговорные), задрафтай proposal со ссылкой на репо. Подчеркни Calendar two-way sync и voice input — обе фичи прямо упомянуты как недостающие в реальных тендерах.

**Compound the project, не закрывай его.** Перечитай `learnings.md` от начала до конца. Вытащи entries которые генерализуются за пределы П2 — async wrapping patterns, FSM templates, APScheduler 4 lifecycle, Whisper integration. Они становятся seed'ом для `project_specs.md` Проекта 3 (document processor — там Claude Code, Telegram bot, PDF/DOCX extraction). Проект 3 переиспользует **значительную часть** P2 infrastructure: тот же aiogram skeleton, тот же config setup, тот же error handler pattern, ту же deploy infra.

Проект 3 стартует с 30-минутного review `learnings.md` П2 и 1-часового драфта `project_specs.md` под document-processing домен. Промпт 1 Проекта 3 включает: «Прочитай `learnings.md` из Проекта 2 перед планированием.» Это compound в действии.

---

## Резюме одним параграфом

Построй «Booking Bot» за 28 часов в 4–5 рабочих дней на Python 3.11 с aiogram 3.x + APScheduler 4 + gspread + Google Calendar + Groq Whisper-Large-v3-turbo (бесплатный tier; OpenAI Whisper из ТЗ заменён на Groq — обоснование в §2.1 спеки), задеплой на Railway. Стадия 1 — допиши `project_specs.md` через диалог с Claude Code; стадия 2 — scaffold + минимальный bot skeleton + первый Railway deploy; стадии 3–6 — собери услуги, FSM-ядро, отмену, админ-команды, reminders; стадии 7–9 — уложи три WOW-фичи слоями; стадия 10 — README, deploy, final QA. Claude Code пишет Python код напрямую через create_file/str_replace, верифицирует каждый non-trivial third-party API через Context7 перед написанием. Ты между промптами планируешь, ревьюишь, тестируешь руками, фиксируешь уроки в `learnings.md` своим compound engineering процессом. Три quality gates — per-prompt, pipeline, production-readiness — пройдены прежде чем линковать с портфолио-сайта. Результат — второй портфолио-кейс с принципиально другим стеком (Python + FSM vs n8n + workflows из П1) и фундамент для Проекта 3 (document processor), который значительно переиспользует инфраструктуру.
