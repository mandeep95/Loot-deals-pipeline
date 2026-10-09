"""One-time login helper — run ONCE on your Mac (or any computer with internet).

Creates the Telethon session file and prints it as base64, which you paste
into Render as the READER_SESSION_B64 environment variable. After that the
cron reader on Render can log in without any interactive code.

Run:  python login.py
"""
from __future__ import annotations

import base64
import os

from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
PHONE = os.environ["TG_PHONE"]


def main() -> None:
    with TelegramClient("reader", API_ID, API_HASH) as client:  # noqa: F841
        client.start(phone=PHONE)  # enter the OTP Telegram sends you
        me = client.get_me()
        print(f"Logged in as @{me.username or me.id}. Session saved.")

    with open("reader.session", "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    with open("session.b64.txt", "w") as f:
        f.write(b64)
    print()
    print("Copy the ENTIRE line below into Render env var READER_SESSION_B64:")
    print(b64)


if __name__ == "__main__":
    main()
