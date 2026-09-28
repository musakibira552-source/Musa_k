import hashlib
import hmac
import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Telegram Inbox Bot", version="1.0.0")

DB_PATH = os.getenv("DB_PATH", "/data/inbox.db")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
INSTAGRAM_VERIFY_TOKEN = os.getenv("INSTAGRAM_VERIFY_TOKEN", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")

GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v23.0")

WA_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WA_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

IG_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
IG_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "")

GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


def now():
    return datetime.now(timezone.utc).isoformat()


def db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()

    con.executescript("""
    CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        external_id TEXT NOT NULL,
        name TEXT,
        username TEXT,
        last_message TEXT,
        last_message_at TEXT,
        unread INTEGER DEFAULT 0,
        UNIQUE(platform, external_id)
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platform TEXT NOT NULL,
        external_message_id TEXT,
        external_contact_id TEXT NOT NULL,
        direction TEXT NOT NULL,
        text TEXT,
        created_at TEXT NOT NULL,
        telegram_message_id INTEGER
    );

    CREATE TABLE IF NOT EXISTS todos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        done INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """)

    con.commit()
    con.close()


@app.on_event("startup")
def startup():
    init_db()


def authorized(user_id: int) -> bool:
    return bool(TELEGRAM_USER_ID) and str(user_id) == str(TELEGRAM_USER_ID)


async def tg(method: str, payload: dict):

    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()

        data = r.json()

        if not data.get("ok"):
            raise RuntimeError(str(data))

        return data["result"]


async def tg_text(text: str, reply_to: Optional[int] = None):

    payload = {
        "chat_id": TELEGRAM_USER_ID,
        "text": text
    }

    if reply_to:
        payload["reply_parameters"] = {
            "message_id": reply_to
        }

    return await tg("sendMessage", payload)


def upsert_contact(
    platform,
    external_id,
    name=None,
    username=None,
    text=None
):

    con = db()

    con.execute("""
        INSERT INTO contacts(
            platform,
            external_id,
            name,
            username,
            last_message,
            last_message_at,
            unread
        )
        VALUES (?, ?, ?, ?, ?, ?, 1)

        ON CONFLICT(platform, external_id)
        DO UPDATE SET
            name=COALESCE(
                excluded.name,
                contacts.name
            ),

            username=COALESCE(
                excluded.username,
                contacts.username
            ),

            last_message=excluded.last_message,

            last_message_at=excluded.last_message_at,

            unread=contacts.unread + 1
    """, (
        platform,
        str(external_id),
        name,
        username,
        text,
        now()
    ))

    con.commit()

    row = con.execute(
        """
        SELECT *
        FROM contacts
        WHERE platform=?
        AND external_id=?
        """,
        (
            platform,
            str(external_id)
        )
    ).fetchone()

    con.close()

    return row


def save_message(
    platform,
    external_id,
    direction,
    text,
    external_message_id=None
):

    con = db()

    cur = con.execute("""
        INSERT INTO messages(
            platform,
            external_message_id,
            external_contact_id,
            direction,
            text,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        platform,
        external_message_id,
        str(external_id),
        direction,
        text,
        now()
    ))

    con.commit()

    msg_id = cur.lastrowid

    con.close()

    return msg_id


async def send_whatsapp(to: str, text: str):

    if not WA_ACCESS_TOKEN or not WA_PHONE_NUMBER_ID:
        raise RuntimeError(
            "WhatsApp credentials are not configured"
        )

    url = f"{GRAPH_BASE}/{WA_PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WA_ACCESS_TOKEN}"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": str(to),
        "type": "text",
        "text": {
            "body": text
        }
    }

    async with httpx.AsyncClient(timeout=30) as client:

        r = await client.post(
            url,
            headers=headers,
            json=payload
        )

        r.raise_for_status()

        return r.json()


async def send_instagram(
    recipient_id: str,
    text: str
):

    if not IG_ACCESS_TOKEN:
        raise RuntimeError(
            "Instagram access token is not configured"
        )

    url = f"{GRAPH_BASE}/{IG_ACCOUNT_ID}/messages"

    payload = {
        "recipient": {
            "id": str(recipient_id)
        },

        "message": {
            "text": text
        },

        "access_token": IG_ACCESS_TOKEN
    }

    async with httpx.AsyncClient(timeout=30) as client:

        r = await client.post(
            url,
            json=payload
        )

        r.raise_for_status()

        return r.json()


def verify_meta_signature(
    raw: bytes,
    signature: Optional[str]
) -> bool:

    if not META_APP_SECRET:
        return True

    if not signature:
        return False

    if not signature.startswith("sha256="):
        return False

    expected = hmac.new(
        META_APP_SECRET.encode(),
        raw,
        hashlib.sha256
    ).hexdigest()

    received = signature.split("=", 1)[1]

    return hmac.compare_digest(
        received,
        expected
    )


async def handle_incoming(
    platform: str,
    sender_id: str,
    text: str,
    external_message_id: str,
    name=None,
    username=None
):

    upsert_contact(
        platform,
        sender_id,
        name,
        username,
        text
    )

    save_message(
        platform,
        sender_id,
        "in",
        text,
        external_message_id
    )

    label = (
        "WhatsApp"
        if platform == "whatsapp"
        else "Instagram"
    )

    body = text or "[non-text message]"

    sent = await tg_text(
        f"📩 {label}\n"
        f"Contact: {name or sender_id}\n"
        f"ID: {sender_id}\n\n"
        f"{body}"
    )

    con = db()

    con.execute(
        """
        UPDATE messages
        SET telegram_message_id=?
        WHERE id=(
            SELECT MAX(id)
            FROM messages
            WHERE platform=?
            AND external_contact_id=?
        )
        """,
        (
            sent["message_id"],
            platform,
            str(sender_id)
        )
    )

    con.commit()

    con.close()


@app.get("/")
async def health():

    return {
        "status": "ok",
        "service": "inbox-bot"
    }


@app.get("/webhook/whatsapp")
async def whatsapp_verify(
    request: Request
):

    q = request.query_params

    if (
        q.get("hub.mode") == "subscribe"
        and
        q.get("hub.verify_token")
        == WHATSAPP_VERIFY_TOKEN
    ):

        return PlainTextResponse(
            q.get("hub.challenge", "")
        )

    raise HTTPException(
        status_code=403,
        detail="Verification failed"
    )


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(
    request: Request
):

    raw = await request.body()

    if not verify_meta_signature(
        raw,
        request.headers.get(
            "x-hub-signature-256"
        )
    ):

        raise HTTPException(
            status_code=403,
            detail="Bad signature"
        )

    data = json.loads(raw)

    for entry in data.get("entry", []):

        for change in entry.get(
            "changes",
            []
        ):

            value = change.get(
                "value",
                {}
            )

            contacts = value.get(
                "contacts",
                []
            )

            name = None

            if contacts:

                name = contacts[0].get(
                    "profile",
                    {}
                ).get(
                    "name"
                )

            for msg in value.get(
                "messages",
                []
            ):

                if msg.get("type") != "text":
                    continue

                sender = msg.get("from")

                text = msg.get(
                    "text",
                    {}
                ).get(
                    "body",
                    ""
                )

                await handle_incoming(
                    "whatsapp",
                    sender,
                    text,
                    msg.get("id"),
                    name=name
                )

    return {
        "ok": True
    }


@app.get("/webhook/instagram")
async def instagram_verify(
    request: Request
):

    q = request.query_params

    if (
        q.get("hub.mode") == "subscribe"
        and
        q.get("hub.verify_token")
        == INSTAGRAM_VERIFY_TOKEN
    ):

        return PlainTextResponse(
            q.get("hub.challenge", "")
        )

    raise HTTPException(
        status_code=403,
        detail="Verification failed"
    )


@app.post("/webhook/instagram")
async def instagram_webhook(
    request: Request
):

    raw = await request.body()

    if not verify_meta_signature(
        raw,
        request.headers.get(
            "x-hub-signature-256"
        )
    ):

        raise HTTPException(
            status_code=403,
            detail="Bad signature"
        )

    data = json.loads(raw)

    for entry in data.get(
        "entry",
        []
    ):

        for messaging in entry.get(
            "messaging",
            []
        ):

            sender = messaging.get(
                "sender",
                {}
            ).get(
                "id"
            )

            message = messaging.get(
                "message",
                {}
            )

            if (
                not sender
                or not message
                or message.get("is_echo")
            ):
                continue

            text = message.get(
                "text",
                ""
            )

            if not text:
                continue

            await handle_incoming(
                "instagram",
                sender,
                text,
                message.get("mid")
            )

    return {
        "ok": True
    }


async def process_telegram_message(
    message: dict
):

    chat = message.get(
        "chat",
        {}
    )

    user = message.get(
        "from",
        {}
    )

    user_id = user.get(
        "id"
    )

    if not authorized(user_id):
        return

    text = message.get(
        "text",
        ""
    ).strip()

    reply = message.get(
        "reply_to_message"
    )

    if text == "/start":

        await tg_text(
            "🤖 Inbox bot is online.\n\n"
            "Forwarded WhatsApp/Instagram "
            "messages appear here.\n"
            "Reply to an inbox message with "
            "your answer to send it back.\n\n"
            "Commands:\n"
            "/digest - recent unread inbox\n"
            "/todo <text> - add task\n"
            "/todo - list tasks\n"
            "/done <id> - complete task"
        )

        return

    if text == "/digest":

        con = db()

        rows = con.execute(
            """
            SELECT
                platform,
                name,
                external_id,
                last_message

            FROM contacts

            WHERE unread=1

            ORDER BY last_message_at DESC

            LIMIT 10
            """
        ).fetchall()

        con.close()

        if not rows:

            await tg_text(
                "📭 No unread conversations."
            )

        else:

            lines = [
                "📋 Unread inbox:"
            ]

            for r in rows:

                lines.append(
                    f"• {r['platform']} — "
                    f"{r['name'] or r['external_id']}\n"
                    f"  {r['last_message'] or '[non-text]'}"
                )

            await tg_text(
                "\n".join(lines)
            )

        return

    if text.startswith("/todo "):

        item = text[6:].strip()

        if not item:

            await tg_text(
                "Usage: /todo <text>"
            )

            return

        con = db()

        cur = con.execute(
            """
            INSERT INTO todos(
                text,
                created_at
            )
            VALUES (?, ?)
            """,
            (
                item,
                now()
            )
        )

        con.commit()

        con.close()

        await tg_text(
            f"✅ Todo #{cur.lastrowid} added."
        )

        return

    if text == "/todo":

        con = db()

        rows = con.execute(
            """
            SELECT id, text
            FROM todos
            WHERE done=0
            ORDER BY id
            """
        ).fetchall()

        con.close()

        if rows:

            result = "\n".join(
                f"#{r['id']} — {r['text']}"
                for r in rows
            )

        else:

            result = "No open todos."

        await tg_text(
            "📝 Open todos:\n" + result
        )

        return

    if text.startswith("/done "):

        try:

            todo_id = int(
                text[6:].strip()
            )

        except ValueError:

            await tg_text(
                "Usage: /done <id>"
            )

            return

        con = db()

        con.execute(
            """
            UPDATE todos
            SET done=1
            WHERE id=?
            """,
            (
                todo_id,
            )
        )

        con.commit()

        con.close()

        await tg_text(
            f"✅ Todo #{todo_id} marked done."
        )

        return

    if reply:

        tg_message_id = reply.get(
            "message_id"
        )

        con = db()

        row = con.execute(
            """
            SELECT
                m.*,
                c.name

            FROM messages m

            LEFT JOIN contacts c

            ON c.platform=m.platform
            AND c.external_id=m.external_contact_id

            WHERE
                m.telegram_message_id=?
                AND
                m.direction='in'

            ORDER BY m.id DESC

            LIMIT 1
            """,
            (
                tg_message_id,
            )
        ).fetchone()

        con.close()

        if row:

            if row["platform"] == "whatsapp":

                await send_whatsapp(
                    row["external_contact_id"],
                    text
                )

            else:

                await send_instagram(
                    row["external_contact_id"],
                    text
                )

            save_message(
                row["platform"],
                row["external_contact_id"],
                "out",
                text
            )

            con = db()

            con.execute(
                """
                UPDATE contacts
                SET unread=0
                WHERE platform=?
                AND external_id=?
                """,
                (
                    row["platform"],
                    row["external_contact_id"]
                )
            )

            con.commit()

            con.close()

            await tg_text(
                "✅ Sent."
            )

            return

    if text:

        await tg_text(
            "I didn't match that to an action.\n"
            "Reply to an incoming message to "
            "send a response, or use /start."
        )


@app.post("/webhook/telegram")
async def telegram_webhook(
    request: Request
):

    secret = request.headers.get(
        "x-telegram-bot-api-secret-token"
    )

    if (
        TELEGRAM_WEBHOOK_SECRET
        and
        secret != TELEGRAM_WEBHOOK_SECRET
    ):

        raise HTTPException(
            status_code=403,
            detail="Bad Telegram secret"
        )

    data = await request.json()

    if "message" in data:

        await process_telegram_message(
            data["message"]
        )

    return {
        "ok": True
    }
