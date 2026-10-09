"""Webhook bot: the same poster logic as bot.py, but wakes on demand.

Render's free web services sleep after inactivity and wake on incoming HTTP
requests — perfect for Telegram webhooks. Set WEBHOOK_URL to your Render URL
(https://<name>.onrender.com); python-telegram-bot registers it automatically.

The in-memory PENDING approvals don't survive a sleep/wake cycle, so approvals
also persist to approvals.json on disk (survives sleeps; lost only on redeploy,
in which case the card just says "expired" — safe).

Run locally:  WEBHOOK_URL=https://<your-tunnel> python webhook.py
On Render:    startCommand: python webhook.py   (PORT + WEBHOOK_URL from env)
"""
from __future__ import annotations

import json
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

import bot as bot_handlers  # reuses start / on_message / on_button / _kb

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("deals-webhook")

APPROVALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "approvals.json")


def _load_approvals() -> None:
    try:
        with open(APPROVALS_FILE) as f:
            for token, post in json.load(f).items():
                bot_handlers.PENDING.setdefault(token, ("", post))
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def _save_approvals() -> None:
    try:
        data = {t: post for t, (_url, post) in bot_handlers.PENDING.items()}
        with open(APPROVALS_FILE, "w") as f:
            json.dump(data, f)
    except OSError:
        pass


# persist approvals across sleep/wake: wrap the original handlers
_orig_on_message = bot_handlers.on_message
_orig_on_button = bot_handlers.on_button


async def on_message(update: Update, context) -> None:  # noqa: ANN001, ANN202
    _load_approvals()
    await _orig_on_message(update, context)
    _save_approvals()


async def on_button(update: Update, context) -> None:  # noqa: ANN001, ANN202
    _load_approvals()
    await _orig_on_button(update, context)
    _save_approvals()


def main() -> None:
    webhook_url = os.environ["WEBHOOK_URL"].rstrip("/")
    port = int(os.environ.get("PORT", "8443"))
    app = Application.builder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", bot_handlers.start))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, on_message))
    app.add_handler(CallbackQueryHandler(on_button))
    log.info("Webhook bot starting on port %d -> %s", port, webhook_url)
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=webhook_url,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
