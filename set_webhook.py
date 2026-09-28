"""
Point your Telegram bot at your server.

Usage:

python set_webhook.py https://YOUR-DOMAIN
"""

import os
import sys

import httpx
from dotenv import load_dotenv


load_dotenv()


if (
    len(sys.argv) != 2
    or not sys.argv[1].startswith("https://")
):

    sys.exit(
        "Usage: python set_webhook.py https://YOUR-DOMAIN"
    )


r = httpx.post(

    f"https://api.telegram.org/"
    f"bot{os.environ['TELEGRAM_BOT_TOKEN']}"
    f"/setWebhook",

    json={

        "url":
            sys.argv[1].rstrip("/")
            + "/webhook/telegram",

        "secret_token":
            os.environ[
                "TELEGRAM_WEBHOOK_SECRET"
            ],

        "allowed_updates": [
            "message",
            "callback_query"
        ],
    }
)


print(r.json())
