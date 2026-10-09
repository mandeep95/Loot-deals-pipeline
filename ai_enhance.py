"""AI post enhancement with automatic provider fallback.

Providers (tried in order when AI_PROVIDER=auto):
  1. zai  — Z.AI (https://api.z.ai), key in ZAI_API_KEY, model in ZAI_MODEL
  2. groq — Groq free tier, key in GROQ_API_KEY, model in GROQ_MODEL

Set AI_PROVIDER=zai or groq to pin one. Fail-open: any failure returns None
and the caller falls back to the template post.

The affiliate link is NEVER given to the AI — it's appended afterwards, so
the model can't mangle or hallucinate URLs.

Standard library only (urllib). Failures log to stderr (visible in
Render logs) for debugging.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

PROVIDERS = {
    "zai": {
        "url": "https://api.z.ai/api/paas/v4/chat/completions",
        "key_env": "ZAI_API_KEY",
        "model_env": "ZAI_MODEL",
        "default_model": "glm-4.5-air",
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "key_env": "GROQ_API_KEY",
        "model_env": "GROQ_MODEL",
        "default_model": "llama-3.1-8b-instant",
    },
}

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


def _provider_order() -> list[str]:
    """Configured providers in try-order. AI_PROVIDER pins one; 'auto'
    tries zai then groq, skipping any without a key."""
    pinned = os.getenv("AI_PROVIDER", "auto").strip().lower()
    if pinned in PROVIDERS:
        names = [pinned]
    else:
        names = list(PROVIDERS)
    return [n for n in names
            if os.getenv(PROVIDERS[n]["key_env"], "").strip()]


def _try_provider(name: str, prompt: str) -> str | None:
    cfg = PROVIDERS[name]
    key = os.getenv(cfg["key_env"], "").strip()
    model = os.getenv(cfg["model_env"], "").strip() or cfg["default_model"]
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 400,
    }).encode()
    req = urllib.request.Request(
        cfg["url"],
        data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.load(r)
        text = (data["choices"][0]["message"]["content"] or "").strip()
        if not text:
            _log(f"{name}: empty response")
            return None
        return text
    except urllib.error.HTTPError as e:
        detail = e.read()[:200].decode("utf-8", "replace")
        _log(f"{name}: HTTP {e.code} {detail}")
        return None
    except Exception as e:  # network etc. — fail-open
        _log(f"{name}: {type(e).__name__}: {str(e)[:150]}")
        return None


def enhance_post(raw_text: str, title: str, deal_info: str = "") -> str | None:
    """Return AI-rewritten post body, or None to use the template instead."""
    prompt = (
        f"Product: {title}\n"
        + (f"Deal facts: {deal_info}\n" if deal_info else "")
        + f"\nRaw message:\n{(raw_text or '')[:1500]}"
    )
    for name in _provider_order():
        result = _try_provider(name, prompt)
        if result:
            _log(f"{name}: enhanced OK")
            return result
    return None
