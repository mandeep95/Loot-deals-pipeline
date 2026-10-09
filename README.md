# Loot-Deal Pipeline (Level 2: semi-auto)

Watches loot finder channels 24×7 as your account, forwards loot candidates to a
private group, swaps in **your** affiliate links, formats the post, and asks for
your one-tap approval before publishing to your channel.

```
finder channels ──▶ reader.py (your account, Telethon)
                        │ forwards loot-pattern matches
                        ▼
              private draft group ◀── you can also forward manually
                        │ bot.py (Bot API)
                        │ 1. extract product link
                        │ 2. convert to YOUR affiliate link
                        │ 3. verify the loot price is still live (🟢/🔴/🟡)
                        │ 4. format post + approval card
                        ▼
              you tap ✅ Approve ──▶ posted to your deals channel
```

## One-time setup (~15 minutes)

### 1. Create the bot (2 min)
1. Open Telegram, message **@BotFather**, send `/newbot`, follow the prompts.
2. Copy the bot token → `BOT_TOKEN` in `.env`.

### 2. Create your groups/channel
1. Create a **private group** (only you) — this is the draft room.
2. Add your bot to it as admin.
3. Create your **public deals channel**, add the bot as admin (needs "Post Messages").
4. Get IDs: forward any message from the group to **@userinfobot** → `DRAFT_CHAT_ID`.
   Channel can be `@yourchannelname` directly → `DEALS_CHANNEL`.

### 3. Telegram API credentials for the reader (3 min)
1. Go to https://my.telegram.org → log in with your number → **API development tools**.
2. Create an app, copy **api_id** and **api_hash** → `TG_API_ID`, `TG_API_HASH`.
3. `TG_PHONE` = your number with country code, e.g. `+919876543210`.
4. `SOURCE_CHANNELS` = comma-separated `@usernames` of finder channels you're in.
5. `READER_TARGET_CHAT` = same draft group id as `DRAFT_CHAT_ID`.

### 4. Affiliate links (5 min)
- Sign up at **Cuelinks** (or EarnKaro), grab your API key from the dashboard.
- Set `AFFILIATE_PROVIDER=cuelinks` and `CUELINKS_API_KEY=...`.
- Not ready yet? Leave `AFFILIATE_PROVIDER=none` — everything works, links just
  won't earn commission until you add the key.

### 5. Install & run
```bash
cd deals-pipeline
cp .env.example .env        # then fill in your values
pip install -r requirements.txt
python -m pytest tests/ -q  # sanity check (or: python tests/run_tests.py)

# terminal 1 — the poster bot
python bot.py
# terminal 2 — the channel watcher (first run asks for your Telegram login code)
python reader.py
```

For 24×7 running, use `nohup`, `tmux`, or a tiny VPS. Your Mac works fine too —
just keep the two terminals alive.

## Hosting — Render free tier (no card needed) ⭐ recommended for you

Render's free tier sleeps, so the pipeline runs on **triggers** instead of 24×7
processes. Two free services, zero card:

| Piece | How it runs on Render | Trigger |
|---|---|---|
| `webhook.py` (poster bot) | Web service, sleeps when idle | Wakes on every Telegram update (forward, ✅/❌ tap) |
| `reader_cron.py` (watcher) | Cron job, exits after each run | Every 12 minutes |

Trade-off vs a 24×7 VM: loot detection lags ~12–15 min + ~30s cold start on
wake. Fine for loots that live 30+ min; you'll miss some 5-minute flash loots.

### Deploy steps
1. **One-time login (on your computer, 2 min):**
   ```bash
   pip install -r requirements.txt
   python login.py        # enter the OTP Telegram sends you
   ```
   It prints a long base64 line and saves `session.b64.txt`.
2. **Push this folder to a GitHub repo** (Render deploys from git).
3. **Render dashboard → New → Blueprint →** point at the repo (uses `render.yaml`).
4. Fill the `sync: false` env vars: `BOT_TOKEN`, `DRAFT_CHAT_ID` (= your user id),
   `TG_API_ID`, `TG_API_HASH`, `READER_TARGET_CHAT`, `READER_SESSION_B64`
   (the base64 from step 1), `EARNKARO_API_KEY` (when you have it).
5. After the web service deploys, copy its URL (`https://deals-bot.onrender.com`),
   set `WEBHOOK_URL` to it, redeploy once. The bot registers the webhook itself.
6. Make sure `@Dealsbydeep_bot` is admin of your channel (already done ✅).

Check the cron logs in Render dashboard to see each run's forwards.

## Hosting — Oracle Cloud Always Free (24×7, needs card verification)

The reader needs 24×7 uptime (it's a live connection to Telegram). Free Render /
Railway / Replit all sleep — not suitable. Oracle's Always Free tier gives you a
VM that never expires and never bills.

1. Sign up at oracle.com/cloud/free — needs a card for verification (not charged;
   note: some Indian debit cards fail verification; a credit card usually works).
2. Create an **Ampere A1** VM, Ubuntu 22.04/24.04 (the free shape).
3. Upload the zip: `scp deals-pipeline.zip ubuntu@<vm-ip>:~/`
4. SSH in and run: `bash ~/setup-vm.sh` — wait, no: the script is inside the zip.
   Run: `unzip -o ~/deals-pipeline.zip -d ~/ && bash ~/deals-pipeline/setup-vm.sh`
5. First run the reader once manually for the Telegram login code, then enable
   the services (the script prints the exact commands).

No card / signup fails? Fallback: **Termux on your Android** — install Termux,
`pkg install python`, unzip, `pip install -r requirements.txt`, run both scripts.
Free and no signup, but only runs while the phone is on and Termux stays alive —
fine for testing, not true 24×7.

## Tuning
- `MIN_DISCOUNT_PCT` (default 70): how big a drop counts as loot.
- `LOOT_KEYWORDS`: extra trigger words, comma-separated.
- `MAX_FORWARDS_PER_HOUR` (default 12): reader rate limit — keeps your account safe.
- Duplicate products are never reposted twice (tracked in memory per run).

## Safety
- The reader is read-mostly: it never posts or messages anyone. Don't raise the
  rate limit aggressively — restricted accounts are hard to recover.
- `reader.session` and `.env` contain account secrets. Never share or commit them.
- Nothing reaches your channel without your ✅ tap. That filter is the product.
