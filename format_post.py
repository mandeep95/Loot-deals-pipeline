"""Deal post formatting: turn a loot candidate into a clean channel post."""
from __future__ import annotations

from patterns import extract_discount_pct, extract_prices, price_drop_pct


def _fmt_inr(value: float) -> str:
    return f"₹{int(value):,}".replace(",", ",")  # Indian grouping handled below


def inr(value: float) -> str:
    """Format with Indian digit grouping: 4999 -> ₹4,999 ; 149999 -> ₹1,49,999."""
    s = str(int(round(value)))
    if len(s) <= 3:
        return f"₹{s}"
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.append(head[-2:])
        head = head[:-2]
    if head:
        parts.append(head)
    return "₹" + ",".join(reversed(parts)) + "," + tail


def build_post(title: str, original_text: str, affiliate_url: str) -> str:
    """Build the channel-ready message. Pure function, unit-tested."""
    prices = extract_prices(original_text)
    pct = extract_discount_pct(original_text) or price_drop_pct(prices)

    lines = ["🔥 <b>LOOT DEAL</b> 🔥", "", f"<b>{title.strip()}</b>", ""]
    if len(prices) >= 2:
        lines.append(f"💰 <b>{inr(min(prices))}</b>  <s>{inr(max(prices))}</s>")
    elif prices:
        lines.append(f"💰 <b>{inr(prices[0])}</b>")
    if pct:
        lines.append(f"📉 <b>{pct}% OFF</b>")
    lines += ["", f"🛒 <a href=\"{affiliate_url}\">Grab the deal here</a>", "", "⚡ <i>Loot deals die fast — order quickly!</i>"]
    return "\n".join(lines)


def build_approval_card(title: str, reasons: dict, post_preview: str) -> str:
    why = []
    if reasons.get("keyword"):
        why.append(f"keyword: “{reasons['keyword']}”")
    if reasons.get("explicit_pct"):
        why.append(f"{reasons['explicit_pct']}% off stated")
    if reasons.get("price_drop_pct"):
        why.append(f"~{reasons['price_drop_pct']}% price drop detected")
    if reasons.get("unverified_url"):
        why.append("shortened link (will resolve on verify)")
    return (
        f"🕵️ <b>New loot candidate</b>\n"
        f"<b>{title.strip()}</b>\n"
        f"Matched: {', '.join(why) or 'pattern'}\n\n"
        f"<i>Preview:</i>\n{post_preview}"
    )


def deal_title(original_text: str, fallback: str = "Loot deal") -> str:
    """Best-effort title: first non-empty line, stripped of URLs."""
    for line in (original_text or "").splitlines():
        line = line.strip()
        if not line or line.lower().startswith("http"):
            continue
        # cut trailing URLs some channels append
        line = line.split("http")[0].strip()
        if line:
            return line[:120]
    return fallback
