# `secrets/` — куди класти Google Service Account JSON

Ця папка містить лише один файл: `credentials.json` — JSON-ключ Google
сервіс-аккаунта, який бот використовує для доступу до Google Sheets і
Google Calendar.

## Що сюди покласти

Один файл: **`secrets/credentials.json`**.

Це JSON, який Google Cloud Console згенерував і запропонував завантажити,
коли ти створював ключ для сервіс-аккаунта (Service Accounts → Keys → Add Key
→ Create new key → JSON). Зміст виглядає приблизно так:

JSON містить такі поля (значення замінено описом — у реальному файлі будуть конкретні значення від Google):

| Поле | Що це |
|---|---|
| `type` | завжди `"service_account"` |
| `project_id` | ID Google Cloud-проєкту, де створено аккаунт |
| `private_key_id` | ID приватного ключа |
| `private_key` | сам приватний ключ у PEM-форматі — це **секрет**, не показуй нікому |
| `client_email` | email сервіс-аккаунта виду `<name>@<project>.iam.gserviceaccount.com` — саме цю адресу шарити з Sheet і Calendar |
| `client_id` | числовий ID клієнта |
| `auth_uri` / `token_uri` | стандартні OAuth2 endpoint`и Google |

**Не редагуй цей файл.** Скопіюй як є з машини, де його завантажив, у цю
папку, перейменуй у `credentials.json`, якщо назва інша.

## Що зробити з `client_email` із JSON

Адреса виду `<щось>@<project>.iam.gserviceaccount.com` — це email сервіс-
аккаунта. **Цю адресу треба видати як редактора (Editor):**

1. У Google Sheets-таблиці бота — Share → додати цей email → роль Editor
2. У Google Calendar кожного мастера — Settings → Share with specific people
   → додати цей email → роль "Make changes to events"

Без цього бот не зможе нічого ні писати, ні читати — отримаєш 403 Forbidden.

## Чому файл не в Git

`secrets/credentials.json` містить `private_key`, який = доступ до твоїх
Google API. Якщо потрапить у публічний репо — Google автоматично відкличе
ключ протягом кількох хвилин і завалить тебе попередженнями. `.gitignore`
у корені виключає весь вміст `secrets/` крім цього README.

## Як подається у код

`bot/config.py` через pydantic-settings читає змінну `GOOGLE_SERVICE_ACCOUNT_PATH`
із `.env`. За замовчуванням вона дорівнює `./secrets/credentials.json`.
`bot/services/sheets.py` і `bot/services/calendar.py` ініціалізують
клієнти через `service_account.Credentials.from_service_account_file(path, scopes=[...])`.

## На Railway

`credentials.json` НЕ копіюється у Docker-образ. Завантажуєш як Railway
Secret File з mount-point `/app/secrets/credentials.json` (це шлях
всередині контейнера). Прод-значення `GOOGLE_SERVICE_ACCOUNT_PATH` у Railway
Variables виставляєш на `/app/secrets/credentials.json` — і код далі
не помічає різниці між локалкою та продом.
