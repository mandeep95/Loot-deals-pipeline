"""Verify-alive check: is the loot price still live on the product page?

Best-effort and FAIL-OPEN: if the page can't be fetched (bot protection,
network issue), we return "unknown" and the human approval card shows a
"couldn't verify — check manually" note. A stale/failed check never blocks
a deal; it only adds information to the approval card.

This keeps the human tap as the real filter, per the build spec.
"""
from __future__ import annotations

import re

import httpx

from patterns import PRICE_RE

TIMEOUT = httpx.Timeout(12.0)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

# JSON-LD / meta price hints sites sometimes embed
META_PRICE_RE = re.compile(
    r'"price"\s*:\s*"?([\d,]+(?:\.\d{1,2})?)"?', re.IGNORECASE
)


def fetch_page_prices(url: str) -> list[float]:
    """Prices found on the live product page. Empty list = couldn't determine."""
    try:
        r = httpx.get(url, headers=HEADERS, timeout=TIMEOUT, follow_redirects=True)
        if r.status_code != 200 or not r.text:
            return []
        prices = [_to_float(m.group(1)) for m in PRICE_RE.finditer(r.text[:200_000])]
        prices += [_to_float(m.group(1)) for m in META_PRICE_RE.finditer(r.text[:200_000])]
        # drop absurd values (page furniture, EMI totals)
        prices = [p for p in prices if 10 <= p <= 10_000_000]
        return sorted(set(prices))
    except Exception:
        return []


def _to_float(num: str) -> float:
    return float(num.replace(",", ""))


def verify_alive(url: str, expected_loot_price: float | None) -> tuple[str, str]:
    """Return (status, note). status in {"alive", "dead", "unknown"}.

    - alive:   page shows a price within ±5% of the expected loot price
    - dead:    page loads but the loot price is gone (or page unreachable as product)
    - unknown: couldn't fetch/parse — human should check manually
    """
    page_prices = fetch_page_prices(url)
    if not page_prices:
        return "unknown", "Couldn't verify automatically — please check the link manually."
    if expected_loot_price is None:
        return "unknown", f"Page reachable, prices seen from {page_prices[0]:,.0f}."
    lo, hi = expected_loot_price * 0.95, expected_loot_price * 1.05
    if any(lo <= p <= hi for p in page_prices):
        return "alive", f"Loot price still live on page (₹{expected_loot_price:,.0f})."
    return "dead", (
        f"Loot price gone — page now shows from ₹{page_prices[0]:,.0f}. "
        "Likely expired; rejecting is safer."
    )
