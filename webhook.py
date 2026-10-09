"""Webhook bot + cron-reader trigger in one free Render web service.

Render's free tier has no cron jobs, so both halves live here:
  - POST /telegram  -> Telegram Bot API webhook (forwards, approve/reject taps).
                      Wakes the sleeping service on demand.
  - GET  /reader?secret=... -> runs the channel poll (reader_cron.main()).
                      Hit every 12 min by a free cron-job.org job.
  - GET  /health     -> liveness check.

Secrets: BOT_TOKEN, DRAFT_CHAT_ID, DEALS_CHANNEL, CRON_SECRET,
         TG_API_ID, TG_API_HASH, READER_TARGET_CHAT, SOURCE_CHANNELS,
         READER_SESSION_B64 (from login.py), affiliate keys (optional).

Run:  python webhook.py   (needs PORT and WEBHOOK_URL env vars)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import bot as bot_handlers  # start / on_message / on_button

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("deals-webhook")

PORT = int(os.environ.get("PORT", "8443"))
WEBHOOK_URL = os.environ["WEBHOOK_URL"].rstrip("/")
CRON_SECRET = os.environ.get("CRON_SECRET", "")
APPROVALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "approvals.json")

app = Application.builder().token(os.environ["BOT_TOKEN"]).build()

_reader_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None


def _load_approvals() -> None:
    try:
        with open(APPROVALS_FILE) as f:
            for token, post in json.load(f).items():
                bot_handlers.PENDING.setdefault(token, ("", post))
    except (FileNotFoundError, json.JSONDecodeError):
        pass


def _save_approvals() -> None:
    try:
        with open(APPROVALS_FILE, "w") as f:
            json.dump({t: post for t, (_u, post) in bot_handlers.PENDING.items()}, f)
    except OSError:
        pass


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _load_approvals()
    await bot_handlers.on_message(update, context)
    _save_approvals()


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _load_approvals()
    await bot_handlers.on_button(update, context)
    _save_approvals()


def _run_reader_async() -> None:
    """Run the channel poll in a fire-and-forget thread (skips if one is active)."""
    if not _reader_lock.acquire(blocking=False):
        log.info("reader already running; skipping overlapping trigger")
        return

    def _target() -> None:
        try:
            import reader_cron  # lazy: needs reader env vars, not bot env
            asyncio.run(reader_cron.main())
        except Exception as exc:  # noqa: BLE001
            log.warning("reader run failed: %s", exc)
        finally:
            _reader_lock.release()

    threading.Thread(target=_target, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes = b"") -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            try:
                self.wfile.write(body)
            except BrokenPipeError:
                pass

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/telegram":
            self._send(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400)
            return
        update = Update.de_json(data, app.bot)
        if _loop is not None:
            asyncio.run_coroutine_threadsafe(app.process_update(update), _loop)
        self._send(200, b'{"ok":true}')

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/reader":
            secret = parse_qs(parsed.query).get("secret", [""])[0]
            if not CRON_SECRET or secret != CRON_SECRET:
                self._send(403, b'{"ok":false,"error":"forbidden"}')
                return
            _run_reader_async()
            self._send(200, b'{"ok":true,"started":true}')
        elif parsed.path in ("/", "/health"):
            self._send(200, b'{"ok":true,"service":"deals-bot"}')
        else:
            self._send(404)

    def log_message(self, *args) -> None:  # noqa: ANN002, ANN202
        pass


async def main() -> None:
    global _loop
    app.add_handler(CommandHandler("start", bot_handlers.start))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, on_message))
    app.add_handler(CallbackQueryHandler(on_button))
    await app.initialize()
    await app.start()
    await app.bot.set_webhook(f"{WEBHOOK_URL}/telegram")
    log.info("Webhook set to %s/telegram", WEBHOOK_URL)
    _loop = asyncio.get_running_loop()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    log.info("Serving on port %d", PORT)
    await asyncio.to_thread(server.serve_forever)


if __name__ == "__main__":
    asyncio.run(main())
