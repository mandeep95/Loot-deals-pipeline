"""AI post enhancement via Groq (free tier, OpenAI-compatible API).

Takes the raw forwarded deal text + structured facts and rewrites it into a
short, punchy Telegram deal post. Fail-open: returns None on any error (or
when no key is configured) and the caller falls back to the template post.

The affiliate link is NEVER given to the AI — it's appended afterwards, so
the model can't mangle or hallucinate URLs.

Uses only the standard library (urllib) so there's no extra dependency.
Failures are logged to stderr (visible in Render logs) for debugging.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")  # fast + free

SYSTEM_PROMPT = """You rewrite raw forwarded deal messages into short, punchy Telegram deal posts.
Rules:
- Output ONLY the post text, no explanations or quotes.
- Keep it under 500 characters.
- First line: hook (product + the deal).
- Include the price and discount exactly as given in the deal info; never invent prices.
- 2-4 emojis max, tasteful. No hashtags.
- Do NOT include any URL — the purchase link is added separately.
- Match the input language (English or Hinglish)."""


def _log(msg: str) -> None:
    print(f"[ai_enhance] {msg}", file=sys.stderr, flush=True)


def enhance_post(raw_text: str, title: str, deal_info: str = "") -> str | None:
    """Return AI-rewritten post body, or None to use the template instead."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        prompt = (
            f"Product: {title}\n"
            + (f"Deal facts: {deal_info}\n" if deal_info else "")
            + f"\nRaw message:\n{(raw_text or '')[:1500]}"
        )
        body = json.dumps({
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 400,
        }).encode()
        req = urllib.request.Request(
            GROQ_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.load(r)
        text = (data["choices"][0]["message"]["content"] or "").strip()
        if not text:
            _log("empty response from Groq")
            return None
        return text
    except Exception as e:  # fail-open: template post is used instead
        _log(f"failed: {type(e).__name__}: {str(e)[:200]}")
        return None
