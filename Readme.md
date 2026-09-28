# Telegram-Controlled WhatsApp + Instagram Inbox Bot

This project is a FastAPI service controlled from Telegram.

## Included

- app.py — main FastAPI application
- requirements.txt — Python dependencies
- .env.example — configuration template
- set_webhook.py — Telegram webhook registration
- Dockerfile — container deployment
- docker-compose.yml — persistent deployment
- BOT_PROMPT.md — architecture/specification
- .gitignore — protects secrets/database files

## Local setup

Install dependencies:

pip install -r requirements.txt

Copy the environment file:

cp .env.example .env

Fill in your credentials.

Then start the server:

uvicorn app:app --host 0.0.0.0 --port 8000

For local testing, expose port 8000 through
an HTTPS tunnel.

Then register Telegram:

python set_webhook.py https://YOUR-HTTPS-DOMAIN

## Docker

docker compose up -d --build

The database is stored in the inbox-data volume.

## Meta setup

Create/configure a Meta developer app with:

- WhatsApp Cloud API
- Instagram Messaging API

WhatsApp webhook:

https://YOUR-DOMAIN/webhook/whatsapp

Instagram webhook:

https://YOUR-DOMAIN/webhook/instagram

Use the same verify tokens entered in .env.

## Telegram

Get your bot token from BotFather.

Get your Telegram numeric user ID from a
Telegram user-ID bot.

Put the ID in:

TELEGRAM_USER_ID

## Important

The code does not contain your real tokens.

Put secrets in .env.

Text messaging is implemented first.

Image/video/audio handling and AI drafting
can be added as future modules.
