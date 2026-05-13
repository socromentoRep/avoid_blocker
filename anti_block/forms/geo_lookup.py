"""anti_block.forms.geo_lookup — provider name → geo country → SOAX bridge port.

Used by form-filler skill to decide WHEN and FROM WHICH geo to retry a request
after a direct DC-IP attempt failed with 403/429/region-block.

Strategy (in order):
  1. DB `providers.country` field (HQ country, populated for ~80% of PSPs)
  2. URL TLD parse (.in→IN, .br→BR, .mx→MX, .de→DE, .gb→GB, .fr→FR, .ca→CA)
  3. URL keyword heuristic (bharatpe → IN, conekta → MX, etc.) — last resort
  4. None — no proxy retry, just report failure

Bridge ports are fixed in systemd unit files (gost listeners) at
11080-11090 — see prompts/anti-block-cheatsheet.md for the canonical map.

CLI:
    python3 -m anti_block.forms.geo_lookup --provider checkout.com
    python3 -m anti_block.forms.geo_lookup --url https://www.bharatpe.com/contact

Returns JSON to stdout:
    {"provider": "...", "url": "...", "geo": "IN", "source": "tld",
     "bridge_port": 11080, "socks5_url": "socks5://127.0.0.1:11080"}
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Canonical SOAX bridge ports. Keep in sync with systemd soax-bridge.service units
# and prompts/anti-block-cheatsheet.md ⚠️ — single source of truth.
GEO_BRIDGE: dict[str, int] = {
    "IN": 11080,
    "BR": 11082,
    "MX": 11083,
    "CI": 11084,
    "DE": 11085,
    "PL": 11086,
    "RS": 11087,
    "GB": 11088,
    "FR": 11089,
    "CA": 11090,
}

# ccTLD → ISO country mapping (only TLDs we have bridges for + common variants).
TLD_TO_GEO: dict[str, str] = {
    "in": "IN", "co.in": "IN",
    "br": "BR", "com.br": "BR",
    "mx": "MX", "com.mx": "MX",
    "ci": "CI",
    "de": "DE",
    "pl": "PL",
    "rs": "RS",
    "uk": "GB", "co.uk": "GB", "gb": "GB",
    "fr": "FR",
    "ca": "CA",
}

# Provider name keyword → geo heuristic. Used when DB has no country
# and URL TLD is generic (.com / .io). Conservative — only well-known.
KEYWORD_TO_GEO: dict[str, str] = {
    "bharatpe": "IN", "razorpay": "IN", "paytm": "IN", "phonepe": "IN",
    "conekta": "MX", "openpay": "MX", "openpaymx": "MX",
    "pix": "BR", "ebanx": "BR", "pagseguro": "BR",
    "klarna": "DE", "sofort": "DE", "giropay": "DE",
}


def _query_db(provider: str) -> Optional[str]:
    """Lookup provider HQ country in scan DB. Returns ISO 3166-1 alpha-2 or None."""
    if not provider:
        return None
    # Defence: only allow safe chars in provider name (psql injected via -c)
    if not re.match(r"^[a-zA-Z0-9._\-]+$", provider):
        logger.warning("provider name has unsafe chars: %r", provider)
        return None
    try:
        out = subprocess.run(
            [
                "docker", "exec", "ps-scan-db", "psql",
                "-U", "scan_user", "-d", "scan_analytics",
                "-At", "-c",
                f"SELECT UPPER(country) FROM providers WHERE LOWER(name)=LOWER('{provider}') LIMIT 1",
            ],
            capture_output=True, text=True, timeout=8,
        )
        val = (out.stdout or "").strip()
        if val and len(val) == 2 and val.isalpha():
            return val
    except Exception as e:
        logger.warning("db query failed: %s", e)
    return None


def _parse_tld(url: str) -> Optional[str]:
    """Extract ccTLD from URL and map to geo."""
    if not url:
        return None
    try:
        host = urlparse(url).hostname or ""
        host = host.lower()
        # Try two-level (co.uk, com.br, com.mx) first
        parts = host.split(".")
        if len(parts) >= 3:
            two = ".".join(parts[-2:])
            if two in TLD_TO_GEO:
                return TLD_TO_GEO[two]
        if parts:
            one = parts[-1]
            if one in TLD_TO_GEO:
                return TLD_TO_GEO[one]
    except Exception as e:
        logger.debug("tld parse failed for %r: %s", url, e)
    return None


def _keyword_match(provider: str, url: str) -> Optional[str]:
    """Fall back: match provider or URL host against KEYWORD_TO_GEO."""
    haystack = f"{provider or ''} {url or ''}".lower()
    for kw, geo in KEYWORD_TO_GEO.items():
        if kw in haystack:
            return geo
    return None


def lookup_geo(provider: str = "", url: str = "") -> dict:
    """Resolve geo + bridge for a provider/url.

    Returns dict with keys: provider, url, geo (or None), source, bridge_port, socks5_url.
    Source ∈ {"db", "tld", "keyword", "none"}.
    """
    geo: Optional[str] = None
    source = "none"
    if provider:
        geo = _query_db(provider)
        if geo:
            source = "db"
    if not geo:
        geo = _parse_tld(url)
        if geo:
            source = "tld"
    if not geo:
        geo = _keyword_match(provider, url)
        if geo:
            source = "keyword"

    port = GEO_BRIDGE.get(geo) if geo else None
    socks5 = f"socks5://127.0.0.1:{port}" if port else None

    return {
        "provider": provider,
        "url": url,
        "geo": geo,
        "source": source,
        "bridge_port": port,
        "socks5_url": socks5,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="provider/url → geo+bridge resolver")
    ap.add_argument("--provider", default="", help="provider slug or name")
    ap.add_argument("--url", default="", help="target form URL")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    result = lookup_geo(provider=args.provider, url=args.url)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
