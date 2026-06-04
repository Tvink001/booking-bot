# Loom Video — Script + Recording Guide

Інструкція для запису portfolio-grade Loom відео тривалістю **5–7 хвилин**. Відео — це твоя "візитка" для рекрутера/CTO, що відкривають твій GitHub. На відміну від GIF (10-секундна тизер-demo), Loom — це деталізований walkthrough з твоїм голосом, який пояснює "чому", а не лише "що".

## Вибір мови

- **Українська** — якщо таргетиш UA/EU ринок, говориш природно. Default choice для цього проекту.
- **Англійська** — якщо подаєшся в Big Tech / US-based стартапи. Перекажи нижчий скрипт; пройдися рот-перевір текстом до запису, бо акцент впливає менше за впевненість.
- **Російська** — НЕ рекомендована: project text RU, але recruiter audience це сприйме як політичний сигнал.

Якщо вагаєшся — запиши **дві версії** (UA + EN), завантаж обидві у Loom як окремі videos, у README дай посилання на UA з підпискою "EN version available".

## Чому Loom (а не YouTube)

- **Loom video host** — рекрутер бачить твою face cam в куті + screen одночасно (це highly engages).
- **Speed control 1.5×–2×** — recruiter може дивитися швидше.
- **Tracking** — Loom показує, скільки секунд recruiter дивився (analytics).
- **Free tier** — 25 видео по 5 хв (saw the recent docs — Loom Free plan changed; verify before recording. Якщо вийшло за ліміт — Loom Starter = $12.5/міс, можна відписатися після рекрутингу).
- **No-config sharing** — URL працює зразу, не треба public/private setup як на YouTube.

---

## Pre-flight

### 1. Технічний setup (15 хвилин)

- **Loom Desktop app** (не browser extension — desktop дає кращу якість): https://www.loom.com/download
- **HD camera** ON — recruiter бачить твоє обличчя в куті (15% engagement boost vs voice-only).
- **Микрофон** — використай headset або зовнішній USB mic. Built-in laptop mic — last resort.
- **Screen resolution** — 1920×1080 (Full HD). Усе, що нижче — текст у Telegram / Sheets буде нечитабельний.
- **Two monitors** — ідеально. На моніторі 1: те, що показуєш (Telegram + Sheets + IDE). На моніторі 2: цей скрипт, щоб не блукати очима.
- **Loom settings:**
  - Recording: **Screen + Cam**
  - Camera: **Bubble (bottom-right corner)**, size: medium
  - Resolution: **1080p HD**
  - Microphone: твій mic (test → playback)
  - Drawing tool: **enabled** (для annotation під час architecture overview)

### 2. Environment setup (10 хвилин)

- **Bot запущений локально:** `$env:MODE="polling"; python -m bot.main` — лог "Polling started", "APScheduler started".
- **Telegram Desktop** відкритий, шрифт збільшений (Settings → Interface → 110–120% zoom — щоб recruiter бачив текст).
- **Telegram window size** — приблизно 500×800 (вертикальний phone-like), не на весь екран.
- **VS Code** з відкритим проектом, default theme — Dark+ (контрастна, читабельна на компресованому Loom).
- **Browser tabs підготовлені** (по порядку, бо переключатимешся):
  1. GitHub repo → `README.md` зверху
  2. GitHub repo → `docs/architecture.md`
  3. Google Sheet → tab `bookings`
  4. Google Calendar → master's view (де буде створюватись event)
  5. Groq Console → Usage page (для $0 proof)
- **Sheets pre-state:**
  - `bookings` tab — порожній або 1-2 historical записи (не безлад)
  - `_vip_sent` tab — порожній (видали свій id якщо є)
  - 5 рядків зі своїм tg_id зі status=`completed` (для VIP demo)
  - 1 рядок зі своїм tg_id зі status=`confirmed` + datetime_start у наступні 7 днів
- **Calendar pre-state:**
  - На master's Calendar додай подію "Lunch 12:00–13:00" на завтра (для WOW 1 demo) — її не видаляй до зйомки.

### 3. Прочитай скрипт двічі вголос — таймер на 6 хв

Якщо вийшло за 7 хв — скорочуй secondary деталі. Якщо менше 5 — додай ще одну архітектурну деталь.

---

## Script (6 хв) — UA version

> **Маркери:** `[ACTION]` = що ти робиш на екрані; `[SAY]` = твій текст; `[DRAW]` = Loom annotation tool.

### 0:00–0:30 — Intro (30s)

**[ACTION]** Відкрита перша вкладка — README.md на GitHub.

**[SAY]**
> "Всім привіт, мене звати Артем. Хочу показати тобі Telegram-бот для бронювання послуг, який я зробив для малого бізнесу — салонів, барбершопів, студій танцю. Це повна заміна людини-адміністратора: клієнт записується сам за 10 тапів, власник керує всім через Google Sheets, який він і так знає. Збудовано на Python 3.11, aiogram 3.27, з трьома AI-фічами, які виділяють його з-поміж типових booking-ботів. Покажу як працює і яка архітектура під капотом."

### 0:30–1:30 — Demo: повний booking flow з voice input (60s)

**[ACTION]** Перемкнись на Telegram. `/start` → 📅 Записаться → service → master → date → slot.

**[SAY]** *(йдеш по екрану, не зупиняючись)*
> "Дивись як це виглядає для клієнта. /start — головне меню. Записатися. Послуга — стрижка. Майстер. Дата — на завтра. Слоти. Зверни увагу — слотів 12:00 і 12:30 немає, тому що майстер заблокував обід у своєму Google Calendar. Це двостороння синхронізація — перша WOW-фіча. Беру 14:00."

**[ACTION]** На name prompt — натиснути 🎤 Голосом.

**[SAY]**
> "Замість того, щоб писати ім'я — натискаю 'Голосом'. Це третя WOW-фіча, на Groq Whisper Large v3."

**[ACTION]** Натиснути record button, сказати "Артем" або "Богдана", відпустити.

**[ACTION]** Через 1-2 секунди з'явиться "Распознано: …" — натиснути ✅ Подтвердить.

**[SAY]**
> "Розпізнало. Підтверджую. Тепер телефон — через нативну кнопку Telegram 'Поделиться контактом'. Підтверджую запис. Готово — клієнт отримує підтвердження, власник у групі отримує DM, у Google Calendar створюється подія, плануються нагадування за 24 години і за 1 годину."

### 1:30–2:00 — Side-by-side: Sheets + Calendar (30s)

**[ACTION]** Перемкнись на Google Sheets → tab `bookings`. Прокрути до останнього рядка — щойно створеного.

**[SAY]**
> "Ось щойно створений запис у Sheets — 15 колонок, від UUID до visit_count snapshot. Власник тут редагує статуси: confirmed → completed коли клієнт прийшов."

**[ACTION]** Перемкнись на Google Calendar.

**[SAY]**
> "І ось подія в Calendar майстра. Ім'я клієнта, послуга, телефон у description. Майстер може це використовувати у своєму звичному календарі без жодних додаткових застосунків."

### 2:00–3:30 — Architecture deep-dive (90s)

**[ACTION]** Відкрий `docs/architecture.md` на GitHub. Прокрути до Mermaid діаграми.

**[SAY]**
> "Тепер архітектура. *[вкажи на діаграму через Loom annotation tool]* Telegram client спілкується з нашим aiogram dispatcher через webhook з secret-token validation. Dispatcher тримає 6-стейтну FSM для booking flow і admin filter для adminських команд. Окремо живе APScheduler 4 з персистентним SQLite jobstore — він пам'ятає всі нагадування навіть після рестарту бота. Зовні бот пише в Google Sheets, читає/пише в Calendar, надсилає голос у Groq Whisper API."

**[ACTION]** Прокрути до секції "Why APScheduler 4".

**[SAY]**
> "Цікавий момент — у технічному завданні було v3, але v3 більше не підтримується. Через Context7 MCP я підняв документацію v4 і побачив, що це повний рерайт API — AsyncScheduler замість AsyncIOScheduler, add_schedule замість add_job. Тому я свідомо пішов проти специфікації. Це задокументовано і прийнято раніше за код."

**[ACTION]** Прокрути до "Idempotency strategy".

**[SAY]**
> "Найбільш технічно цікаве — write-after-success ідемпотентність. На кожен side effect — DM, Calendar write, status flip — спочатку зовнішній виклик, тільки потім guard flag у Sheets. Якщо процес помирає посередині — наступна спроба безпечно повториться. Це три незалежні guard-механізми: reminder flags, _vip_sent sheet, і порядок 5-ти кроків при cancellation."

### 3:30–4:30 — Three WOW features (60s)

**[ACTION]** Перемкнись на README. Прокрути до WOW таблиці.

**[SAY]**
> "Три AI/integration-фічі, які виділяють бот з-поміж типових. Перша — двостороння Calendar синхронізація: ти бачив, що слоти 12:00 зникли, тому що в Calendar майстра подія 'Lunch'. 60-секундний кеш на freebusy запити. Жодних webhook-ів — pull-based по запиту."

**[ACTION]** Згадай VIP feature.

**[SAY]**
> "Друга — автоматичний VIP-статус. Денний крон о 9 ранку Києва шукає клієнтів з 5+ завершеними візитами і одним майбутнім записом — надсилає одноразовий promo DM. Ідемпотентно через окремий лист _vip_sent."

**[ACTION]** Перемкнись на Groq Console → Usage.

**[SAY]**
> "Третя — голосове введення імені. Замість друку ім'я можна надиктувати. Whisper Large v3 turbo через Groq — free tier, нуль доларів. Ось доказ — Usage за весь lifetime проекту = 0 долларів. *[покажи total cost]* Якщо API падає або ключ невалідний — graceful fallback на текстовий ввід плюс рядок у _errors. AI як enhancement, не critical path."

### 4:30–5:30 — Production hygiene + tests (60s)

**[ACTION]** Перемкнись на IDE. Відкрий `tests/` каталог.

**[SAY]**
> "Тестове покриття — 77 тестів на 11 файлів. Фокус на чисті функції: slot availability, phone normalization, candidate selection для VIP. Плюс FSM transition tests. Плюс idempotency invariants — наприклад, що при API failure прапорець reminder_sent НЕ перевертається. Прогон pipeline — *[відкрий term, виконай ruff/mypy/pytest]* — все зелене за 11 секунд."

**[ACTION]** Покажи pytest output (можна заздалегідь у terminal).

**[ACTION]** Відкрий `bot/handlers/errors.py` (або згадай sanitization).

**[SAY]**
> "Безпека — webhook secret-token валідація, sanitized error logging з regex redaction для token/key/password/credential, service-account credentials у Railway secret store. Жодних секретів у репозиторії — .gitignore це enforce-ить."

### 5:30–6:00 — Wrap-up (30s)

**[ACTION]** Поверни на README header.

**[SAY]**
> "Підсумовуючи — це продакшн-готовий бот, який реально замінює людину. 8 commits, 77 тестів, повна документація. Що для мене особисто було важливим у цьому проекті — це Context7-first підхід до залежностей. Не писати з пам'яті, а перевіряти проти живої документації. APScheduler 4 і gspread v6 — два кейси, де це вберегло від реальних багів. Якщо тобі цікаво обговорити архітектурні рішення чи будь-який конкретний момент — пиши, я завжди радий поспілкуватися. Дякую за увагу."

**[ACTION]** Stop recording.

---

## Script (5:30 хв) — EN version (compressed)

Якщо EN — використай той самий каркас, але:
- Скороти intro до 20s
- Об'єднай "Architecture deep-dive" + "WOW features" в один блок (90s замість 150s)
- Кінцівка — 20s: "If you want to dive deeper into any decision, my contact is in the README. Thanks for watching."

Не намагайся перекладати дослівно — переписуй у природний англійський flow. Recruiter цінує впевненість і концептуальну ясність, не граматичну ідеальність.

---

## Post-recording checklist

1. **Перегляд** — Loom Editor → передивись на 1.25× speed. Шукай:
   - "Угу" / "ееее" пасажі → можна обрізати Loom-овою кнопкою Trim.
   - Місця, де ти plumbing-ом возишся (chunky window switch) → Trim 0.5s.
   - Чи звук рівний — Loom має noise suppression у Settings.
2. **Title** — "Booking Bot — Telegram-based SMB scheduling automation (Python / aiogram / APScheduler / AI)"
3. **Description** — паста з README hero block + посилання на GitHub.
4. **Thumbnail** — Loom Editor → Custom Thumbnail → screenshot з Mermaid діаграмою (якщо EN audience) або з voice-confirm screen (UA audience).
5. **Privacy** — Public link (з Loom URL), НЕ "Only invited people". Інакше recruiter не зможе відкрити.
6. **Comments** — Enabled (для engagement signal).
7. **Captions** — Loom auto-generates → перевір 3-4 ключових технічних терміни (APScheduler, Whisper, freebusy), виправ якщо невірно.

## Linking from README.md

Після завантаження додай у README прямо під hero block:

```markdown
## 🎥 Watch the 6-minute walkthrough

[![Booking Bot walkthrough on Loom](docs/screenshots/loom-thumbnail.png)](https://www.loom.com/share/<your-id>)
```

Це створить кликабельну thumbnail у README, яка веде на Loom. Save thumbnail як `docs/screenshots/loom-thumbnail.png` (одночасний screenshot з Loom editor → Save as image).

---

## Чого НЕ робити

- ❌ Не показуй живі credentials у Sheets / .env / `secrets/credentials.json` — пройдись pre-recording по екранах, переконайся, що нічого чутливого не видно.
- ❌ Не вмикай нотифікації Telegram / Slack / Email на час запису — попадуть на відео.
- ❌ Не читай скрипт дослівно — recruiter відразу почує. Краще запам'ятай головні тези і говори природно.
- ❌ Не записуй за 1 take, якщо нервуєш — Loom дозволяє paste pieces; запиши по секціях, склей через Loom Editor.
- ❌ Не залишай порожні паузи довше 2 секунд — обрізай у Editor.
