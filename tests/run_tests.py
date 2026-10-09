"""Unit tests for the loot pipeline's pure logic (no network, no Telegram).

Run:  python -m pytest tests/ -q   (or: python tests/run_tests.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MIN_DISCOUNT_PCT", "70")
os.environ.setdefault("LOOT_KEYWORDS", "loot,price error,priceerror,glitch,steal deal")

from format_post import build_post, deal_title, inr  # noqa: E402
from patterns import (  # noqa: E402
    extract_discount_pct,
    extract_prices,
    extract_product_urls,
    is_loot,
    price_drop_pct,
)

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS {name}")
    else:
        failed += 1
        print(f"  FAIL {name}")


print("== patterns ==")

check("extract_prices finds ₹ and Rs amounts",
      extract_prices("MRP ₹4,999 loot at Rs. 499") == [4999.0, 499.0])

check("price_drop_pct 4999 -> 499 is 90",
      price_drop_pct([4999.0, 499.0]) == 90)

check("explicit 80% off detected",
      extract_discount_pct("Flat 80% off today") == 80)

check("product urls: only storefront links kept",
      extract_product_urls("buy https://www.flipkart.com/item/p/abc and https://random.blog/x")
      == ["https://www.flipkart.com/item/p/abc"])

check("loot keyword + link matches",
      is_loot("LOOT deal! boAt earbuds ₹4,999 at ₹499 https://www.amazon.in/dp/XYZ")[0] is True)

check("big drop without keyword matches",
      is_loot("boAt Airdopes MRP ₹4,999 now ₹499 https://www.flipkart.com/x")[0] is True)

check("explicit 85% off matches",
      is_loot("Flat 85% off on shoes https://www.myntra.com/shoe/123")[0] is True)

check("small 20% discount does NOT match",
      is_loot("Nice 20% off on tees https://www.myntra.com/tee/1")[0] is False)

check("loot keyword but NO product link does NOT match",
      is_loot("LOOT LOOT price error guys hurry")[0] is False)

check("ordinary chat message does NOT match",
      is_loot("Hey, did you watch the match yesterday?")[0] is False)

print("== formatting ==")

check("inr groups Indian style", inr(149999) == "₹1,49,999" and inr(499) == "₹499")

post = build_post(
    "boAt Airdopes 141",
    "LOOT! boAt Airdopes MRP ₹4,999 at ₹499 https://www.flipkart.com/x",
    "https://aff.link/abc",
)
check("post has LOOT header", "LOOT DEAL" in post)
check("post shows loot + mrp prices", "₹499" in post and "₹4,999" in post)
check("post shows 90% off", "90% OFF" in post)
check("post carries affiliate link", "https://aff.link/abc" in post)

check("deal_title picks first text line",
      deal_title("boAt Airdopes LOOT\n₹499 only\nhttps://x") == "boAt Airdopes LOOT")

print("== short/affiliate links ==")

check("bit.ly link accepted as product url",
      extract_product_urls("Loot! ₹499 https://bit.ly/3xyzAB") == ["https://bit.ly/3xyzAB"])

check("amzn.to link accepted",
      extract_product_urls("deal https://amzn.to/4abc") == ["https://amzn.to/4abc"])

check("t.me link never a product url",
      extract_product_urls("join https://t.me/somechannel") == [])

check("loot with ONLY a short link matches",
      is_loot("🔥 LOOT 🔥 boAt Airdopes MRP ₹4,999 at ₹499 👉 https://bit.ly/3xyzAB")[0] is True)

check("unverified_url reason set for short link",
      is_loot("LOOT ₹499 https://bit.ly/3x")[1].get("unverified_url") is True)

print("== cashback loots ==")

check("90% cashback detected as pct",
      extract_discount_pct("Grab Them at 90% Cashback") == 90)

check("fkm.asia accepted as product url",
      extract_product_urls("buy https://fkm.asia/4ykj now") == ["https://fkm.asia/4ykj"])

check("cashback loot post matches",
      is_loot("🚨Grab Them at 90% Cashback\nBrillare X Amazon Offer live\n"
              "Tea Tree Shampoo - https://fkm.asia/4ykj")[0] is True)

post_cb = build_post("Brillare Shampoo", "Grab at 90% Cashback https://fkm.asia/4ykj",
                     "https://aff.link/x")
check("cashback post shows CASHBACK label", "90% CASHBACK" in post_cb)

print("== simple deals ==")
from format_post import build_simple_post, build_approval_card  # noqa: E402

sp = build_simple_post("Noise Buds", "https://aff.link/x")
check("simple post has title + link, no LOOT header",
      "Noise Buds" in sp and "https://aff.link/x" in sp and "LOOT" not in sp)
card = build_approval_card("Noise Buds", {}, sp, simple=True)
check("simple approval card marked as simple deal", "simple deal" in card.lower())

print("== cashback math ==")
from patterns import cashback_amount, cashback_deal, extract_coupon  # noqa: E402
from format_post import build_post  # noqa: E402

S25 = ("Samsung Galaxy S25 Ultra (12GB + 256GB) at ₹84,999\n"
       "Apply ₹10,000 off Coupon\nLink: https://amzn.to/4boKpo4\n"
       "Extra ₹4,249 Cashback with Amazon ICICI Credit Cards")
price, cb_amt, cb_pct = cashback_deal(S25)
check("cashback price is 84999", price == 84999)
check("cashback amount is 4249", cb_amt == 4249)
check("cashback pct is 5, not 95", cb_pct == 5)
check("coupon extracted", extract_coupon(S25) == 10000)

post = build_post("Samsung Galaxy S25 Ultra", S25, "https://x")
check("post shows real price 84,999", "₹84,999" in post)
check("post shows 5% CASHBACK", "5% CASHBACK" in post)
check("post does NOT show fake 95%", "95%" not in post)
check("post does NOT price it at 4,249", "₹4,249</b>" not in post)
check("post mentions coupon", "coupon" in post.lower())
check("post mentions cashback amount", "₹4,249" in post)

m, r = is_loot("LOOT " + S25)
check("no spurious price_drop_pct reason", r.get("price_drop_pct") is None)
check("cashback_pct reason present", r.get("cashback_pct") == 5)

# sanity: genuine price drops still work
m2, r2 = is_loot("LOOT boAt buds MRP ₹4,999 at ₹499 https://amzn.to/x")
check("real price drop still detected", r2.get("price_drop_pct") == 90)

# sanity: '% cashback' with no amount nearby -> no fake math
m3, r3 = is_loot("LOOT deal at ₹999, 10% cashback https://amzn.to/x")
check("pct-only cashback has no cashback_deal", cashback_deal("deal at ₹999, 10% cashback") == (None, None, None))

print("== ai enhancement (fail-open, multi-provider) ==")
import ai_enhance as _ai  # noqa: E402

for k in ("ZAI_API_KEY", "GROQ_API_KEY", "AI_PROVIDER"):
    os.environ.pop(k, None)
check("no keys -> no providers", _ai._provider_order() == [])
check("no keys -> None (template fallback)", _ai.enhance_post("x", "y") is None)

os.environ["GROQ_API_KEY"] = "dummy"
check("groq only -> [groq]", _ai._provider_order() == ["groq"])
os.environ["ZAI_API_KEY"] = "dummy"
check("both keys -> zai first", _ai._provider_order() == ["zai", "groq"])
os.environ["AI_PROVIDER"] = "groq"
check("pinned groq", _ai._provider_order() == ["groq"])
os.environ["AI_PROVIDER"] = "zai"
check("pinned zai", _ai._provider_order() == ["zai"])
for k in ("ZAI_API_KEY", "GROQ_API_KEY", "AI_PROVIDER"):
    os.environ.pop(k, None)

print("== unknown shorteners ==")

check("link.amazon accepted",
      extract_product_urls("monitor https://link.amazon/B0crzKuKW") == ["https://link.amazon/B0crzKuKW"])

check("fkrt.site accepted",
      extract_product_urls("mat https://fkrt.site/6fU3nqE") == ["https://fkrt.site/6fU3nqE"])

print("== verify-alive (logic, network stubbed) ==")
import types  # noqa: E402

# verify.py imports httpx at module load; the sandbox has no httpx and the
# tests below stub out fetch_page_prices, so a stub module is enough.
_httpx_stub = types.ModuleType("httpx")
_httpx_stub.Timeout = lambda *a, **k: None
_httpx_stub.get = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stubbed"))
sys.modules.setdefault("httpx", _httpx_stub)

import verify as _v  # noqa: E402

_orig = _v.fetch_page_prices
try:
    _v.fetch_page_prices = lambda url: [499.0, 4999.0]  # loot price present
    check("alive when loot price on page",
          _v.verify_alive("https://x", 499.0)[0] == "alive")
    _v.fetch_page_prices = lambda url: [2999.0, 4999.0]  # loot price gone
    check("dead when loot price gone (2)",
          _v.verify_alive("https://x", 499.0)[0] == "dead")
    _v.fetch_page_prices = lambda url: []  # blocked / unreachable
    check("unknown when page unreadable",
          _v.verify_alive("https://x", 499.0)[0] == "unknown")
finally:
    _v.fetch_page_prices = _orig

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
