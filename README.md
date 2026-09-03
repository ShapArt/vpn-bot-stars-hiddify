# SH4PART VPN Bot

**Telegram Stars → subscription provisioning → profile delivery → renewal reminders.**

A small FastAPI service behind a Telegram bot. It keeps payment/order state in SQLite, provisions or extends access through a configured Hiddify integration and returns the subscription data the user needs to connect.

This repository is about the backend path after a person presses **Buy**, not about building a generic Telegram framework.

## Flow

```text
Telegram user
     │
     ▼
choose plan
     │
     ▼
Telegram Stars invoice
     │
     ▼
pre-checkout / successful payment
     │
     ▼
order + user state in SQLite
     │
     ▼
Hiddify provisioning
     │
     ├── panel/API path
     ├── bridge path
     └── external provision command
     │
     ▼
subscription URL / deeplink / QR
     │
     ▼
expiry reminders / renewal
```

## What the service does

- receives Telegram updates through `POST /telegram/webhook`;
- validates the Telegram webhook secret;
- exposes configurable subscription plans from `PRICING_PLANS_JSON`;
- handles Telegram Stars checkout events;
- stores users, orders and sent-reminder markers in SQLite;
- provisions access through the configured Hiddify path;
- returns subscription links and onboarding data to the user;
- can generate QR output when the optional QR dependency is available;
- schedules expiry reminders with APScheduler;
- keeps the user guide and platform-specific connection links close to the runtime flow.

## Runtime

The application intentionally lives mostly in [`app/main.py`](app/main.py). It is a compact service, so the complete payment-to-provisioning path can be traced without jumping through a large framework hierarchy.

That is also the main trade-off: the file is load-bearing. If the service grew into a larger billing platform, splitting Telegram handlers, provisioning and persistence into separate modules would be the obvious next step.

## Data model

SQLite stores three small groups of state:

- `users` — Telegram identity, subscription URL/display name, expiry and language;
- `orders` — plan, payment payload/amount/currency/status and creation time;
- `reminders_sent` — idempotency markers for expiry notifications.

WAL mode, indexes and a busy timeout are enabled in the local database setup.

## Provisioning

The deployment can be wired to Hiddify in several ways depending on the environment:

1. direct panel/API access;
2. an external bridge service;
3. a configured provisioning command.

The choice is controlled through environment variables rather than hard-coded into the Telegram handlers.

Relevant settings include:

```text
HIDDIFY_BASE_URL
HIDDIFY_API_KEY
HIDDIFY_BRIDGE_URL
HIDDIFY_BRIDGE_TOKEN
HIDDIFY_PROVISION_CMD
SUB_LINK_DOMAIN
```

## Security boundaries

The repository expects secrets to come from the environment, not from source code.

At minimum a deployment needs:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_WEBHOOK_SECRET
```

Other credentials such as the Hiddify API key/bridge token are also environment-driven. `.env.example` contains the supported configuration names without real secrets.

The webhook endpoint checks the Telegram webhook secret before handling an update. Payment confirmation and provisioning are separate stages; a chat command by itself does not become subscription state.

## Configuration

Copy `.env.example` and fill in the deployment-specific values.

```bash
cp .env.example .env
```

The main groups are:

| Group | Variables |
|---|---|
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` |
| Plans | `PRICING_PLANS_JSON` |
| Hiddify | `HIDDIFY_BASE_URL`, `HIDDIFY_API_KEY`, bridge/command settings |
| Storage | `DB_PATH` |
| Reminders | `REMINDER_CRON`, `REMINDER_DAYS` |
| Support/branding | `SUPPORT_TG`, `SUPPORT_EMAIL`, `BRAND_SITE`, `TG_CHANNEL` |

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in the required Telegram values, then start the service:

```bash
uvicorn app.main:app --reload --port 8000
```

Telegram must be able to reach the configured webhook URL for the real bot flow. Local startup alone is enough for code/debug work but not for receiving Telegram updates from the public API.

## Stack

`Python` · `FastAPI` · `httpx` · `SQLite` · `Telegram Bot API` · `Telegram Stars` · `Hiddify` · `APScheduler` · `qrcode`

## Repository map

```text
app/main.py       application, Telegram flow, DB and provisioning logic
.env.example      deployment configuration template
requirements.txt  Python dependencies
CHANGELOG.md      project changes
```

## Current scope

This is a small self-hosted service, not a full billing system. SQLite and a compact single-service architecture are deliberate for that scale. The project focuses on making the path from **payment** to **usable access** traceable and configurable.

## По-русски

Это backend Telegram-бота для выдачи VPN-подписки: пользователь выбирает тариф, оплачивает его Telegram Stars, сервис сохраняет заказ, создаёт/продлевает доступ через Hiddify и возвращает ссылку/данные для подключения. Отдельно работают напоминания об окончании подписки.

Самая важная часть проекта — стык нескольких состояний: Telegram-платёж, локальная БД, внешний provisioning и фактическая выдача доступа пользователю.

## License

See [LICENSE](LICENSE).
