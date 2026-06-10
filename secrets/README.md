# `secrets/` — Google Service Account JSON

This folder holds a single file: `credentials.json` — the Google service-account
JSON the bot uses to talk to Google Sheets and Google Calendar.

## What goes here

One file: **`secrets/credentials.json`**.

This is the JSON Google Cloud Console offers for download when you create a key
for the service account (Service Accounts → Keys → Add Key → Create new key →
JSON). Fields inside:

| Field | What it is |
|---|---|
| `type` | always `"service_account"` |
| `project_id` | the Google Cloud project the account belongs to |
| `private_key_id` | id of the private key |
| `private_key` | the private key in PEM — **this is the secret**, do not share |
| `client_email` | service-account email, looks like `<name>@<project>.iam.gserviceaccount.com` — this is the address you share with Sheet and Calendar |
| `client_id` | numeric client id |
| `auth_uri` / `token_uri` | Google's standard OAuth2 endpoints |

**Don't edit the file.** Copy it as-is from the machine you downloaded it on,
rename to `credentials.json` if needed.

## What to do with `client_email`

The `<something>@<project>.iam.gserviceaccount.com` address is the service
account's email. **You need to grant it Editor on:**

1. The bot's Google Sheet — Share → add the email → role: Editor
2. Each master's Google Calendar — Settings → Share with specific people →
   add the email → role: "Make changes to events"

Without this, the bot can neither read nor write — you'll get 403 Forbidden.

## Why the file isn't in git

`secrets/credentials.json` contains a `private_key` that = access to your
Google APIs. If it lands in a public repo, Google auto-revokes the key within
minutes and floods you with alerts. The root `.gitignore` excludes everything
in `secrets/` except this README.

## How the code finds it

`bot/config.py` (pydantic-settings) reads `GOOGLE_SERVICE_ACCOUNT_PATH` from
`.env`. The default is `./secrets/credentials.json`. `bot/services/sheets.py`
and `bot/services/calendar.py` instantiate clients via
`service_account.Credentials.from_service_account_file(path, scopes=[...])`.

## On Railway

`credentials.json` is NOT baked into the Docker image. Upload it as a Railway
Secret File with mount-point `/app/secrets/credentials.json` (the path inside
the container). Set `GOOGLE_SERVICE_ACCOUNT_PATH` in Railway Variables to
`/app/secrets/credentials.json` — and the code can't tell prod from local.
