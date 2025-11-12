# 🛰️ VPN Bot (Hiddify + Telegram Stars, RU-only)

[![CI](https://github.com/ShapArt/vpn-bot-stars-hiddify/actions/workflows/ci.yml/badge.svg)](https://github.com/ShapArt/vpn-bot-stars-hiddify/actions/workflows/ci.yml) [![license](https://img.shields.io/github/license/ShapArt/vpn-bot-stars-hiddify)](https://github.com/ShapArt/vpn-bot-stars-hiddify/blob/main/LICENSE)






**Ключевые факты:**


- 🌟 Оплата XTR (Stars), авто-выдача профилей и напоминания


- 🛰️ Hiddify/Xray, VLESS-Reality/Hysteria2/TUIC (витрина, без секретов)


- 🔒 Акцент на безопасные .env и Secret scanning








<table>


<tr>


<td><b>✨ Что умеет</b><br/>Короткий список возможностей, ориентированных на ценность.</td>


<td><b>🧠 Технологии</b><br/>Стек, ключевые решения, нюансы безопасности.</td>


<td><b>🖼️ Демо</b><br/>Скриншот/гиф или ссылка на Pages.</td>


</tr>


</table>





> [!TIP]


> Репозиторий оформлен по правилам: Conventional Commits, SemVer, CHANGELOG, SECURITY policy и CI.


> Секреты — только через `.env`/секреты репозитория.








<p align="left">


  <img alt="build" src="https://img.shields.io/github/actions/workflow/status/ShapArt/vpn-bot-stars-hiddify/ci.yml?label=CI&logo=githubactions">


  <img alt="license" src="https://img.shields.io/github/license/ShapArt/vpn-bot-stars-hiddify">


  <img alt="last commit" src="https://img.shields.io/github/last-commit/ShapArt/vpn-bot-stars-hiddify">


  <img alt="issues" src="https://img.shields.io/github/issues/ShapArt/vpn-bot-stars-hiddify">


  <img alt="stars" src="https://img.shields.io/github/stars/ShapArt/vpn-bot-stars-hiddify?style=social">


</p>








FastAPI‑бот для продажи доступа к Hiddify через звёзды (XTR) в Telegram.


Фичи:


- 🌟 Оплата XTR (Stars) — `sendInvoice` (валюта XTR)


- 🔗 Автовыдача SUB/QR + deeplink `hiddify://import/<SUB>`


- 🧭 Поддержка панельного API (создание/продление пользователей)


- ⏰ Напоминания о продлении, авто‑приостановка по истечению


- 🧬 Гид внутри бота (Android/iOS/PC), RU‑локаль


- 🗄️ SQLite + индексы; простая деплой‑модель





> В этом публичном репозитории **нет ключей/секретов**. Все чувствительные значения — только через `.env`/секреты репозитория.





## Быстрый старт (локально)


```bash


python -m venv .venv && . .venv/bin/activate  # Windows: .venv\Scripts\activate


pip install -r requirements.txt


uvicorn app.main:app --reload --port 8000


```





## ENV


См. `.env.example` — заполните секреты и пути панели Hiddify.





## Лицензия


MIT





## Архитектура





*Заполнить по мере развития проекта.*








## Конфигурация





*Заполнить по мере развития проекта.*








## Тесты





*Заполнить по мере развития проекта.*








## Roadmap





*Заполнить по мере развития проекта.*


