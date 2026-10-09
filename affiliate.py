"""Affiliate link conversion: turn a raw product URL into YOUR earning link.

Providers are pluggable. Configure AFFILIATE_PROVIDER in .env:
  cuelinks  -> uses the Cuelinks publisher API (needs CUELINKS_API_KEY)
  earnkaro  -> uses the EarnKaro API (needs EARNKARO_API_KEY)
  none      -> passthrough (useful for testing; you earn nothing)
"""
from __future__ import annotations

import os

import httpx

TIMEOUT = httpx.Timeout(15.0)


class AffiliateConverter:
    provider: str = "none"

    def convert(self, url: str) -> str:
        raise NotImplementedError


class CuelinksConverter(AffiliateConverter):
    provider = "cuelinks"
    # Cuelinks link-conversion endpoint (publisher API). Key from cuelinks.com dashboard.
    API_URL = "https://api.cuelinks.com/v2/links"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def convert(self, url: str) -> str:
        try:
            r = httpx.post(
                self.API_URL,
                headers={"Authorization": f"Token {self.api_key}"},
                json={"url": url},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            # Cuelinks returns the converted link under a few possible keys; try each.
            for key in ("short_url", "url", "affiliate_url", "link"):
                if data.get(key):
                    return str(data[key])
        except Exception:
            pass
        return url  # fail-open: original link is better than no link


class EarnkaroConverter(AffiliateConverter):
    provider = "earnkaro"
    # EarnKaro converter endpoint (from EarnKaro public docs, verified Oct 2026):
    # POST https://ekaro-api.affiliaters.in/api/converter/public
    # body: {"deal": "<url>", "convert_option": "convert_only"}
    # Key: EarnKaro dashboard -> API section.
    API_URL = "https://ekaro-api.affiliaters.in/api/converter/public"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def convert(self, url: str) -> str:
        try:
            r = httpx.post(
                self.API_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"deal": url, "convert_option": "convert_only"},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            for key in ("short_url", "url", "affiliate_url", "link", "deal"):
                val = data.get(key)
                if val and val != url:
                    return str(val)
            # some responses nest under "data"
            nested = data.get("data") or {}
            for key in ("short_url", "url", "affiliate_url", "link"):
                if nested.get(key):
                    return str(nested[key])
        except Exception:
            pass
        return url


class PassthroughConverter(AffiliateConverter):
    provider = "none"

    def convert(self, url: str) -> str:
        return url


def get_converter() -> AffiliateConverter:
    provider = os.getenv("AFFILIATE_PROVIDER", "none").strip().lower()
    if provider == "cuelinks" and os.getenv("CUELINKS_API_KEY"):
        return CuelinksConverter(os.getenv("CUELINKS_API_KEY", ""))
    if provider == "earnkaro" and os.getenv("EARNKARO_API_KEY"):
        return EarnkaroConverter(os.getenv("EARNKARO_API_KEY", ""))
    return PassthroughConverter()
