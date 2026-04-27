# vpn-bot-stars-hiddify

Telegram-first VPN subscription backend built around **payment -> provisioning -> delivery** as one coherent operator flow.

## Why this project exists

VPN subscription bots often break at the seams: payment is handled in one place, provisioning in another, and client onboarding becomes a support burden after the sale.

This repository is structured as a practical backend for that handoff. It combines Telegram bot flows, Hiddify provisioning, user profile delivery, and reminder logic in one service so the path from purchase to usable configuration stays short and predictable.

## What it does

The current implementation is centered around a FastAPI application that:

- receives Telegram webhook updates;
- exposes plan and purchase flows;
- provisions access through Hiddify-related integration paths;
- stores user and order state in SQLite;
- delivers subscription URLs, Hiddify deeplinks, and QR-based onboarding data;
- keeps Russian-language bot guidance close to the actual operational flow;
- runs reminder logic for expiring access.

## Key capabilities

- **Telegram webhook backend** with explicit secret-based webhook validation
- **Plan configuration from environment** rather than hardcoded pricing logic in multiple places
- **Provisioning fallbacks** via panel API, external bridge, or command-based integration depending on deployment shape
- **Profile delivery** in multiple formats: subscription URL, Hiddify deeplink, and QR where available
- **Built-in guide content** for onboarding users across mobile and desktop clients
- **Expiry reminders and suspension-oriented scheduling** driven by cron-like configuration

## Architecture overview

The repository is intentionally simple and direct.

### Runtime shape

- **Application entrypoint:** `app/main.py`
- **HTTP framework:** FastAPI
- **HTTP client:** `httpx`
- **Storage:** SQLite
- **Scheduling:** APScheduler (optional import path, enabled by environment)
- **Configuration:** `.env` / `.env.example`

### Integration boundaries

- **Telegram Bot API** for updates, messaging, invoices, and profile delivery
- **Hiddify panel / bridge / provision command** for access creation and subscription management
- **Local SQLite state** for users, orders, and reminder markers

### Current design trade-off

Most of the operational logic lives in `app/main.py`. That keeps the deployment footprint small and the flow easy to trace, but it also makes the file load-bearing. The repository currently favors directness and operational continuity over an early multi-module rewrite.

## Technical highlights

- Startup fails fast when required secrets such as `TELEGRAM_BOT_TOKEN` or `TELEGRAM_WEBHOOK_SECRET` are missing
- Provisioning is treated as a guarded path, not as a best-effort side effect
- User-facing copy is kept close to the runtime behavior, which helps avoid drift between docs and bot output
- Reminder behavior is configurable through environment variables rather than buried in code-only constants
- The data model is intentionally narrow: users, orders, and reminder markers cover the main operational state

## Repository structure

```text
vpn-bot-stars-hiddify/
  app/
    main.py
  .env.example
  requirements.txt
  AGENTS.md
  README.md
```

## Quick start

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Run locally:

```bash
uvicorn app.main:app --reload --port 8000
```

## Configuration

Environment variables define the runtime behavior.

Notable settings include:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_WEBHOOK_SECRET`
- `HIDDIFY_BASE_URL`
- `HIDDIFY_API_KEY`
- `HIDDIFY_BRIDGE_URL`
- `HIDDIFY_BRIDGE_TOKEN`
- `HIDDIFY_PROVISION_CMD`
- `PRICING_PLANS_JSON`
- `DB_PATH`
- `REMINDER_CRON`
- `REMINDER_DAYS`

See `.env.example` for the current baseline.

## Example workflow

1. A user opens the bot and selects a plan.
2. Telegram payment flow completes.
3. The backend provisions or refreshes access through the configured Hiddify integration path.
4. The bot stores local state in SQLite.
5. The user receives onboarding-ready profile data: subscription URL, Hiddify deeplink, and optional QR.
6. Reminder logic later checks expiry windows and notifies users according to the configured schedule.

## Operational notes

- The repo is **environment-driven** and depends on external Hiddify infrastructure to be genuinely useful
- Russian UX copy is the default user-facing language in the current codebase
- The provisioning and billing path is load-bearing and should be changed carefully
- There is no documented repo-wide lint or typecheck command in the current repository instructions

## Constraints and trade-offs

- The application is compact, but that compactness makes `app/main.py` central and easy to destabilize
- SQLite is appropriate for a small self-hosted workflow, but it is still a local file database with obvious operational limits
- Provisioning behavior depends on external systems and credentials, so this repository is not a standalone demo without deployment context
- The repo is optimized around getting a working operator flow, not around presenting a fully abstracted library

## Where this repo fits in a portfolio

This project is a good example of **applied backend engineering around real delivery flow boundaries**:

- external API integration
- webhook handling
- stateful user lifecycle logic
- operator-friendly onboarding output
- configuration-heavy deployment behavior

## License

See `LICENSE`.
