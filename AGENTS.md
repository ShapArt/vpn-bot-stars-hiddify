# AGENTS.md

Drop-in instructions for coding agents working in this repo. Read this file before every task.

Working code only. Verify before claiming success.

## 0. Non-negotiables

1. No fluff. Start with the action or answer.
2. Do not agree with a false premise. Say what is wrong, then fix the real problem.
3. Never fabricate paths, env vars, API behavior, or test results.
4. Touch only what the task requires. No drive-by cleanup.
5. Secrets stay out of the repo. Never hardcode tokens, webhook secrets, API keys, admin UUIDs, or production URLs.
6. Do not weaken safety around Telegram payments, webhook auth, or Hiddify provisioning without an explicit request.
7. Keep user-facing bot text in Russian unless the task explicitly changes locale behavior.

## 1. How to work in this repo

State a short plan before editing.
Read the files you will change and the handlers that call them.
Match existing patterns in the repo instead of inventing a new architecture.
If the task is ambiguous in a way that changes billing, provisioning, or access control behavior, ask instead of guessing.

## 2. Project context

### Stack
- Python 3.11+
- FastAPI
- Telegram Bot API
- httpx
- SQLite
- APScheduler
- Hiddify panel API integration

### Commands
- Install: `python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`
- Run locally: `uvicorn app.main:app --reload --port 8000`
- No stable repo-wide lint/typecheck command is documented here. Do not invent one.

### Layout
- Main app entry: `app/main.py`
- Source of truth for runtime behavior is the code, not the README.
- Env-driven configuration is loaded from `.env` / `.env.example`.

### Load-bearing areas
- `app/main.py` currently contains webhook handling, billing flow, Hiddify provisioning, DB access, guide text, reminders, and suspension logic in one place.
- Payment flow is load-bearing: invoice -> pre-checkout -> successful payment -> provisioning -> DB upsert -> profile delivery.
- Provisioning flow is load-bearing: `provision_subscription` -> fallback / bridge / panel API -> subscription link -> bot delivery.
- Webhook authentication via `TELEGRAM_WEBHOOK_SECRET` is load-bearing.

## 3. Repo-specific rules

- Read the full end-to-end path before changing payments, tariffs, reminders, subscription links, or provisioning.
- Do not silently rename env vars or change fallback semantics.
- Do not log sensitive values such as bot tokens, subscription URLs, API keys, or user payloads.
- Preserve backward compatibility for existing callback data unless the task explicitly allows a bot UI migration.
- If you change user-visible guide text, keep links official and avoid making up platform behavior.
- If you touch DB schema or `CREATE TABLE` statements, add migration logic or safe compatibility handling instead of breaking existing SQLite files.
- Avoid large refactors in `app/main.py` unless the task is specifically about restructuring. This file is already central and easy to destabilize.
- When changing reminder or suspension logic, verify UTC handling and expiry math.
- When changing subscription parsing or deeplink generation, test both `https://...` and `hiddify://import/...` flows.

## 4. Verification

Success means behavior is verified, not just coded.

For every non-trivial change:
1. Run the app locally if the change touches startup, env loading, webhook routing, or imports.
2. Exercise the narrowest possible path relevant to the change.
3. If there is no automated test for the area, describe the exact manual verification you performed.
4. Do not claim tests passed if you did not run them.

Good manual checks in this repo include:
- app starts with `uvicorn app.main:app --reload --port 8000`
- webhook route imports cleanly
- callback data still maps to the expected branch
- payment/provisioning changes preserve DB writes and bot responses

## 5. Simplicity rules

- Do not add abstractions for single-use code.
- Do not add configurability that was not requested.
- Do not split files just because you dislike the current shape.
- Prefer the smallest safe diff.

## 6. Forbidden

- Hardcoding secrets or production identifiers
- Rewriting large blocks of guide copy when the task is unrelated
- Changing Russian UX copy to English by default
- Bypassing webhook secret checks
- Changing payment, plan, or provisioning behavior without tracing the full flow first
- Claiming Hiddify or Telegram API behavior from memory when the code says otherwise

## 7. Project learnings

- For billing changes, trace the full path: callback -> invoice -> successful payment -> `provision_subscription` -> `DBI.upsert_user` -> user message.
- For provisioning changes, preserve the fallback path unless the task explicitly removes it.
- For expiry logic, check both DB `expires_at` values and panel-derived expiry data before changing calculations.
