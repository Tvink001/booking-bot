# Demo GIF + WOW Screenshots — Capture Guide

Цей файл — крок-за-кроком інструкція для запису 4 артефактів, на які посилається `README.md` і `docs/architecture.md`. Артефакти кладеш у цей же каталог (`docs/screenshots/`) під точними іменами файлів зі списку нижче. Поки їх немає, в README будуть broken-image-іконки на GitHub.

## Що треба записати

| Файл | Що це | Розмір target |
|---|---|---|
| `demo.gif` | 30-секундний end-to-end booking flow з voice input | ≤5 MB (GitHub автоматично рендерить inline до цього розміру) |
| `wow1-calendar-sync.png` | Slot picker «до» і «після» блоку у Calendar | <500 KB |
| `wow2-vip-dm.png` | VIP DM, який отримав клієнт | <500 KB |
| `wow3-voice.png` | "Распознано: {name}" confirm step | <500 KB |

## Рекомендовані інструменти (Windows)

- **Для GIF:** [ScreenToGif](https://www.screentogif.com/) — безкоштовно, native, можна обрізати, ставити FPS, оптимізувати розмір.
- **Для PNG:** `Win+Shift+S` (Snipping Tool) → rectangle → Ctrl+V у Paint → Save as PNG. Або [Greenshot](https://getgreenshot.org/) для швидших workflows.
- **Для compress PNG після:** [TinyPNG](https://tinypng.com/) — drag-and-drop, lossless ~70% reduction.

## Pre-flight (зроби раз перед усім записом)

1. **Розмір вікна Telegram Desktop** — 400×700 px приблизно (вертикальний phone-like). Це робить GIF-и читабельними у README, не розтягнутими.
2. **Прибери всі особисті чати** у Telegram — щоб у GIF не потрапили нічиї імена/повідомлення. Найкраще — використовуй другий Telegram акаунт (Telegram Web в incognito-вкладці) суто для демо.
3. **Очисти Sheets** від тестових записів — щоб slot picker не був порожнім через минулі booking-и. Або — створи окремий "demo" service у `services` tab з порожнім розкладом.
4. **Перевір що bot запущений** локально: `$env:MODE="polling"; python -m bot.main` — у логах має бути "Polling started" + "APScheduler started".
5. **Master.work_days** включає сьогоднішній день weekday — інакше date picker не покаже сьогодні-завтра.

---

## 1. `demo.gif` — full booking flow (30s)

**Що показуємо:** від `/start` до success message через voice input.

### Послідовність (one take, ~30 секунд)

| Час | Дія | Результат |
|---|---|---|
| 0:00 | Натиснути `/start` | Бачимо main menu — 3 кнопки |
| 0:02 | Натиснути 📅 **Записаться** | Service picker |
| 0:04 | Натиснути будь-який service | Master picker |
| 0:06 | Натиснути будь-якого master | Date grid (14 днів) |
| 0:08 | Натиснути на завтрашню дату | Slot picker |
| 0:10 | Натиснути будь-який вільний slot | Name prompt з кнопкою 🎤 |
| 0:12 | Натиснути **🎤 Голосом** | "🎤 Запишите голосовое сообщение…" |
| 0:14 | Записати голосове "Артем" (~2 сек) | "Распознано: Артем … Подтвердить / Редактировать" |
| 0:18 | Натиснути ✅ **Подтвердить** | "Имя: Артем" + phone prompt |
| 0:20 | Натиснути 📱 **Поделиться контактом** + apple-confirm | "Принято." + confirmation screen |
| 0:24 | Натиснути ✅ **Подтвердить** на confirm screen | "✅ Запись создана!" success message |
| 0:28 | Stop recording | — |

### ScreenToGif settings

- **FPS:** 12 (балaнс smoothness/size)
- **Recording area:** обведи лише вікно Telegram, не весь екран
- **Editor → Reduce frame count → "Skip every other frame"** якщо файл >5 MB
- **Editor → Save → "Save as GIF (legacy)"** з quality 80%

Якщо отриманий GIF >5 MB:
- Зменши window до ~350×600 перед записом
- Зменши FPS до 10
- Обріж edges (Editor → Crop)

---

## 2. `wow1-calendar-sync.png` — Calendar blocks excluded

**Що показуємо:** slot picker, де частина слотів зникла через manually-blocked time у master's Calendar.

### Pre-setup

1. Відкрий master's Google Calendar (той самий gmail, що ділиться зі service-account).
2. На завтра створи подію **"Lunch"** з 12:00–13:00.
3. Зачекай ~5 секунд, щоб Calendar API проіндексував.

### Capture

1. У Telegram: `/start` → 📅 Записаться → service → master → завтрашня дата.
2. Дочекайся slot picker.
3. `Win+Shift+S` → обведи slot picker.
4. **Перевір:** у "До обіду" блоці немає `12:00` і `12:30` (40-min service займає обидва) або немає `12:00` (30-min service).
5. Save як `wow1-calendar-sync.png`.

### Опційно — composite "до/після"

Якщо хочеш яскраво продемонструвати: зроби 2 screenshot-и (один з блоком, один без — спочатку видали Lunch у Calendar, зачекай 65 секунд для cache TTL expire, потім перезайди в picker і знов capture), складеш side-by-side через Paint або Photopea.

### Cleanup

Видали "Lunch" подію з Calendar після зйомки.

---

## 3. `wow2-vip-dm.png` — VIP promo DM

**Що показуємо:** DM від бота — "⭐ {name}, вы наш VIP-клиент…"

### Pre-setup

1. Відкрий tab `_vip_sent` — **видали** свій рядок (якщо є).
2. Відкрий tab `bookings` — переконайся, що у тебе є **5 рядків** зі своїм `client_telegram_id` + status `completed`. Якщо ні — виправ status у column I.
3. Переконайся, що є хоча б 1 рядок з status `confirmed` і datetime_start у наступні 7 днів для твого id.

### Capture

1. Тимчасово додай `/run_vip` назад у admin.py — або:
2. Простіше: змусь cron спрацювати через зменшення часу. Замість того — просто розбуди cron вручну:
   - У Python REPL з активним env: `python -c "import asyncio; from bot.handlers.vip import check_vip_promos, set_runtime; from aiogram import Bot; from bot.config import settings; from bot.services.sheets import SheetsService; bot = Bot(settings.bot_token.get_secret_value()); set_runtime(bot, SheetsService()); asyncio.run(check_vip_promos())"`
3. Через секунд 2–3 у Telegram прийде DM `⭐ Артем, вы наш VIP-клиент…`
4. `Win+Shift+S` → обведи це DM повідомлення + 2-3 повідомлення вище (для контексту).
5. Save як `wow2-vip-dm.png`.

### Cleanup

- Видали свій рядок з `_vip_sent` (інакше повторно не отримаєш для наступних тестів).

---

## 4. `wow3-voice.png` — voice transcription confirm

**Що показуємо:** "Распознано: {name}" screen з кнопками ✅ / ✏️.

### Capture

1. У Telegram: `/start` → 📅 Записаться → service → master → date → slot.
2. На name prompt — натисни **🎤 Голосом**.
3. Запиши голосове повідомлення з ім'ям (українським для більшого WOW: "Олександр", "Богдана").
4. Дочекайся "Распознано: Олександр … Подтвердить / Редактировать".
5. **Перш ніж натиснути будь-що:** `Win+Shift+S` → обведи це повідомлення + попереднє ("🎤 Запишите…" + voice bubble + результат).
6. Save як `wow3-voice.png`.

### Quality check

- Текст у screenshot читабельний при 100% zoom.
- ✅ / ✏️ кнопки видно повністю.
- Voice bubble (попереднє повідомлення) видно — це показує, що bot обробив live voice.

---

## Після всіх 4 файлів

1. Перевір, що файли у каталозі:
   ```
   docs/screenshots/
     demo.gif
     wow1-calendar-sync.png
     wow2-vip-dm.png
     wow3-voice.png
     README.md  (цей файл)
   ```
2. Commit:
   ```powershell
   git add docs/screenshots/
   git commit -m "Add demo GIF + 3 WOW screenshots"
   git push
   ```
3. Відкрий repo на GitHub → перевір, що:
   - У `README.md` GIF грає inline.
   - 3 screenshots видно в WOW таблиці (не broken-image-іконки).
   - Mermaid діаграма рендериться.

Якщо GIF >5 MB і GitHub його обрізає → передивись pre-flight крок 1 (зменши window) або переробі через ScreenToGif з нижчим FPS.
