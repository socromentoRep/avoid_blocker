"""xpay-platform public API client.

The 1xbet/MELbet/Linebet platform shares a backend with a public unauthenticated
endpoint that returns deposit/withdrawal payment systems for a given geo:

    GET /paysystems/information/systems?ref_id={ID}&geo={CC}
    → {"deposits": [...], "withdrawals": [...]}

The same endpoint pattern works on many forks/whitelabels of the same platform.
Pass the operator domain and ref_id (per-geo, often 189) as CLI args.

Note: XPAY_DOMAINS below is a starter registry — extend with your own brands.

Use:
    python3 -m anti_block.scrape.xpay <domain> <ref_id> --geo <CC> --use-bridge

If ANTIBLOCK_USE_BRIDGE=1 in env, requests go via local SOCKS5 bridge
(see anti_block/scrape/bundle.py for ANTIBLOCK_BRIDGE_PORTS env config).
"""
from __future__ import annotations

import os
from typing import Any
from curl_cffi import requests as cffi_req
from anti_block.tls.client import TLSScoutClient


# Starter registry of known xpay-platform domains. Extend with your own.
# These are the public main-brand domains of operators using the 1xbet platform fork.
XPAY_DOMAINS = {
    'linebet': 'linebet.com',
    'melbet': 'melbet.com',
    'mostbet': 'mostbet.com',
    '1xbet-ci': '1xbet.ci',
}

# Bridge ports configured via env var ANTIBLOCK_BRIDGE_PORTS="GEO:port,GEO:port,..."
import os as _os
def _parse_bridge_ports():
    spec = _os.environ.get("ANTIBLOCK_BRIDGE_PORTS", "")
    out = {}
    for chunk in spec.split(","):
        if ":" in chunk:
            geo, port = chunk.split(":", 1)
            try: out[geo.strip().upper()] = int(port.strip())
            except ValueError: continue
    return out
LOCAL_BRIDGE_PORTS = _parse_bridge_ports()


def fetch_methods_url(domain: str, ref_id: int, geo: str = 'IN') -> str:
    return f'https://{domain}/paysystems/information/systems?ref_id={ref_id}&geo={geo.upper()}'


def fetch_methods(
    domain: str = 'melbet.com',
    ref_id: int = 189,
    geo: str = 'IN',
    profile: str = 'chrome131_android',
    timeout: int = 25,
    use_bridge: bool = False,
) -> list[dict[str, Any]]:
    """Fetch payment systems through xpay public API.

    use_bridge=True → local soax-bridge port 11080-11085 (стабильнее когда SOAX direct
    sessions заняты scout'ами).
    """
    if os.environ.get('ANTIBLOCK_USE_BRIDGE') == '1':
        use_bridge = True

    url = fetch_methods_url(domain, ref_id, geo)
    is_android = 'android' in profile
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-IN,en;q=0.9,hi;q=0.8',
        'Referer': f'https://{domain}/',
        'User-Agent': (
            'Mozilla/5.0 (Linux; Android 14; SM-A165F) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36'
            if is_android else
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        ),
    }

    if use_bridge:
        port = LOCAL_BRIDGE_PORTS.get(geo.upper())
        if not port:
            raise RuntimeError(f'No local bridge port for geo={geo}')
        proxies = {'http': f'socks5h://127.0.0.1:{port}', 'https': f'socks5h://127.0.0.1:{port}'}
        resp = cffi_req.get(url, impersonate=profile, timeout=timeout, proxies=proxies, headers=headers)
    else:
        client = TLSScoutClient(soax_geo=geo, profile=profile, timeout=timeout)
        resp = client.get(url, headers=headers)

    if resp.status_code != 200:
        raise RuntimeError(f'xpay API returned HTTP {resp.status_code}: {resp.text[:200]}')

    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f'xpay returned non-JSON: {e}. body={resp.text[:200]}')

    items: list = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # melbet/linebet xpay format: {"deposits": [...], "withdrawals": [...]}
        items = (data.get('deposits') or []) + (data.get('withdrawals') or [])
        if not items:
            items = data.get('data') or data.get('systems') or data.get('methods') or []
    return [m for m in items if isinstance(m, dict)]


# Known PSP keywords для extraction provider name из method 'code' field.
# xpay codes имеют formаt 'paytm_wallet_interkassa2' — нужно распознать interkassa.
KNOWN_PSP_KEYWORDS = [
    'interkassa', 'silkpay', 'bestpay24', 'paykassma', 'kvitum', 'payzen',
    'icash', 'monetix', 'moneygo', 'bt3', 'einpayz', 'eazype',
    'jeton', 'astropay', 'sticpay', 'neteller', 'skrill', 'piastrix',
    'ecopayz', 'mifinity', 'perfect_money', 'webmoney', 'rapid_transfer',
    'paycord', 'paytm', 'phonepe', 'whatsapp', 'googlepay',
]


def extract_provider_from_code(code: str) -> str:
    """Извлечь PSP name из xpay method code ('paytm_wallet_interkassa2' → 'interkassa')."""
    if not code:
        return ''
    code_lower = code.lower()
    for kw in KNOWN_PSP_KEYWORDS:
        if kw in code_lower:
            return kw
    # Fallback: last underscore part if it's not numeric and >3 chars
    if '_' in code_lower:
        tail = code_lower.rsplit('_', 1)[-1].rstrip('0123456789')
        if len(tail) > 3:
            return tail
    return ''


def extract_unique_providers(methods: list[dict[str, Any]]) -> dict[str, dict]:
    """Group xpay methods by provider/agent."""
    providers: dict[str, dict] = {}
    for m in methods:
        agent = (
            m.get('agent') or m.get('paySystem') or m.get('system_name')
            or m.get('provider') or m.get('processor') or ''
        )
        if not agent:
            agent = extract_provider_from_code(m.get('code') or '')
        if not agent:
            # Last try: parse из method name "UPI Fast [silkpay]"
            name = m.get('name') or m.get('ui_label') or ''
            if '[' in name and ']' in name:
                inner = name[name.index('[') + 1:name.index(']')]
                agent = inner.lower()
        if not agent:
            continue

        agent = str(agent).strip().lower()
        bucket = providers.setdefault(agent, {
            'name': agent,
            'methods': [],
            'codes': [],
            'currencies': set(),
        })
        bucket['methods'].append(m.get('name') or m.get('ui_label', ''))
        if m.get('code'):
            bucket['codes'].append(m['code'])
        # Currency parsing — xpay melbet style 'min_in: "50 RUB"'
        for cur_field in ('currency', 'min_in', 'max_in'):
            v = m.get(cur_field)
            if isinstance(v, str):
                for cur in ('USD', 'INR', 'EUR', 'RUB', 'BRL', 'MXN', 'XOF'):
                    if cur in v:
                        bucket['currencies'].add(cur)

    for p in providers.values():
        p['currencies'] = sorted(p['currencies'])
        p['method_count'] = len(p['methods'])

    return providers


def cli_main():
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(prog='anti_block.scrape.xpay')
    parser.add_argument('domain', help='e.g. melbet.com, linebet.com')
    parser.add_argument('ref_id', type=int, help='189 for IN brands')
    parser.add_argument('--geo', default='IN')
    parser.add_argument('--profile', default='chrome131_android')
    parser.add_argument('--use-bridge', action='store_true',
                        help='Local soax-bridge port instead of direct SOAX')
    parser.add_argument('--raw', action='store_true', help='Print raw response items')
    args = parser.parse_args()

    try:
        methods = fetch_methods(
            args.domain, args.ref_id, args.geo, args.profile,
            use_bridge=args.use_bridge,
        )
    except Exception as e:
        print(f'FAIL: {e}', file=sys.stderr)
        sys.exit(2)

    if args.raw:
        print(json.dumps(methods[:50], indent=2, default=str))
        return

    providers = extract_unique_providers(methods)
    print(json.dumps({
        'url': fetch_methods_url(args.domain, args.ref_id, args.geo),
        'method_count': len(methods),
        'unique_providers': len(providers),
        'providers': sorted(providers.keys()),
        'detail': providers,
    }, indent=2, default=str))


if __name__ == '__main__':
    cli_main()
