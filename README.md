# vpn-bot-stars-hiddify

Telegram-first VPN subscription backend built around a simple but operationally important promise: **a user pays, receives access, imports the profile, and starts using the service without falling into a support gap between billing and provisioning**.

## Executive summary

This project sits at the boundary between product delivery and backend operations. The core problem is not “how to send messages from a bot.” The real problem is stitching together a fragile multi-step flow — payment, provisioning, persistence, onboarding, and reminder handling — into something predictable enough to run as a small operator-facing service.

The repository approaches that problem with a compact FastAPI application, environment-driven configuration, Telegram Bot API integration, Hiddify-oriented provisioning paths, and local SQLite state.

## Why this project exists

Many subscription-style bots fail at the handoff points:

- payment succeeds but access is not provisioned cleanly;
- access exists but the user is not onboarded properly;
- subscription links are delivered, but the import experience is unclear;
- expiry and renewal handling become manual support work.

This project exists to compress those failure points into one coherent backend flow.

## What the system does

The current implementation is centered around a FastAPI application that:

- receives Telegram webhook updates;
- exposes plan and purchase flows;
- handles payment-related bot behavior;
- provisions access through Hiddify-related integration paths;
- stores user and order state in SQLite;
- delivers subscription URLs, Hiddify deeplinks, and QR-based onboarding data;
- keeps Russian-language guide content close to the actual user journey;
- schedules reminder logic for expiring access.

## Product and engineering lens

This repository is interesting because it combines **user lifecycle logic** with **ops-facing backend behavior**.

The code is not only about chat UX. It also has to answer questions such as:

- where subscription state lives;
- how payment completion maps to provisioning;
- what happens when one integration path is unavailable;
- how onboarding output is delivered in a usable format;
- how expiry reminders stay configurable without turning into hardcoded behavior.

## Architecture overview

### Runtime shape

- **Application entrypoint:** `app/main.py`
- **HTTP framework:** FastAPI
- **HTTP client:** `httpx`
- **Persistence:** SQLite
- **Scheduling:** APScheduler (optional import path)
- **Configuration:** environment variables via `.env` / `.env.example`

### External boundaries

- **Telegram Bot API** for updates, messaging, invoices, and delivery
- **Hiddify panel / bridge / provision command** for provisioning and subscription handling
- **Local file-backed database** for user, order, and reminder state

### Internal flow model

A simplified runtime flow looks like this:

1. Telegram delivers an update.
2. The backend validates and routes the webhook payload.
3. The user enters or completes a plan/payment path.
4. The provisioning layer resolves the configured Hiddify integration path.
5. Local state is persisted.
6. The bot returns onboarding-ready artifacts to the user.
7. Scheduler logic later handles reminder windows and expiry-related follow-up.

## Key capabilities

- **Webhook-driven bot backend** with explicit secret-based validation
- **Environment-driven plan configuration** instead of duplicating tariff logic across the codebase
- **Provisioning fallback paths** via panel API, bridge service, or command-based integration depending on deployment shape
- **Multi-format onboarding delivery** through subscription URL, Hiddify deeplink, and QR output when available
- **Guide content kept near runtime logic**, reducing drift between documentation and real bot behavior
- **Reminder scheduling** configurable through cron-like environment settings

## Technical decisions worth highlighting

### 1. Compact single-service design

Most of the operational behavior lives in `app/main.py`.

That is a conscious trade-off. It reduces file sprawl and keeps the payment-to-provisioning path easy to trace, but it also makes the file load-bearing. For a small self-hosted service, this is a pragmatic choice; for a larger deployment, modularization would become the next structural step.

### 2. Narrow data model

The repository keeps state focused on the operational minimum: users, orders, and reminder markers.

That is useful because the system is not trying to become a full billing platform. It is trying to keep the delivery flow reliable.

### 3. Configuration over branching sprawl

The runtime behavior is environment-driven. This is particularly important in a project where the actual deployment shape can vary depending on which Hiddify integration path is available.

### 4. Delivery-oriented output

The repository does not stop at “provision access.” It explicitly treats deeplinks, subscription URLs, and QR output as part of the backend responsibility because onboarding failure is still delivery failure.

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

## Local setup

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

Important runtime settings include:

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

## Example usage flow

1. A user opens the bot.
2. The bot presents available plans.
3. The Telegram payment flow completes.
4. The backend provisions or refreshes access through the configured Hiddify integration path.
5. The application persists user/order state.
6. The bot returns onboarding-ready artifacts to the user.
7. Reminder logic checks future expiry windows and sends notifications according to schedule.

## Operational considerations

- The service is **environment-driven** and depends on external Hiddify infrastructure to be genuinely useful
- Russian UX copy is the default user-facing language in the current implementation
- The payment and provisioning path is load-bearing and should be changed carefully
- There is no documented repo-wide lint or typecheck command in the current instructions

## Constraints and trade-offs

- The compact application structure makes the runtime path easy to follow, but also makes `app/main.py` central and easy to destabilize
- SQLite is a reasonable fit for a small self-hosted operator workflow, but it remains a local file-backed database with obvious scaling and operational trade-offs
- Provisioning behavior depends on external systems and credentials, so the repository is not a standalone demo in isolation
- The project is intentionally delivery-oriented rather than over-abstracted into a framework or library

## Why this repo is strong in a portfolio

This is a good example of **applied backend engineering around real delivery boundaries**:

- external API integration
- webhook handling
- stateful lifecycle logic
- onboarding-aware output design
- configuration-heavy deployment behavior
- small-service pragmatism

It shows the kind of engineering work that matters in real small systems: not theoretical scale, but correctly joining the steps where users and operators usually get hurt.

## Good next additions for portfolio depth

- a simple architecture diagram
- one end-to-end payment/provisioning flow diagram
- a screenshot set for the bot onboarding path
- one short section describing failure handling for provisioning fallbacks

## License

See `LICENSE`.
