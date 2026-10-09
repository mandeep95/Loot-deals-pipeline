"""Loot-pattern detection: decides whether a channel message looks like a loot deal.

Pure functions only — no network, no Telegram. Fully unit-testable.
"""
from __future__ import annotations

import os
import re

# ₹4,999 / Rs. 4999 / INR 4999 / 4,999
PRICE_RE = re.compile(
    r"(?:₹|Rs\.?|INR)\s?([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE
)
# "90% off", "flat 80% discount"
PCT_RE = re.compile(r"(\d{1,3})\s?%\s?(?:off|discount)", re.IGNORECASE)
# plain URLs
URL_RE = re.compile(r"https?://[^\s)>\]]+")
# known Indian storefront hosts (substring match)
STOREFRONTS = (
    "amazon.in", "flipkart.com", "myntra.com", "ajio.com",
    "croma.com", "reliance", "tatacliq.com", "nykaa.com",
    "meesho.com", "snapdeal.com", "vijaysales.com",
)


def _to_float(num: str) -> float:
    return float(num.replace(",", ""))


def extract_prices(text: str) -> list[float]:
    """All rupee prices mentioned in the text, in order of appearance."""
    return [_to_float(m.group(1)) for m in PRICE_RE.finditer(text or "")]


def extract_discount_pct(text: str) -> int | None:
    """Explicit 'NN% off' figure, if present."""
    m = PCT_RE.search(text or "")
    return int(m.group(1)) if m else None


def extract_product_urls(text: str) -> list[str]:
    """URLs that look like product pages on Indian storefronts."""
    urls = []
    for m in URL_RE.finditer(text or ""):
        url = m.group(0).rstrip(".,;!")  # trailing punctuation from chat text
        low = url.lower()
        if any(host in low for host in STOREFRONTS):
            urls.append(url)
    # de-dupe, keep order
    return list(dict.fromkeys(urls))


def load_keywords() -> list[str]:
    raw = os.getenv("LOOT_KEYWORDS", "loot,price error,priceerror,glitch,steal deal")
    return [k.strip().lower() for k in raw.split(",") if k.strip()]


def min_discount_pct() -> int:
    try:
        return int(os.getenv("MIN_DISCOUNT_PCT", "70"))
    except ValueError:
        return 70


def price_drop_pct(prices: list[float]) -> int | None:
    """Implied discount from highest vs lowest price in the message.

    Loot posts usually read like '₹4,999 → ₹499' or 'MRP 4999, loot at 499'.
    """
    if len(prices) < 2:
        return None
    hi, lo = max(prices), min(prices)
    if hi <= 0 or lo >= hi:
        return None
    return round((hi - lo) / hi * 100)


def is_loot(text: str) -> tuple[bool, dict]:
    """Return (matched, reasons). Reasons explain WHY it matched (for the approval card)."""
    text = text or ""
    low = text.lower()
    reasons: dict = {}

    for kw in load_keywords():
        if kw in low:
            reasons["keyword"] = kw
            break

    pct = extract_discount_pct(text)
    if pct is not None and pct >= min_discount_pct():
        reasons["explicit_pct"] = pct

    drop = price_drop_pct(extract_prices(text))
    if drop is not None and drop >= min_discount_pct():
        reasons["price_drop_pct"] = drop

    urls = extract_product_urls(text)
    if urls:
        reasons["product_urls"] = urls

    matched = bool(reasons.get("keyword") or reasons.get("explicit_pct") or reasons.get("price_drop_pct"))
    # A loot post without a product link is useless to us — require one.
    if matched and not urls:
        matched = False
        reasons["no_product_url"] = True
    return matched, reasons
