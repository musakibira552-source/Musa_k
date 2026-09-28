# Telegram-Controlled WhatsApp + Instagram Inbox Bot

## Goal

Build a private Telegram control panel for a
WhatsApp Business number and an Instagram
professional account.

## Core workflow

1. WhatsApp/Instagram sends an incoming message
   to the Meta webhook.

2. FastAPI verifies the webhook request.

3. The bot stores the contact and message in SQLite.

4. The bot sends a notification to the authorized
   Telegram user.

5. The Telegram user replies directly to that
   notification.

6. The bot identifies the original platform/contact.

7. The bot sends the reply back through the
   corresponding Meta API.

8. The conversation is marked read in the local
   database.

## Telegram commands

/start
- Show help/status

/digest
- Show unread conversations

/todo <text>
- Create a task

/todo
- List open tasks

/done <id>
- Complete a task

## Security

Only TELEGRAM_USER_ID can control the bot.

TELEGRAM_WEBHOOK_SECRET protects Telegram
webhook requests.

META_APP_SECRET can validate Meta webhook
signatures.

Secrets must remain in `.env` and must never
be committed to GitHub.

## Storage

SQLite is used for:

- contacts
- incoming/outgoing messages
- todos
- Telegram message IDs used to route replies

## Current scope

The starter implementation handles text messages.

Media, templates, conversation windows,
multiple Telegram operators, AI drafting,
analytics, and a full admin dashboard can
be added as later modules.
