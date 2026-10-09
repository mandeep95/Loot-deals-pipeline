"""Bot API bot: the poster.

Listens in your private draft group. For every forwarded loot message it:
  1. extracts product URLs
  2. converts them to YOUR affiliate links
  3. builds a clean channel post + an approval card with Approve / Reject buttons
On Approve -> posts to your deals channel. On Reject -> drops it silently.

Run:  python bot.py
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from affiliate import get_converter
from ai_enhance import enhance_post
from format_post import (
    build_approval_card,
    build_post,
    build_simple_post,
    deal_title,
    inr,
)
from patterns import (
    NON_PRODUCT_HOSTS,
    cashback_deal,
    extract_all_urls,
    extract_coupon,
    extract_discount_pct,
    extract_prices,
    extract_product_urls,
    is_loot,
    price_drop_pct,
)
from verify import verify_alive

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("deals-bot")

DRAFT_CHAT_ID = int(os.environ["DRAFT_CHAT_ID"])
DEALS_CHANNEL = os.environ["DEALS_CHANNEL"]

# pending approvals: token -> (product_url, final post text, photo file_id or None)
PENDING: dict[str, tuple[str, str, str | None]] = {}
# de-dupe: product URL -> True (don't repost the same loot twice)
SEEN_URLS: set[str] = set()

converter = get_converter()
log.info("Affiliate provider: %s", converter.provider)


def _kb(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Approve & Post", callback_data=f"ok:{token}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"no:{token}"),
            ]
        ]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Loot-deals poster bot is live.\n"
        "Forward me a loot message in this group and I'll prep it for your channel."
    )


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or msg.chat_id != DRAFT_CHAT_ID:
        return
    text = msg.text or msg.caption or ""
    if not text.strip():
        return

    matched, reasons = is_loot(text)
    urls = reasons.get("product_urls") or extract_product_urls(text)
    if not urls:
        # Last resort: any non-Telegram URL at all (covers shorteners we
        # haven't catalogued). Only truly link-less messages get skipped.
        urls = [u for u in extract_all_urls(text)
                if not any(h in u.lower() for h in NON_PRODUCT_HOSTS)]
    if not urls:
        # No link at all — nothing we can post. Keep the diagnostic skip.
        sig = reasons.get("signals", {})
        seen = []
        if sig.get("keyword"):
            seen.append(f"keyword “{sig['keyword']}”")
        if sig.get("explicit_pct"):
            seen.append(f"{sig['explicit_pct']}% off")
        if sig.get("price_drop_pct"):
            seen.append(f"~{sig['price_drop_pct']}% price drop")
        if sig.get("prices"):
            seen.append("prices " + "/".join(f"₹{int(p):,}" for p in sig["prices"][:4]))
        detail = ("I saw: " + ", ".join(seen)) if seen else "I couldn't find a deal pattern in it"
        await msg.reply_text(
            f"Skipped — no product link found. {detail}.\n"
            "Forward the message with the product link as plain text.")
        return

    url = urls[0]
    if url in SEEN_URLS:
        await msg.reply_text("Already posted this product — skipping duplicate.")
        return

    affiliate_url = converter.convert(url)
    title = deal_title(text)
    photo_id = msg.photo[-1].file_id if msg.photo else None

    prices = extract_prices(text)
    pct = extract_discount_pct(text) or price_drop_pct(prices)

    if matched:
        # Loot path: full formatting + live-price verification.
        template_post = build_post(title, text, affiliate_url)
        expected = min(prices) if prices else None
        status, note = verify_alive(url, expected)
        verdict_icon = {"alive": "🟢", "dead": "🔴", "unknown": "🟡"}[status]
        deal_info = ""
        cb_price, cb_amt, cb_pct = cashback_deal(text)
        coupon = extract_coupon(text)
        if cb_pct is not None:
            deal_info = f"Price {inr(cb_price)}, {cb_pct}% CASHBACK ({inr(cb_amt)} back)"
        else:
            if prices and len(prices) >= 2:
                deal_info = f"Price {inr(min(prices))} (was {inr(max(prices))})"
            elif prices:
                deal_info = f"Price {inr(prices[0])}"
            if pct:
                deal_info += f", {pct}% {'CASHBACK' if 'cashback' in text.lower() else 'OFF'}"
        if coupon:
            deal_info += f", {inr(coupon)} off coupon"
    else:
        # Simple-deal path: user forwarded it, so post it plainly.
        template_post = build_simple_post(title, affiliate_url)
        status, note, deal_info = None, "", ""

    # AI enhancement (fail-open): rewrite the body, affiliate link appended
    # afterwards so the model can never mangle it. HTML-escape AI text.
    ai_body = enhance_post(text, title, deal_info.strip(", "))
    if ai_body:
        import html as _html

        post = _html.escape(ai_body) + f"\n\n🛒 <a href=\"{affiliate_url}\">Grab the deal here</a>"
        preview_label = "<i>Preview (✨ AI-enhanced):</i>"
    else:
        post = template_post
        preview_label = "<i>Preview:</i>"

    if matched:
        card = build_approval_card(title, reasons, post)
        card += f"\n\n{verdict_icon} <b>Live check:</b> {note}"
        if status == "dead":
            card += "\n<i>Tip: this one looks expired — Reject is probably right.</i>"
    else:
        card = build_approval_card(title, reasons, post, simple=True)
    card = card.replace("<i>Preview:</i>", preview_label)

    token = f"{msg.message_id}"
    PENDING[token] = (url, post, photo_id)
    await msg.reply_text(card, parse_mode="HTML", reply_markup=_kb(token),
                         disable_web_page_preview=True)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    action, _, token = (query.data or "").partition(":")
    item = PENDING.pop(token, None)
    if item is None:
        await query.edit_message_text("This approval expired.")
        return
    url, post, photo_id = item
    if action == "ok":
        if photo_id:
            # keep the product image: photo + formatted caption (not text-only)
            await context.bot.send_photo(DEALS_CHANNEL, photo=photo_id,
                                         caption=post, parse_mode="HTML")
        else:
            await context.bot.send_message(DEALS_CHANNEL, post, parse_mode="HTML",
                                           disable_web_page_preview=False)
        SEEN_URLS.add(url)  # don't repost the same product twice
        await query.edit_message_text("✅ Posted to your channel.")
        log.info("Posted a deal to %s", DEALS_CHANNEL)
    else:
        await query.edit_message_text("❌ Rejected — not posted.")


def main() -> None:
    app = Application.builder().token(os.environ["BOT_TOKEN"]).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, on_message))
    app.add_handler(CallbackQueryHandler(on_button))
    log.info("Bot polling started.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
