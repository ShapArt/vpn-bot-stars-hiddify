from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Optional scheduler for reminders (kept optional & type-safe for Pylance)
try:
    from apscheduler.schedulers.asyncio import (
        AsyncIOScheduler,  # type: ignore[reportMissingImports]
    )
    from apscheduler.triggers.cron import (
        CronTrigger,  # type: ignore[reportMissingImports]
    )
except Exception:
    AsyncIOScheduler = None  # type: ignore[assignment]
    CronTrigger = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover
    from apscheduler.schedulers.asyncio import (
        AsyncIOScheduler as _SchedulerType,  # type: ignore
    )
else:
    _SchedulerType = Any  # fall back

# ---------- Logging ----------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)

# ---------- Optional QR ----------
try:
    import qrcode  # type: ignore
except Exception:
    qrcode = None

# ---------- Config ----------
load_dotenv(override=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()

BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Sh4pArt’s App").strip()
SERVER_LOCATION = os.getenv("SERVER_LOCATION", "Netherlands").strip()

HIDDIFY_BASE_URL = os.getenv("HIDDIFY_BASE_URL", "").rstrip("/")
SUB_LINK_DOMAIN = os.getenv("SUB_LINK_DOMAIN", HIDDIFY_BASE_URL).rstrip("/")

ADMIN_PROXY_PATH = os.getenv("ADMIN_PROXY_PATH", "").strip().strip("/")
USER_PROXY_PATH = os.getenv("USER_PROXY_PATH", "").strip().strip("/")
HIDDIFY_API_KEY = os.getenv("HIDDIFY_API_KEY", "").strip()  # admin UUID

# optional external bridge / cli (disabled by default)
HIDDIFY_BRIDGE_URL = os.getenv("HIDDIFY_BRIDGE_URL", "").rstrip("/")
HIDDIFY_BRIDGE_TOKEN = os.getenv("HIDDIFY_BRIDGE_TOKEN", "").strip()
HIDDIFY_PROVISION_CMD = os.getenv("HIDDIFY_PROVISION_CMD", "").strip()

TG_CHANNEL = os.getenv("TG_CHANNEL", "").strip()
SUPPORT_TG = os.getenv("SUPPORT_TG", "@ShapArt").strip()
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "sh4part@gmail.com").strip()
BOOSTY_URL = os.getenv("BOOSTY_URL", "").strip()
BRAND_SITE = os.getenv("BRAND_SITE", "").strip()

PRICING_PLANS_JSON = os.getenv("PRICING_PLANS_JSON", "[]")
DB_PATH = os.getenv("DB_PATH", "/opt/vpn-bot/vpn_bot.sqlite3")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# UI toggles
SHOW_PANEL_IN_MENU = os.getenv("SHOW_PANEL_IN_MENU", "1") in ("1", "true", "True")

# Admins / notify
ADMIN_PRESEED_USER_IDS = os.getenv("ADMIN_PRESEED_USER_IDS", "")
ADMIN_PRESEED_PLAN_JSON = os.getenv("ADMIN_PRESEED_PLAN_JSON", "")
ADMIN_NOTIFY_USER_IDS = os.getenv("ADMIN_NOTIFY_USER_IDS", ADMIN_PRESEED_USER_IDS)

# Reminders: by default only D-3 and D-0 (day of expiry)
REMINDER_CRON = os.getenv("REMINDER_CRON", "0 10 * * *")  # 10:00 UTC
try:
    REMINDER_DAYS = json.loads(os.getenv("REMINDER_DAYS", "[3,0]"))
except Exception:
    REMINDER_DAYS = [3, 0]

# Link/Name formatting
DISPLAY_PREFIX = os.getenv("DISPLAY_PREFIX", "tg-")
HIDDIFY_FORCE_LONG_SUB = os.getenv("HIDDIFY_FORCE_LONG_SUB", "1").lower() in (
    "1",
    "true",
    "yes",
)

if not TELEGRAM_BOT_TOKEN:
    raise SystemExit("Missing TELEGRAM_BOT_TOKEN")
if not TELEGRAM_WEBHOOK_SECRET:
    raise SystemExit("Missing TELEGRAM_WEBHOOK_SECRET")

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# ---------- Official links (used inside the in-bot Guide) ----------
GUIDE_LINKS: Dict[str, str] = {
    # Hiddify official
    "hiddify_play": "https://play.google.com/store/apps/details?id=app.hiddify.com",
    "hiddify_ios": "https://apps.apple.com/app/hiddify-proxy-vpn/id6596777532",
    "hiddify_app_releases": "https://github.com/hiddify/hiddify-app/releases",
    "hiddify_site": "https://hiddify.com/",
    "hiddify_url_scheme": "https://hiddify.com/app/URL-Scheme/",
    # Alternatives on iOS
    "shadowrocket": "https://apps.apple.com/app/shadowrocket/id932747118",
    "streisand": "https://apps.apple.com/app/streisand/id6450534064",
    "amnezia_ios": "https://apps.apple.com/app/amneziavpn/id1600529900",
    "amnezia_dl": "https://amnezia.org/downloads",
    # Help / platform docs
    "apple_region": "https://support.apple.com/118283",
    "google_play_protect": "https://support.google.com/googleplay/answer/2812853",
    "google_play_protect_dev": "https://developers.google.com/android/play-protect",
    "samsung_unknown": "https://www.samsung.com/ae/support/mobile-devices/how-to-enable-permission-to-install-apps-from-unknown-source-on-my-samsung-phone/",
    "ms_smartscreen": "https://learn.microsoft.com/en-us/windows/security/operating-system-security/virus-and-threat-protection/microsoft-defender-smartscreen/available-settings",
    # Telegram Stars
    "telegram_stars_blog": "https://telegram.org/blog/telegram-stars",
    "telegram_stars_api": "https://core.telegram.org/bots/payments-stars",
    "telegram_stars_core": "https://core.telegram.org/api/stars",
    "premium_bot": "https://t.me/PremiumBot",
}


# ---------- Plans ----------
@dataclass
class Plan:
    name: str
    days: int
    traffic_gb: int
    devices: int
    price: int  # XTR

    @property
    def plan_id(self) -> str:
        base = self.name.lower().strip().replace(" ", "-")
        return f"{base}-{self.days}d-{self.traffic_gb}g-{self.devices}dvc"


def parse_plans(s: str) -> List[Plan]:
    try:
        arr = json.loads(s)
        out = []
        for it in arr:
            out.append(
                Plan(
                    name=str(it["name"]),
                    days=int(it["days"]),
                    traffic_gb=int(it["traffic_gb"]),
                    devices=int(it["devices"]),
                    price=int(it["price"]),
                )
            )
        return out
    except Exception as e:
        logging.warning("Invalid PRICING_PLANS_JSON: %s", e)
        return []


_env_plans = parse_plans(PRICING_PLANS_JSON)
# enforce exactly two public tariffs as requested
PLANS: List[Plan] = (
    _env_plans[:2]
    if _env_plans
    else [Plan("Lite", 30, 50, 2, 100), Plan("Plus", 30, 200, 5, 150)]
)


# ---------- DB ----------
class DB:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._ensure()

    def _ensure(self):
        with sqlite3.connect(self.path) as c:
            c.execute("PRAGMA journal_mode=WAL;")
            c.execute("PRAGMA synchronous=NORMAL;")
            c.execute("PRAGMA busy_timeout=3000;")
            c.execute("PRAGMA cache_size=-2000;")
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS users(
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    sub_url TEXT,
                    display_name TEXT,
                    expires_at TEXT,
                    language TEXT
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS orders(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER,
                    plan_id TEXT,
                    payload TEXT,
                    amount INTEGER,
                    currency TEXT,
                    status TEXT,
                    created_at TEXT
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders_sent(
                    telegram_id INTEGER,
                    key TEXT,
                    sent_at TEXT,
                    PRIMARY KEY(telegram_id, key)
                )
                """
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_expires ON users(expires_at)"
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at)"
            )

    # users
    def upsert_user(
        self,
        telegram_id: int,
        username: Optional[str],
        sub_url: Optional[str],
        display_name: Optional[str],
        expires_at: Optional[str],
        language: Optional[str],
    ):
        with sqlite3.connect(self.path) as c:
            c.execute(
                """
                INSERT INTO users(telegram_id, username, sub_url, display_name, expires_at, language)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username=COALESCE(EXCLUDED.username, username),
                    sub_url=COALESCE(EXCLUDED.sub_url, sub_url),
                    display_name=COALESCE(EXCLUDED.display_name, display_name),
                    expires_at=COALESCE(EXCLUDED.expires_at, expires_at),
                    language=COALESCE(EXCLUDED.language, language)
                """,
                (telegram_id, username, sub_url, display_name, expires_at, language),
            )

    def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(self.path) as c:
            c.row_factory = sqlite3.Row
            r = c.execute(
                "SELECT * FROM users WHERE telegram_id=?", (telegram_id,)
            ).fetchone()
            return dict(r) if r else None

    def get_user_lang(self, telegram_id: int) -> Optional[str]:
        with sqlite3.connect(self.path) as c:
            r = c.execute(
                "SELECT language FROM users WHERE telegram_id=?", (telegram_id,)
            ).fetchone()
            return r[0] if r and r[0] else None

    def set_user_lang_if_empty(self, telegram_id: int, lang: str) -> str:
        cur = self.get_user_lang(telegram_id)
        if cur:
            return cur
        with sqlite3.connect(self.path) as c:
            c.execute(
                "INSERT INTO users(telegram_id, language) VALUES(?, ?) "
                "ON CONFLICT(telegram_id) DO UPDATE SET language=COALESCE(language, excluded.language)",
                (telegram_id, lang),
            )
        return lang

    def set_user_lang(self, telegram_id: int, lang: str):
        with sqlite3.connect(self.path) as c:
            c.execute(
                "INSERT INTO users(telegram_id, language) VALUES(?, ?) "
                "ON CONFLICT(telegram_id) DO UPDATE SET language=excluded.language",
                (telegram_id, lang),
            )

    def get_users_expiring_on(self, day_utc: datetime) -> List[Dict[str, Any]]:
        key = day_utc.date().isoformat()
        with sqlite3.connect(self.path) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                "SELECT * FROM users WHERE expires_at LIKE ? || '%'", (key,)
            ).fetchall()
            return [dict(r) for r in rows]

    # reminders
    def mark_reminder_sent(self, telegram_id: int, key: str):
        with sqlite3.connect(self.path) as c:
            c.execute(
                "INSERT OR IGNORE INTO reminders_sent(telegram_id, key, sent_at) VALUES(?,?,?)",
                (telegram_id, key, datetime.utcnow().isoformat()),
            )

    def reminder_was_sent(self, telegram_id: int, key: str) -> bool:
        with sqlite3.connect(self.path) as c:
            r = c.execute(
                "SELECT 1 FROM reminders_sent WHERE telegram_id=? AND key=?",
                (telegram_id, key),
            ).fetchone()
            return bool(r)

    # orders
    def create_order(
        self, telegram_id: int, plan_id: str, payload: str, amount: int, currency: str
    ) -> int:
        with sqlite3.connect(self.path) as c:
            cur = c.execute(
                """
                INSERT INTO orders(telegram_id, plan_id, payload, amount, currency, status, created_at)
                VALUES(?,?,?,?,?, 'pending', ?)
                """,
                (
                    telegram_id,
                    plan_id,
                    payload,
                    amount,
                    currency,
                    datetime.utcnow().isoformat(),
                ),
            )
            rid = cur.lastrowid
            if rid is None:
                raise RuntimeError("Failed to insert order: lastrowid is None")
            return int(rid)


DBI = DB(DB_PATH)

# ---------- HTTPX ----------
_tg_client: Optional[httpx.AsyncClient] = None


def _limits() -> httpx.Limits:
    return httpx.Limits(max_connections=60, max_keepalive_connections=30)


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(20.0)


async def tg_api(method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{API_BASE}/{method}"
    cli = _tg_client or httpx.AsyncClient(timeout=_timeout(), limits=_limits())
    created_here = cli is not _tg_client
    try:
        r = await cli.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data}")
        return data
    finally:
        if created_here:
            await cli.aclose()


async def tg_api_multipart(
    method: str, data: Dict[str, Any], files: Dict[str, Tuple[str, bytes, str]]
):
    url = f"{API_BASE}/{method}"
    cli = _tg_client or httpx.AsyncClient(timeout=_timeout(), limits=_limits())
    created_here = cli is not _tg_client
    try:
        r = await cli.post(url, data=data, files=files)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error: {data}")
        return data
    finally:
        if created_here:
            await cli.aclose()


async def notify_admins(text: str):
    ids = [s.strip() for s in (ADMIN_NOTIFY_USER_IDS or "").split(",") if s.strip()]
    for s in ids:
        try:
            await tg_api("sendMessage", {"chat_id": int(s), "text": text})
        except Exception:
            pass


# ---------- i18n (RU-only) ----------
def T(_lang: str, key: str, **kw) -> str:
    s = TEXTS_RU.get(key, key)
    try:
        return s.format(**kw)
    except Exception:
        return s


TEXTS_RU: Dict[str, str] = {
    # Свежие, незаезженные эмодзи: 🛰️ 🧬 🪪 🧭 🪄
    "welcome": "🛰️ Привет! Это *{brand}* — быстрый анти‑DPI VPN на базе Hiddify.\nСерверы: *{loc}*. Оплата — *звёздами (XTR)*.\n\nВыберите раздел ниже.",
    "card": "🧬 *Что вы получаете*\n• Узлы в {loc}\n• Импорт в Hiddify — deeplink/QR\n• Поддержка: {support_tg} • Почта: {support_email}",
    "choose": "Выберите раздел:",
    "plans_title": "🪄 *Тарифы*",
    "plan_line": "*{name}* — {days} дн.\nТрафик: {gb} ГБ • Устройств: {devices}\nЦена: *{price} XTR*",
    "pay_info": "Оплата звёздами (XTR) прямо в Telegram — мгновенная активация.",
    "plan_card": "✨ *{name}*\n• Срок: {days} дней\n• Трафик: {gb} ГБ\n• Устройства: до {devices}\n• Стоимость: *{price} XTR*",
    "links_empty": "Пока нет активных подписок. Откройте «Купить» и оформите тариф.",
    "account_block": (
        "🪪 *Профиль*\n\n"
        "SUB: {sub}\n"
        "Deeplink: {deeplink}\n"
        "{panel}\n\n"
        "📊 Трафик: {used} из {total} ({percent}%) — осталось {left}\n"
        "⏳ До конца подписки: {days_left}\n"
        "{extra}"
    ),
    "faq_hint": "Подсказки по протоколам:\n{tips}",
    "send_sub": "🔑 Пришлите вашу ссылку (https://… или hiddify://import/…). Я распознаю и сохраню.",
    "sub_saved": "✅ Ссылка привязана.\nSUB: {sub}\nDeeplink: {deeplink}\nОткройте deeplink в Hiddify.",
    "sub_bad": "Не получилось распознать. Пришлите полный https://… или hiddify://import/…",
    "paid_ok": "✅ *Оплата получена*. Доступ активирован!\n\nSUB: {sub}\nDeeplink: {deeplink}\nQR — в «Профиль».",
    "internal_err": "Произошла внутренняя ошибка. Попробуйте позже.",
    "admin_ok": "Готово.",
    "admin_err": "Команда не распознана или не хватает прав.",
    "panel_not_conf": "ℹ️ Операция недоступна: панель не настроена.",
    "regen_ok": "🔁 Профиль перегенерирован. Обновите конфигурацию в приложении.",
    "extend_hint": "➕ Продление/апгрейд: выберите тариф — срок добавится к текущей дате.",
    "guide_title": "📚 *Sh4pArt’s App — Гид*\n",
}


def render_plans_text(lang: str, plans: list) -> str:
    lines = [T(lang, "plans_title"), ""]
    for p in plans:
        lines.append(
            T(
                lang,
                "plan_line",
                name=p.name,
                days=p.days,
                gb=p.traffic_gb,
                devices=p.devices,
                price=p.price,
            )
        )
    return "\n".join(lines)


def render_plan_card(lang: str, p: Plan) -> str:
    return T(
        lang,
        "plan_card",
        name=p.name,
        days=p.days,
        gb=p.traffic_gb,
        devices=p.devices,
        price=p.price,
    )


# ---------- Guide content (FULL posts with links, RU-only) ----------
GUIDE_RU: Dict[str, str] = {
    "toc": (
        "🚀 *Sh4pArt’s App — быстрый анти‑DPI VPN*\n"
        "Коротко: 🇳🇱 узлы (Netherlands), импорт профиля в Hiddify по deeplink/QR, оплата звёздами XTR, честный подход к приватности.\n\n"
        f"*Помощь*: {SUPPORT_TG} • {SUPPORT_EMAIL}\n"
    ),
    "2": (
        "🟢 *Установка: Android (Hiddify Next + APK)*\n\n"
        "Коротко: ставим Hiddify из Google Play (если доступно) или APK из GitHub Releases. Импорт через deeplink/QR.\n\n"
        "Вариант A — Google Play (рекомендуем):\n"
        "• Страница Hiddify: {hiddify_play}\n"
        "• Дайте разрешение «VPN» при первом запуске.\n"
        "• Обновляйте через Play для авто‑обновлений.\n\n"
        "Вариант B — APK из GitHub Releases:\n"
        "• APK (официальный репозиторий): {hiddify_app_releases}\n"
        "• Если блокируется установка — включите «Install unknown apps» для нужного приложения (Samsung: {samsung_unknown}).\n"
        "• Держите Google Play Protect включённым: {google_play_protect} ({google_play_protect_dev}).\n\n"
        "Импорт профиля:\n"
        "• Нажмите на *hiddify://import/<SUB>* — клиент сам добавит подписку. Спецификация deeplink: {hiddify_url_scheme}\n"
        "• Или в Hiddify: ‘+’ → Add from clipboard / Scan QR.\n\n"
        "Мини‑FAQ:\n"
        "• «Deeplink не открывается» → Скопируйте https://…SUB… и добавьте через ‘+ → Add manually’.\n"
        "• «После импорта нет трафика» → Обновите подписку, смените протокол (Reality/Hysteria2/TUIC).\n"
        "• «Как сменить протокол» → Долгий тап по узлу → Edit/Protocol."
    ).format(**GUIDE_LINKS),
    "3": (
        "🍏 *Установка: iOS / iPadOS (регион и альтернативы)*\n\n"
        "Базовый путь: попробуйте официальный Hiddify в App Store: {hiddify_ios}\n"
        "Импортируйте *hiddify://import/<SUB>* или отсканируйте QR внутри приложения.\n\n"
        "Альтернативы (если Hiddify недоступен):\n"
        "• Shadowrocket (платный): {shadowrocket}\n"
        "• Streisand (поддерживает VLESS(Reality), Hysteria2, TUIC): {streisand}\n"
        "• AmneziaVPN (open‑source): {amnezia_ios} • Загрузки: {amnezia_dl}\n\n"
        "Смена региона App Store (если нужно): {apple_region}\n"
        "Импорт в совместимых клиентах: Add → Import from Clipboard / Scan QR — вставьте SUB‑ссылку.\n\n"
        "Лайфхак: сделайте ярлык iOS Shortcuts «Открыть URL» → hiddify://import/<SUB> — быстрый ре‑импорт."
    ).format(**GUIDE_LINKS),
    "4": (
        "🖥 *Установка: Windows / macOS / Linux / Android TV*\n\n"
        "ПК/ноут: скачайте Hiddify App/Next из официальных релизов: {hiddify_app_releases}\n"
        "Импорт: *hiddify://import/<SUB>* или Add from clipboard / Scan QR.\n"
        "macOS: если «Unidentified developer» — System Settings → Privacy & Security → *Open Anyway*.\n\n"
        "Android TV: ставьте Android APK из Releases (сайдлоад). Включите ‘Install unknown apps’ (см. {samsung_unknown}).\n\n"
        "Мини‑FAQ:\n"
        "• SmartScreen/антивирус ругается — типично для свежих билдов; ‘More info → Run anyway’ (см. {ms_smartscreen}).\n"
        "• Нет трафика после сна/перезагрузки — перезапустите VPN, обновите SUB, смените узел/протокол."
    ).format(**GUIDE_LINKS),
    "5": (
        "💳 *Оплата XTR (Telegram Stars) и активация*\n\n"
        "Оплачиваете звёзды XTR в боте — мгновенно получаете SUB + deeplink + QR.\n\n"
        "Как оплатить:\n"
        "1) В боте выберите тариф → Оплатить XTR → подтвердите покупку. Документация: {telegram_stars_api}\n"
        "2) Звёзды списываются из вашего баланса Telegram / {premium_bot}. Подробнее: {telegram_stars_blog} / {telegram_stars_core}\n"
        "3) После оплаты бот выдаёт: https://…/SUB, hiddify://import/<SUB> и QR.\n\n"
        "Если нужен Boosty — возможна ручная активация по договорённости."
    ).format(**GUIDE_LINKS),
    "6": (
        "🔗 *Мои ссылки / Профиль / Продление*\n\n"
        "Где взять свои ссылки: в боте → «🪪 Профиль»: SUB, deeplink, QR. Не делитесь публично.\n"
        "Продление и апгрейд: при оплате срок добавляется к текущей дате.\n\n"
        "Рекомендации по протоколам (начните с этого):\n"
        "• VLESS/Reality — универсально, устойчиво к блокировкам.\n"
        "• Hysteria2 — при агрессивном DPI/потерях.\n"
        "• TUIC — низкие задержки; если нестабильно — переключайтесь.\n\n"
        "Лайфхак: держите несколько узлов/протоколов активными — переключение занимает секунды."
    ),
    "7": (
        "🛠 *FAQ: установка, подключение, оплата, регион*\n\n"
        "Установка/импорт:\n"
        "• Deeplink не открывается → импорт через ‘+ → Add manually’. Спецификация: {hiddify_url_scheme}\n"
        "• APK блокируется → включите Install unknown apps (Samsung: {samsung_unknown}); Play Protect включён: {google_play_protect}\n\n"
        "Подключение/стабильность:\n"
        "• Нет трафика → обновите SUB, смените узел/протокол (Reality → Hysteria2/TUIC).\n"
        "• После сна/перезагрузки нет интернета → выключите/включите VPN, перезапустите клиент.\n\n"
        "Оплата/активация:\n"
        "• XTR списались, а доступа нет → проверьте «Профиль»; если пусто — напишите нам.\n"
        "• Нужен чек → история покупок Stars / {premium_bot}.\n\n"
        "Регион/магазины приложений:\n"
        "• Приложение недоступно → смените страну/регион Apple ID: {apple_region}\n"
        "• На macOS «Unidentified developer» → Open Anyway (Privacy & Security).\n\n"
        "Общие проверки:\n"
        "• Интернет стабильный? Дата/время корректные (автосинхронизация)?\n"
        "• Нет ли другого VPN/прокси? Энергосбережение не мешает?\n"
        "• Клиент свежий? {hiddify_app_releases}\n\n"
        "Лайфхак: храните QR локально — быстрое восстановление на новом устройстве."
    ).format(**GUIDE_LINKS),
    "8": (
        "🛡 *Приватность и безопасность*\n\n"
        "Что мы НЕ делаем:\n"
        "• Не анализируем содержимое вашего трафика.\n"
        "• Не продаём и не передаём данные третьим сторонам.\n\n"
        "Что логируется на стороне сервиса:\n"
        "• Технические метрики: объём, даты, статус — для биллинга и abuse‑защиты.\n"
        "• Ключи и ссылки — только в рамках вашей учётки.\n\n"
        "Советы:\n"
        "• Скачивайте клиенты из официальных источников (Play/App Store, GitHub Releases): {hiddify_app_releases}\n"
        "• Держите Google Play Protect включённым: {google_play_protect}\n"
        "• На macOS запускайте доверенные сборки; при необходимости — Open Anyway.\n"
        "• Не ставьте сомнительные APK; проверяйте подпись/источник.\n\n"
        "Лайфхак: храните SUB‑ссылку в менеджере паролей — удобно и безопасно."
    ).format(**GUIDE_LINKS),
}


# ---------- Keyboards (RU-only) ----------
def kb_main(_lang: str) -> Dict[str, Any]:
    def b(text: str, data: str) -> Dict[str, str]:
        return {"text": text, "callback_data": data}

    rows: List[List[Dict[str, str]]] = [
        [
            b("🛒 Купить", "menu:buy"),
            b("🪪 Профиль", "menu:profile"),
            b("📚 Гид", "menu:guide"),
        ]
    ]
    return {"inline_keyboard": rows}


def kb_back() -> Dict[str, Any]:
    return {"inline_keyboard": [[{"text": "⬅️ Назад", "callback_data": "menu:home"}]]}


def kb_plans(plans: List[Plan]) -> Dict[str, Any]:
    rows: List[List[Dict[str, str]]] = []
    row: List[Dict[str, str]] = []
    for p in plans:
        row.append({"text": f"💠 {p.name}", "callback_data": f"plan:show:{p.plan_id}"})
    if row:
        rows.append(row)
    rows.append([{"text": "⬅️ Назад", "callback_data": "menu:home"}])
    return {"inline_keyboard": rows}


def panel_configured() -> bool:
    return bool(
        HIDDIFY_BASE_URL and ADMIN_PROXY_PATH and USER_PROXY_PATH and HIDDIFY_API_KEY
    )


def kb_plan_actions(p: Plan) -> Dict[str, Any]:
    actions: List[List[Dict[str, str]]] = [
        [{"text": "💳 Оплатить XTR", "callback_data": f"plan:pay:{p.plan_id}"}],
        [{"text": "🔑 Уже есть ключ", "callback_data": "menu:havekey"}],
    ]
    if panel_configured():
        actions.append(
            [{"text": "➕ Продлить/апгрейдить", "callback_data": "plan:extend"}]
        )
    actions.append([{"text": "⬅️ К тарифам", "callback_data": "menu:buy"}])
    return {"inline_keyboard": actions}


def kb_guide_toc() -> Dict[str, Any]:
    rows = [
        [
            {"text": "🟢 Android", "callback_data": "guide:post:2"},
            {"text": "🍏 iOS/iPadOS", "callback_data": "guide:post:3"},
        ],
        [
            {"text": "🖥 Desktop/TV", "callback_data": "guide:post:4"},
            {"text": "💳 Оплата XTR", "callback_data": "guide:post:5"},
        ],
        [
            {"text": "🔗 Профиль/Продление", "callback_data": "guide:post:6"},
            {"text": "🛠 FAQ", "callback_data": "guide:post:7"},
        ],
        [{"text": "🛡 Приватность", "callback_data": "guide:post:8"}],
        [{"text": "⬅️ Главная", "callback_data": "menu:home"}],
    ]
    return {"inline_keyboard": rows}


def kb_guide_nav(idx: int) -> Dict[str, Any]:
    next_idx = idx + 1 if idx < 8 else 2
    rows = [
        [
            {"text": "🔙 Оглавление", "callback_data": "menu:guide"},
            {"text": "▶️ Далее", "callback_data": f"guide:post:{next_idx}"},
        ]
    ]
    return {"inline_keyboard": rows}


# ---------- Helpers ----------
def _ensure_int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except Exception:
        return None


def ensure_persistent_lang(uid: int, msg_from: Dict[str, Any]) -> str:
    # Всегда RU, но сохраняем в БД для единообразия
    stored = DBI.get_user_lang(uid)
    if stored:
        return stored
    return DBI.set_user_lang_if_empty(uid, "ru")


def main_menu_text(lang: str) -> str:
    base = (
        T(lang, "welcome", brand=BUSINESS_NAME, loc=SERVER_LOCATION)
        + "\n\n"
        + T(
            lang,
            "card",
            support_tg=SUPPORT_TG or "—",
            support_email=SUPPORT_EMAIL or "—",
            loc=SERVER_LOCATION,
        )
    )
    if SHOW_PANEL_IN_MENU:
        panel = HIDDIFY_BASE_URL or BRAND_SITE or "—"
        base += f"\n\n🧭 {panel}"
    return base


def deeplink_from_sub(sub: str, display_name: Optional[str] = None) -> str:
    if "#" in sub:
        return f"hiddify://import/{sub}"
    name = display_name or BUSINESS_NAME
    return f"hiddify://import/{sub}#{quote(name)}"


def _first_https_url(text: str) -> Optional[str]:
    m = re.search(r"(https?://[^\s]+)", text)
    return m.group(1) if m else None


def extract_sub_from_text(text: str) -> Optional[str]:
    text = (text or "").strip()
    m = re.search(r"hiddify://import/(https?://[^\s#]+)", text)
    if m:
        return m.group(1)
    url = _first_https_url(text)
    if url:
        p = urlparse(url)
        clean = f"{p.scheme}://{p.netloc}{p.path}"
        if p.query:
            clean += f"?{p.query}"
        return clean
    return None


def _fmt_bytes(n: Optional[int]) -> str:
    if not n or n < 0:
        return "—"
    gb = n / (1024**3)
    if gb >= 1:
        return f"{gb:.1f} ГБ"
    mb = n / (1024**2)
    return f"{mb:.0f} МБ"


def _human_left(
    expire_ts: Optional[int],
    fallback_iso: Optional[str],
    now: Optional[datetime] = None,
) -> str:
    now = now or datetime.utcnow().replace(tzinfo=timezone.utc)
    if expire_ts and expire_ts > 0:
        exp = datetime.fromtimestamp(expire_ts, tz=timezone.utc)
    else:
        exp = None
        if fallback_iso:
            try:
                dt = datetime.fromisoformat(fallback_iso)
                exp = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                exp = None
    if not exp:
        return "—"
    days = (exp - now).days
    if days >= 0:
        return f"{days} дн."
    return f"просрочено на {abs(days)} дн."


async def fetch_subscription_userinfo(
    sub_url: str,
) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[str]]:
    """HEAD the SUB and parse `subscription-userinfo` & optional profile-web-page-url.
    Returns: (upload, download, total, expire_epoch, profile_web_page_url)
    """
    if not sub_url:
        return None, None, None, None, None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as cli:
            r = await cli.head(sub_url, follow_redirects=True)
            hdr = r.headers
            info = (
                hdr.get("subscription-userinfo")
                or hdr.get("Subscription-Userinfo")
                or ""
            )
            # Example: upload=455727941; download=6174315083; total=1073741824000; expire=1671815872
            upload = download = total = expire = None
            for part in info.split(";"):
                kv = part.strip().split("=", 1)
                if len(kv) != 2:
                    continue
                k, v = kv[0].strip().lower(), kv[1].strip()
                if k == "upload":
                    upload = int(v)
                elif k == "download":
                    download = int(v)
                elif k in ("total", "totl"):
                    total = int(v)
                elif k == "expire":
                    try:
                        expire = int(v)
                    except Exception:
                        expire = None
            web_url = hdr.get("profile-web-page-url") or hdr.get("Profile-Web-Page-Url")
            return upload, download, total, expire, web_url
    except Exception:
        return None, None, None, None, None


async def detect_protocols_from_sub(sub_url: str) -> List[str]:
    protos: List[str] = []
    if not sub_url:
        return protos
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as cli:
            r = await cli.get(sub_url, follow_redirects=True)
            txt = r.text.lower()
            if "vless://" in txt:
                protos.append("VLESS")
            if "vmess://" in txt:
                protos.append("VMESS")
            if "trojan://" in txt:
                protos.append("TROJAN")
            if "ss://" in txt:
                protos.append("Shadowsocks")
            if "hysteria2://" in txt or "hysteria://" in txt:
                protos.append("Hysteria")
            if "tuic://" in txt:
                protos.append("TUIC")
            if "wireguard" in txt or "wg://" in txt:
                protos.append("WireGuard")
    except Exception:
        pass
    return protos


def proto_tips(protos: List[str]) -> str:
    if not protos:
        return "—"
    tips: List[str] = []
    if "VLESS" in protos:
        tips.append("VLESS/REALITY — чаще всего стабилен.")
    if "Hysteria" in protos:
        tips.append("Hysteria2 — быстро на мобильных.")
    if "TUIC" in protos:
        tips.append("TUIC — низкая задержка.")
    if "TROJAN" in protos:
        tips.append("Trojan — как запасной через TLS‑SNI.")
    if "VMESS" in protos or "Shadowsocks" in protos:
        tips.append("VMess/SS — запасной вариант.")
    return "• " + "\n• ".join(tips)


# ---------- Panel API helpers (v2 minimal) ----------
def admin_base() -> Optional[str]:
    if not panel_configured():
        return None
    return f"{HIDDIFY_BASE_URL}/{ADMIN_PROXY_PATH}"


def user_base() -> Optional[str]:
    if not (HIDDIFY_BASE_URL and USER_PROXY_PATH):
        return None
    return f"{HIDDIFY_BASE_URL}/{USER_PROXY_PATH}"


# --- NEW: panel user helpers ---
def _extract_uuid_from_sub(sub_url: str) -> Optional[str]:
    try:
        # looks like: https://<host>/<USER_PROXY_PATH>/<uuid>/#Name
        path = urlparse(sub_url).path.strip("/").split("/")
        return path[-1] if path else None
    except Exception:
        return None


async def _panel_list_users(
    cli: httpx.AsyncClient, base_admin: str, headers_admin: Dict[str, str]
) -> List[Dict[str, Any]]:
    url = f"{base_admin}/api/v2/admin/user/"
    r = await cli.get(url, headers=headers_admin)
    r.raise_for_status()
    if r.headers.get("content-type", "").startswith("application/json"):
        return r.json() or []
    return []


async def _panel_find_user_by_tid(
    cli: httpx.AsyncClient,
    base_admin: str,
    headers_admin: Dict[str, str],
    telegram_id: int,
) -> Optional[Dict[str, Any]]:
    users = await _panel_list_users(cli, base_admin, headers_admin)
    for u in users:
        try:
            if int(u.get("telegram_id") or 0) == int(telegram_id):
                return u
        except Exception:
            continue
    return None


def _calc_new_package_days(
    old_start_iso: Optional[str], old_package_days: Optional[int], extend_days: int
) -> Tuple[datetime, int, datetime]:
    now = datetime.now(timezone.utc)
    # старт и текущая дата окончания
    start_dt = datetime.fromisoformat(old_start_iso) if old_start_iso else now
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    cur_expiry = start_dt + timedelta(days=int(old_package_days or 0))
    # продлеваем от актуальной точки
    new_expiry = (cur_expiry if cur_expiry > now else now) + timedelta(
        days=int(extend_days)
    )
    new_days = max(1, (new_expiry - start_dt).days)
    return start_dt, new_days, new_expiry


async def provision_by_panel_api(
    telegram_id: int, username: Optional[str], plan: Plan
) -> Tuple[str, str, Optional[str]]:
    """
    Создаёт/продлевает пользователя через Hiddify Admin API и возвращает:
    (sub_url, display_name, expires_at_iso)
    """
    if not panel_configured():
        raise RuntimeError("panel API not configured")

    base_admin = admin_base()
    base_user = user_base()
    if not base_admin or not base_user:
        raise RuntimeError("panel base urls not resolved")

    headers_admin = {"Hiddify-API-Key": HIDDIFY_API_KEY}
    lang = DBI.get_user_lang(telegram_id) or "ru"
    display_name = f"{DISPLAY_PREFIX}{username or telegram_id}"

    new_expiry_iso: Optional[str] = None

    async with httpx.AsyncClient(timeout=_timeout(), limits=_limits()) as cli:
        # 1) Ищем пользователя по telegram_id
        existing = await _panel_find_user_by_tid(
            cli, base_admin, headers_admin, telegram_id
        )

        if existing:
            user_uuid = existing.get("uuid") or existing.get("user_uuid")
            if not user_uuid:
                raise RuntimeError("panel API: user without uuid")

            old_start = existing.get("start_date")
            old_days = int(existing.get("package_days") or 0)
            old_limit = float(existing.get("usage_limit_GB") or 0.0)

            # Продлеваем «от фактического окончания»: если уже истёк — от now
            _, new_pkg_days, new_expiry = _calc_new_package_days(
                old_start, old_days, plan.days
            )
            new_expiry_iso = new_expiry.isoformat()

            patch = {
                "enable": True,
                "is_active": True,
                "mode": "no_reset",
                "usage_limit_GB": max(old_limit, float(plan.traffic_gb)),
                "package_days": int(new_pkg_days),
                "lang": lang,
                "comment": f"{plan.name} | devices={getattr(plan, 'devices', 1)}",
            }
            url_patch = f"{base_admin}/api/v2/admin/user/{user_uuid}/"
            r = await cli.patch(url_patch, json=patch, headers=headers_admin)
            r.raise_for_status()

        else:
            # 2) Создаём нового
            payload_create = {
                "name": display_name,
                "telegram_id": int(telegram_id),
                "package_days": int(plan.days),
                "usage_limit_GB": float(plan.traffic_gb),
                "is_active": True,
                "enable": True,
                "mode": "no_reset",
                "lang": lang,
                "comment": f"{plan.name} | devices={getattr(plan, 'devices', 1)}",
            }
            url_create = f"{base_admin}/api/v2/admin/user/"
            r = await cli.post(url_create, json=payload_create, headers=headers_admin)
            r.raise_for_status()

            user_obj = (
                r.json()
                if r.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            user_uuid = (user_obj or {}).get("uuid") or (user_obj or {}).get(
                "user_uuid"
            )
            if not user_uuid:
                raise RuntimeError("panel API create: no uuid in response")

            # Вычисляем expires_at
            try:
                start_s = (user_obj or {}).get("start_date")
                start_dt = (
                    datetime.fromisoformat(start_s)
                    if start_s
                    else datetime.now(timezone.utc)
                )
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                expires_at = start_dt + timedelta(
                    days=int((user_obj or {}).get("package_days") or plan.days)
                )
            except Exception:
                expires_at = datetime.now(timezone.utc) + timedelta(days=plan.days)
            new_expiry_iso = expires_at.isoformat()

        # 3) Формируем SUB (short если доступен)
        long_sub = f"{base_user}/{user_uuid}/#{quote(display_name)}"
        sub = long_sub

        if not HIDDIFY_FORCE_LONG_SUB:
            user_headers = {"Hiddify-API-Key": user_uuid}
            r2 = await cli.get(
                f"{base_user}/{user_uuid}/api/v2/user/short/", headers=user_headers
            )
            if r2.status_code == 200 and r2.headers.get("content-type", "").startswith(
                "application/json"
            ):
                sj = r2.json() or {}
                candidate = sj.get("full_url") or sj.get("short") or sj.get("url")
                if isinstance(candidate, str) and candidate.startswith(
                    f"{base_user}/{user_uuid}/"
                ):
                    sub = candidate

        return sub, display_name, new_expiry_iso


async def provision_subscription(
    telegram_id: int, username: Optional[str], plan: Plan
) -> Tuple[str, str, Optional[str], Optional[str]]:
    """Returns (sub_url, display_name, expires_at, warning). Falls back to placeholder if panel fails."""
    errors: List[str] = []

    async def attempt() -> Tuple[Optional[str], Optional[str], Optional[str]]:
        if HIDDIFY_BRIDGE_URL and HIDDIFY_BRIDGE_TOKEN:
            try:
                raise RuntimeError("bridge disabled in this build")
            except Exception as e:
                errors.append(f"bridge: {e}")
        if HIDDIFY_PROVISION_CMD:
            try:
                cmd = HIDDIFY_PROVISION_CMD.format(
                    telegram_id=telegram_id,
                    username=username or "",
                    plan_id=plan.plan_id,
                )
                proc = await asyncio.create_subprocess_shell(
                    cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                out, err = await proc.communicate()
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"cli exit {proc.returncode}: {err.decode()[:200]}"
                    )
                data = json.loads(out.decode())
                sub = data.get("sub_url")
                if not sub:
                    raise RuntimeError("cli: sub_url missing")
                return (
                    sub,
                    data.get("display_name") or BUSINESS_NAME,
                    data.get("expires_at"),
                )
            except Exception as e:
                errors.append(f"cli: {e}")
        try:
            sub, name, exp = await provision_by_panel_api(telegram_id, username, plan)
            return sub, name, exp
        except Exception as e:
            errors.append(f"panel: {e}")
        return None, None, None

    for delay in (0, 2, 5):
        if delay:
            await asyncio.sleep(delay)
        sub, name, exp = await attempt()
        if sub:
            return sub, name or BUSINESS_NAME, exp, None

    base = SUB_LINK_DOMAIN or HIDDIFY_BASE_URL or BRAND_SITE or ""
    base = base.rstrip("/")
    token = (
        base64.urlsafe_b64encode(
            f"{telegram_id}:{plan.plan_id}:{datetime.utcnow().isoformat()}".encode()
        )
        .decode()
        .rstrip("=")
    )
    fake_sub = f"{base}/sub/{token}" if base else f"https://example.invalid/sub/{token}"
    exp = (
        (datetime.utcnow() + timedelta(days=plan.days))
        .replace(tzinfo=timezone.utc)
        .isoformat()
    )
    warn = "SUB выдан в фолбэк‑режиме (автовыдача недоступна)."
    await notify_admins(
        f"Provision fallback for {telegram_id} ({plan.plan_id}). Errors: {errors[:3]}"
    )
    return fake_sub, BUSINESS_NAME, exp, warn


# ---------- Stars invoice ----------
async def send_stars_invoice(chat_id: int, user_id: int, p: Plan, lang: str):
    payload = {
        "type": "plan",
        "plan_id": p.plan_id,
        "user_id": user_id,
        "ts": datetime.utcnow().isoformat(),
    }
    title = f"{p.name} — {p.days} дн / {p.traffic_gb} ГБ / {p.devices} устр."
    desc = T(lang, "pay_info")
    # Для Stars (XTR) provider_token должен быть пустым; одна цена в prices.
    await tg_api(
        "sendInvoice",
        {
            "chat_id": chat_id,
            "title": title,
            "description": desc,
            "payload": json.dumps(payload, ensure_ascii=False),
            "provider_token": "",
            "currency": "XTR",
            "prices": [{"label": p.name, "amount": int(p.price)}],
        },
    )


# ---------- State ----------
PENDING_SUB: Dict[int, bool] = {}

# ---------- FastAPI ----------
app = FastAPI(title="VPN Bot + Hiddify (RU-only)", version="1.4.0")
scheduler: Optional[_SchedulerType] = None


@app.on_event("startup")
async def _startup():
    global _tg_client, scheduler
    _tg_client = httpx.AsyncClient(timeout=_timeout(), limits=_limits())
    logging.info("HTTPX pool started")

    if AsyncIOScheduler is not None and CronTrigger is not None:
        try:
            sch = AsyncIOScheduler(timezone="UTC")
            # reminders
            minute, hour, dom, month, dow = (REMINDER_CRON.split() + ["0"] * 5)[:5]
            sch.add_job(
                reminder_job,
                trigger=CronTrigger(
                    minute=minute,
                    hour=hour,
                    day=dom,
                    month=month,
                    day_of_week=dow,
                    timezone="UTC",
                ),
                id="reminders",
            )
            # suspender
            sm, sh, sdom, smon, sdow = (SUSPEND_CRON.split() + ["0"] * 5)[:5]
            sch.add_job(
                suspender_job,
                trigger=CronTrigger(
                    minute=sm,
                    hour=sh,
                    day=sdom,
                    month=smon,
                    day_of_week=sdow,
                    timezone="UTC",
                ),
                id="suspender",
            )
            sch.start()
            scheduler = sch  # используется в shutdown
            logging.info(
                "APScheduler started (reminders=%s, suspender=%s)",
                REMINDER_CRON,
                SUSPEND_CRON,
            )
        except Exception as e:
            logging.warning("Scheduler init failed: %s", e)
    else:
        logging.info("APScheduler not installed; reminders/suspender disabled")


@app.on_event("shutdown")
async def _shutdown():
    global _tg_client, scheduler
    if scheduler:
        try:
            scheduler.shutdown(wait=False)  # type: ignore[attr-defined]
        except Exception:
            pass
        scheduler = None
    if _tg_client:
        try:
            await _tg_client.aclose()
        finally:
            _tg_client = None
    logging.info("HTTPX pool closed")


# ---------- Telegram ----------
class Update(BaseModel):
    update_id: int
    message: Optional[Dict[str, Any]] = None
    callback_query: Optional[Dict[str, Any]] = None
    pre_checkout_query: Optional[Dict[str, Any]] = None


def reply_markup(kb: Dict[str, Any]) -> Dict[str, Any]:
    return {"reply_markup": kb, "parse_mode": "Markdown"}


async def _send(
    chat_id: int,
    text: str,
    kb: Optional[Dict[str, Any]] = None,
    parse_mode: str = "Markdown",
):
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if kb:
        payload["reply_markup"] = kb
    await tg_api("sendMessage", payload)


async def _edit(
    chat_id: int, message_id: int, text: str, kb: Optional[Dict[str, Any]] = None
):
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    if kb:
        payload["reply_markup"] = kb
    try:
        await tg_api("editMessageText", payload)
    except Exception as e:
        logging.debug("editMessageText failed: %s", e)


async def _answer_cb(cqid: Optional[str]):
    if not cqid:
        return
    try:
        await tg_api("answerCallbackQuery", {"callback_query_id": cqid})
    except Exception:
        pass


# ---------- Reminder job ----------
def _parse_iso_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def _send_reminder(u: Dict[str, Any], days_left: int):
    lang = u.get("language") or "ru"
    chat_id = int(u["telegram_id"])
    txt = (
        f"⏰ Напоминание. Подписка истекает через {days_left} дн. /start → Купить"
        if days_left > 0
        else "⏰ Сегодня последний день подписки. /start → Купить"
    )
    await _send(chat_id, txt, kb_main(lang))


async def reminder_job():
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    for d in REMINDER_DAYS:
        users = DBI.get_users_expiring_on(now + timedelta(days=d))
        for u in users:
            key = f"D{d}"
            if DBI.reminder_was_sent(int(u["telegram_id"]), key):
                continue
            exp = _parse_iso_dt(u.get("expires_at"))
            if not exp:
                continue
            try:
                await _send_reminder(u, d)
                DBI.mark_reminder_sent(int(u["telegram_id"]), key)
            except Exception as e:
                logging.warning(
                    "Reminder send failed for %s D=%s: %s", u.get("telegram_id"), d, e
                )


# --- NEW: auto suspend job ---
SUSPEND_CRON = os.getenv("SUSPEND_CRON", "0 * * * *")  # раз в час по умолчанию


async def _suspend_user_on_panel(user_uuid: str):
    base_admin = admin_base()
    if not base_admin:
        return
    headers_admin = {"Hiddify-API-Key": HIDDIFY_API_KEY}
    async with httpx.AsyncClient(timeout=_timeout(), limits=_limits()) as cli:
        url_patch = f"{base_admin}/api/v2/admin/user/{user_uuid}/"
        patch = {"enable": False, "is_active": False}
        try:
            await cli.patch(url_patch, json=patch, headers=headers_admin)
        except Exception as e:
            logging.warning("Suspend patch failed for %s: %s", user_uuid, e)


async def suspender_job():
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    users = []
    try:
        # берём всех с заполненным expires_at
        with sqlite3.connect(DBI.path) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                "SELECT telegram_id, sub_url, expires_at FROM users WHERE expires_at IS NOT NULL"
            ).fetchall()
            users = [dict(r) for r in rows]
    except Exception as e:
        logging.warning("suspender: db read failed: %s", e)
        return

    for u in users:
        exp = _parse_iso_dt(u.get("expires_at"))
        if not exp or exp > now:
            continue  # не истёк
        sub = u.get("sub_url") or ""
        uuid = _extract_uuid_from_sub(sub) or ""
        if not uuid:
            continue
        await _suspend_user_on_panel(uuid)


# ---------- Handlers ----------
async def _handle_message(msg: Dict[str, Any]):
    chat_id = msg.get("chat", {}).get("id")
    if chat_id is None:
        return
    text = (msg.get("text") or "").strip()
    from_user = msg.get("from") or {}
    uid = _ensure_int(from_user.get("id")) or 0
    lang = ensure_persistent_lang(uid, from_user)

    is_admin = (
        any((str(uid) == s.strip()) for s in ADMIN_PRESEED_USER_IDS.split(","))
        if ADMIN_PRESEED_USER_IDS
        else False
    )

    if PENDING_SUB.get(uid):
        sub = extract_sub_from_text(text)
        if not sub:
            await _send(chat_id, T(lang, "sub_bad"), kb_main(lang))
            return
        DBI.upsert_user(uid, from_user.get("username"), sub, BUSINESS_NAME, None, lang)
        deeplink = deeplink_from_sub(sub, BUSINESS_NAME)
        await _send(
            chat_id, T(lang, "sub_saved", sub=sub, deeplink=deeplink), kb_main(lang)
        )
        PENDING_SUB.pop(uid, None)
        return

    if text.startswith("/start"):
        DBI.upsert_user(uid, from_user.get("username"), None, None, None, lang)
        await _send(chat_id, main_menu_text(lang), kb_main(lang))
        return

    if text.startswith("/set_sub") and is_admin:
        try:
            _, tid, sub = text.split(maxsplit=2)
            DBI.upsert_user(int(tid), None, sub, BUSINESS_NAME, None, "ru")
            await _send(chat_id, T(lang, "admin_ok"))
        except Exception:
            await _send(chat_id, T(lang, "admin_err"))
        return

    await _send(chat_id, T(lang, "choose"), kb_main(lang))


async def _handle_callback(cb: Dict[str, Any]):
    cqid = cb.get("id")
    msg = cb.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    message_id = msg.get("message_id")
    data = cb.get("data", "") or ""
    from_user = cb.get("from", {}) or {}
    user_id = _ensure_int(from_user.get("id")) or 0
    lang = DBI.get_user_lang(user_id) or "ru"

    async def edit(text: str, kb: Optional[Dict[str, Any]] = None):
        if chat_id is None or message_id is None:
            return
        await _answer_cb(cqid)
        await _edit(chat_id, message_id, text, kb)

    if data == "menu:home":
        return await edit(main_menu_text(lang), kb_main(lang))

    if data == "menu:buy":
        return await edit(render_plans_text(lang, PLANS), kb_plans(PLANS))

    if data.startswith("plan:show:"):
        pid = data.split(":", 2)[2]
        p = next((x for x in PLANS if x.plan_id == pid), None)
        if not p:
            return await edit(T(lang, "choose"), kb_plans(PLANS))
        text = render_plan_card(lang, p) + "\n\n" + T(lang, "pay_info")
        return await edit(text, kb_plan_actions(p))

    if data.startswith("plan:pay:"):
        pid = data.split(":", 2)[2]
        p = next((x for x in PLANS if x.plan_id == pid), None)
        await _answer_cb(cqid)
        if not p or chat_id is None:
            return
        # Важно: invoice отправляется НОВЫМ сообщением (ограничение Telegram API).
        await send_stars_invoice(chat_id, user_id, p, lang)
        return

    if data == "plan:extend":
        if not panel_configured():
            return await edit(T(lang, "panel_not_conf"), kb_back())
        txt = T(lang, "extend_hint") + "\n\n" + render_plans_text(lang, PLANS)
        return await edit(txt, kb_plans(PLANS))

    if data == "menu:profile":
        u = DBI.get_user(user_id)
        if not u or not u.get("sub_url"):
            return await edit(T(lang, "links_empty"), kb_main(lang))
        sub = u["sub_url"]
        deeplink = deeplink_from_sub(sub, u.get("display_name") or BUSINESS_NAME)
        upload, download, total, expire, web_url = await fetch_subscription_userinfo(
            sub
        )
        used = (upload or 0) + (download or 0)
        percent = round((used / total * 100), 1) if total and total > 0 else 0
        left = (total - used) if total else None
        days_left = _human_left(expire, u.get("expires_at"))
        protos = await detect_protocols_from_sub(sub)
        tips = proto_tips(protos)
        panel_line = f"🔗 Панель: {web_url}" if web_url else ""
        extra = T(lang, "faq_hint", tips=tips)

        txt = T(
            lang,
            "account_block",
            sub=sub,
            deeplink=deeplink,
            panel=panel_line or "",
            used=_fmt_bytes(used),
            total=_fmt_bytes(total),
            percent=percent,
            left=_fmt_bytes(left),
            days_left=days_left,
            extra=extra,
        )
        return await edit(txt, kb_back())

    if data == "menu:havekey":
        PENDING_SUB[user_id] = True
        return await edit(T(lang, "send_sub"), kb_back())

    if data == "menu:guide":
        text = T(lang, "guide_title")
        toc = GUIDE_RU["toc"]
        return await edit(text + "\n\n" + toc, kb_guide_toc())

    if data.startswith("guide:post:"):
        try:
            idx = int(data.split(":")[-1])
        except Exception:
            return await edit(T(lang, "choose"), kb_guide_toc())
        content = GUIDE_RU.get(str(idx))
        if not content:
            return await edit(T(lang, "choose"), kb_guide_toc())
        return await edit(content, kb_guide_nav(idx))

    return await edit(T(lang, "choose"), kb_main(lang))


async def _handle_pre_checkout(pcq: Dict[str, Any]):
    await tg_api(
        "answerPreCheckoutQuery", {"pre_checkout_query_id": pcq["id"], "ok": True}
    )


async def _handle_successful_payment(msg: Dict[str, Any]):
    chat_id = msg.get("chat", {}).get("id")
    from_user = msg.get("from", {}) or {}
    user_id = _ensure_int(from_user.get("id")) or 0
    lang = DBI.get_user_lang(user_id) or ensure_persistent_lang(user_id, from_user)
    username = from_user.get("username")

    sp = msg.get("successful_payment", {}) or {}
    payload_raw = sp.get("invoice_payload")
    try:
        payload = json.loads(payload_raw) if payload_raw else {}
    except Exception:
        payload = {}
    plan_id = (payload or {}).get("plan_id")
    p = next((x for x in PLANS if x.plan_id == plan_id), None)
    if not p or not chat_id:
        await _send(chat_id, T(lang, "internal_err"), kb_main(lang))
        return

    try:
        sub_url, display_name, expires_at, warn = await provision_subscription(
            user_id, username, p
        )
    except Exception as e:
        await notify_admins(f"Provision fatal for {user_id}: {e}")
        await _send(chat_id, f"{T(lang, 'internal_err')} ({e})", kb_main(lang))
        return

    DBI.upsert_user(user_id, username, sub_url, display_name, expires_at, lang)
    deeplink = deeplink_from_sub(sub_url, display_name)
    txt = T(lang, "paid_ok", sub=sub_url, deeplink=deeplink)
    if warn:
        txt += "\n\n⚠️ " + warn
    await _send(chat_id, txt, kb_main(lang))

    if qrcode:
        try:
            img = qrcode.make(deeplink)  # type: ignore
            buf = io.BytesIO()
            img.save(buf, "PNG")
            buf.seek(0)
            files = {"photo": ("qr.png", buf.read(), "image/png")}
            await tg_api_multipart(
                "sendPhoto", {"chat_id": chat_id, "caption": "QR"}, files
            )
        except Exception:
            pass


# ---------- Webhook ----------
@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request, x_telegram_bot_api_secret_token: Optional[str] = Header(None)
):
    if (
        TELEGRAM_WEBHOOK_SECRET
        and x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET
    ):
        raise HTTPException(status_code=401, detail="invalid secret token")

    data = await request.json()
    upd = Update(**data)
    try:
        if upd.message:
            if upd.message.get("successful_payment"):
                await _handle_successful_payment(upd.message)
            else:
                await _handle_message(upd.message)
        elif upd.callback_query:
            await _handle_callback(upd.callback_query)
        elif upd.pre_checkout_query:
            await _handle_pre_checkout(upd.pre_checkout_query)
    except Exception as e:
        logging.exception("webhook error: %s", e)

    return JSONResponse({"ok": True})


# optional: explain fallback /sub if someone opens an old link
@app.get("/sub/{token}")
async def sub_fallback(token: str):
    return JSONResponse(
        {
            "ok": False,
            "detail": "Fallback sub placeholder. Please use your short link from the bot (looks like https://<host>/<USER_PROXY_PATH>/<uuid>/#Name).",
        },
        status_code=404,
    )


if __name__ == "__main__":
    print("Run: uvicorn vpn_bot_ru_only:app --host 127.0.0.1 --port 8000")
