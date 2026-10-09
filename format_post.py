"""Deal post formatting: turn a loot candidate into a clean channel post."""
from __future__ import annotations

from patterns import (
    cashback_deal,
    extract_coupon,
    extract_discount_pct,
    extract_prices,
    price_drop_pct,
)


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
    is_cashback = "cashback" in (original_text or "").lower()
    cb_price, cb_amt, cb_pct = cashback_deal(original_text)
    coupon = extract_coupon(original_text)

    lines = ["🔥 <b>LOOT DEAL</b> 🔥", "", f"<b>{title.strip()}</b>", ""]
    if cb_pct is not None:
        # Cashback: show the real price + the true cashback %, never a fake drop.
        lines.append(f"💰 <b>{inr(cb_price)}</b>")
        lines.append(f"📉 <b>{cb_pct}% CASHBACK</b> ({inr(cb_amt)} back)")
    else:
        pct = extract_discount_pct(original_text) or price_drop_pct(prices)
        if len(prices) >= 2:
            lines.append(f"💰 <b>{inr(min(prices))}</b>  <s>{inr(max(prices))}</s>")
        elif prices:
            lines.append(f"💰 <b>{inr(prices[0])}</b>")
        if pct:
            label = "CASHBACK" if is_cashback else "OFF"
            lines.append(f"📉 <b>{pct}% {label}</b>")
    if coupon:
        lines.append(f"🎟️ Apply {inr(coupon)} off coupon at checkout")
    lines += ["", f"🛒 <a href=\"{affiliate_url}\">Grab the deal here</a>", "", "⚡ <i>Loot deals die fast — order quickly!</i>"]
    return "\n".join(lines)


def build_simple_post(title: str, affiliate_url: str) -> str:
    """Plain deal post for forwards that didn't match a loot pattern."""
    return (
        f"<b>{title.strip()}</b>\n\n"
        f"🛒 <a href=\"{affiliate_url}\">Grab the deal here</a>"
    )


def build_approval_card(title: str, reasons: dict, post_preview: str,
                        simple: bool = False) -> str:
    if simple:
        return (
            f"📦 <b>New deal</b> (no loot pattern matched — posting as simple deal)\n"
            f"<b>{title.strip()}</b>\n\n"
            f"<i>Preview:</i>\n{post_preview}"
        )
    why = []
    if reasons.get("keyword"):
        why.append(f"keyword: “{reasons['keyword']}”")
    if reasons.get("explicit_pct"):
        why.append(f"{reasons['explicit_pct']}% off stated")
    if reasons.get("price_drop_pct"):
        why.append(f"~{reasons['price_drop_pct']}% price drop detected")
    if reasons.get("cashback_pct"):
        why.append(f"{reasons['cashback_pct']}% cashback detected")
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
