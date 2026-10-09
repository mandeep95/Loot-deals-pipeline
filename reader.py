"""Telethon reader: watches your source channels as YOUR account.

This is a "userbot" — it logs in with your own Telegram account (like Telegram
Web does) and only READS messages from channels you're already subscribed to.
When a message matches the loot patterns, it forwards it to your private draft
group, where bot.py takes over (link swap -> format -> your approval -> post).

Safety notes:
  - Read-mostly and gentle: it never posts, never messages strangers, and
    forwards at most a few messages per hour. Keep it that way — aggressive
    automation is what gets accounts restricted.
  - First run asks for the login code Telegram sends to your phone. The
    session file (reader.session) is created locally — never share it.
  - Your .env holds API_ID/API_HASH: treat them like passwords.

Run:  python reader.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

from dotenv import load_dotenv
from telethon import TelegramClient, events

from patterns import is_loot

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("deals-reader")

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
PHONE = os.environ["TG_PHONE"]
TARGET = os.environ["READER_TARGET_CHAT"]  # your private draft group (username or id)

SOURCES = [s.strip() for s in os.getenv("SOURCE_CHANNELS", "").split(",") if s.strip()]

# Gentle rate limit: max forwards per hour (protects your account standing)
MAX_FORWARDS_PER_HOUR = int(os.getenv("MAX_FORWARDS_PER_HOUR", "12"))
_forward_times: list[float] = []


def _rate_ok() -> bool:
    now = time.time()
    while _forward_times and now - _forward_times[0] > 3600:
        _forward_times.pop(0)
    return len(_forward_times) < MAX_FORWARDS_PER_HOUR


async def main() -> None:
    if not SOURCES:
        raise SystemExit("Set SOURCE_CHANNELS in .env (comma-separated @usernames).")

    client = TelegramClient("reader", API_ID, API_HASH)
    await client.start(phone=PHONE)  # first run: enter the code Telegram sends you
    me = await client.get_me()
    log.info("Logged in as %s.", me.username or me.id)

    # Resolve sources; skip anything we can't access (private group we're not in,
    # typo'd username, etc.) instead of crashing.
    resolved = []
    for src in SOURCES:
        try:
            entity = await client.get_entity(src)
            resolved.append(entity)
            log.info("Watching: %s", getattr(entity, "title", None) or src)
        except Exception as exc:  # noqa: BLE001
            log.warning("Skipping source %s: %s", src, exc)
    if not resolved:
        raise SystemExit("No watchable sources. Check SOURCE_CHANNELS in .env.")

    @client.on(events.NewMessage(chats=resolved))
    async def on_loot(event):  # noqa: ANN001, ANN202
        text = event.raw_text or ""
        matched, reasons = is_loot(text)
        if not matched:
            return
        if not _rate_ok():
            log.warning("Rate limit hit — skipping a loot candidate.")
            return
        try:
            await event.forward_to(TARGET)
            _forward_times.append(time.time())
            log.info("Forwarded loot candidate (matched: %s)", list(reasons.keys()))
        except Exception as exc:  # noqa: BLE001
            log.warning("Forward failed: %s", exc)

    log.info("Reader running. Press Ctrl+C to stop.")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
