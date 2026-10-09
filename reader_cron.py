"""Cron reader: poll-based channel watcher for Render's free tier.

Instead of a persistent connection (which free Render can't do — services
sleep), this script wakes up on a schedule, grabs recent messages from each
source channel, forwards loot matches to your draft chat, and exits.

State (last-checked timestamps + seen URLs) lives in state.json next to this
file. Render's disk persists between cron runs within a deploy; on a fresh
deploy we fall back to a 20-minute lookback window, so the worst case is a
few duplicate approval cards, never missed loots.

Run:  python reader_cron.py        (Render cron: every 12 minutes)
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from telethon import TelegramClient

from patterns import is_loot

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("deals-reader-cron")

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
TARGET = os.environ["READER_TARGET_CHAT"]
SOURCES = [s.strip() for s in os.getenv("SOURCE_CHANNELS", "").split(",") if s.strip()]

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
LOOKBACK_MINUTES = int(os.getenv("CRON_LOOKBACK_MINUTES", "20"))
MAX_FORWARDS_PER_RUN = int(os.getenv("MAX_FORWARDS_PER_RUN", "10"))


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_check": {}, "seen_urls": []}


def save_state(state: dict) -> None:
    state["seen_urls"] = state.get("seen_urls", [])[-500:]  # cap growth
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def ensure_session() -> None:
    """Render can't hold binary secret files, so the session travels as base64
    in READER_SESSION_B64 (produced by login.py)."""
    if os.path.exists("reader.session"):
        return
    b64 = os.getenv("READER_SESSION_B64", "")
    if not b64:
        raise SystemExit(
            "No reader.session and no READER_SESSION_B64. Run login.py once on "
            "your computer and paste the base64 into Render env vars."
        )
    with open("reader.session", "wb") as f:
        f.write(base64.b64decode(b64))
    log.info("Session restored from READER_SESSION_B64.")


async def main() -> None:
    if not SOURCES:
        raise SystemExit("Set SOURCE_CHANNELS in env.")
    ensure_session()
    state = load_state()
    last_check = state.setdefault("last_check", {})
    seen = set(state.setdefault("seen_urls", []))
    now = datetime.now(timezone.utc)
    forwarded = 0

    client = TelegramClient("reader", API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        raise SystemExit("Session invalid. Re-run login.py and update READER_SESSION_B64.")

    for src in SOURCES:
        if forwarded >= MAX_FORWARDS_PER_RUN:
            break
        try:
            entity = await client.get_entity(src)
        except Exception as exc:  # noqa: BLE001
            log.warning("Skipping source %s: %s", src, exc)
            continue
        since = last_check.get(src)
        cutoff = (
            datetime.fromisoformat(since)
            if since
            else now - timedelta(minutes=LOOKBACK_MINUTES)
        )
        try:
            async for msg in client.iter_messages(entity, limit=40):
                if msg.date.replace(tzinfo=timezone.utc) <= cutoff:
                    break
                text = msg.raw_text or ""
                matched, reasons = is_loot(text)
                if not matched:
                    continue
                urls = reasons.get("product_urls", [])
                if urls and urls[0] in seen:
                    continue
                try:
                    await msg.forward_to(TARGET)
                    forwarded += 1
                    if urls:
                        seen.add(urls[0])
                    log.info("Forwarded loot from %s (matched: %s)", src, list(reasons))
                except Exception as exc:  # noqa: BLE001
                    log.warning("Forward failed: %s", exc)
                if forwarded >= MAX_FORWARDS_PER_RUN:
                    break
        except Exception as exc:  # noqa: BLE001
            log.warning("Read failed for %s: %s", src, exc)
        last_check[src] = now.isoformat()

    state["seen_urls"] = sorted(seen)
    save_state(state)
    await client.disconnect()
    log.info("Cron run done. Forwarded %d loot candidates.", forwarded)


if __name__ == "__main__":
    asyncio.run(main())
