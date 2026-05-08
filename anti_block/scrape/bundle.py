"""Bundle/CSS extractor — извлекает PSP без браузера через парсинг JS chunks и CSS class names.

Применимо для sites где scout пропускает данные:
- **sportingbet-br** — `themes-sportingbet-br-payments.bcd0da3bcc45.css` стабильно даёт 14+ PSP через CSS class names (.muchbetter, .neosurf-info, .payment-method-astropaycard)
- **betnacional** — webpack lazy-loaded chunks содержат PSP enum
- **mell5126** — payhost-gate redirect chain в JS bundle
- **valorbetlive** — payment-intention endpoint references

Workflow:
1. Скачиваем homepage HTML через TLS-impersonation
2. Извлекаем `<script src="...">`, `<link rel="stylesheet" href="...">` ссылки
3. Filter по PSP keywords (payment, casino, finance)
4. Скачиваем chunks
5. Regex-extract:
   - CSS: class names типа `.payment-method-{name}`, `.{psp_name}-info`
   - JS: string constants типа `"PROVIDER_NAME"`, `["PSP1", "PSP2"]`, URL-ы payment doms
6. Cross-reference с PSP keyword DB

Использование:
    python3 -m anti_block.scrape.bundle https://sportingbet.bet.br/
    python3 -m anti_block.scrape.bundle https://betnacional.com/

Output JSON: {url, psp_candidates: [...], domains: [...], chunks_analyzed: N}
"""
from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from curl_cffi import requests as cffi_req

try:
    from anti_block.tls.client import TLSScoutClient, ANDROID_CHROME_131_HEADERS
except ImportError:
    TLSScoutClient = None
    ANDROID_CHROME_131_HEADERS = {}


# Bridge ports configured via env var ANTIBLOCK_BRIDGE_PORTS="GEO1:port1,GEO2:port2,..."
# Example: ANTIBLOCK_BRIDGE_PORTS="IN:11080,BR:11082,DE:11085"
# Set up gost (or similar) listeners on these ports forwarding to your SOAX/proxy provider.
import os as _os
def _parse_bridge_ports():
    spec = _os.environ.get("ANTIBLOCK_BRIDGE_PORTS", "")
    out = {}
    for chunk in spec.split(","):
        if ":" in chunk:
            geo, port = chunk.split(":", 1)
            try:
                out[geo.strip().upper()] = int(port.strip())
            except ValueError:
                continue
    return out
LOCAL_BRIDGE_PORTS = _parse_bridge_ports()


# ============================================================
# Known PSP keywords для regex matching в bundles/CSS.
# Это extended list — для bundle parsing мы хотим ловить все известные PSP.
# ============================================================

KNOWN_PSPS = [
    # IN (1xbet platform / linebet / melbet / mostbet)
    'silkpay', 'bestpay24', 'paykassma', 'interkassa', 'kvitum', 'payzen',
    'icash', 'monetix', 'moneygo', 'bt3', 'einpayz', 'eazype',
    'paycord', 'irontrust', 'reliablescientists',
    'sagaga', 'mupay', 'tkpay',
    'paytm', 'phonepe', 'whatsapp', 'googlepay', 'bhim', 'upi',
    'payme', 'cowpay', 'ntrust', 'payu',
    # E-wallets / international
    'jeton', 'astropay', 'sticpay', 'neteller', 'skrill', 'piastrix',
    'ecopayz', 'mifinity', 'perfect_money', 'perfectmoney', 'webmoney',
    'rapid_transfer', 'rapidtransfer',
    # BR
    'picpay', 'paybrokers', 'sulpayment', 'sulpayments', 'safeway',
    'lt_payment', 'ltpayment', 'pagseguro', 'pagsmile', 'mercadopago',
    'pix', 'paypal', 'paypaldirect', 'truelayer', 'tappp', 'okto',
    'worldpay', 'pagsmile', 'asaas',
    # CI / Africa
    'mpayment', 'onepay', 'wave', 'mtn', 'orange', 'moov',
    'flowmetric', 'paymetrust', 'flutterwave', 'paystack',
    # MX / LATAM
    'caliente', 'nuvei', 'safecharge', 'playtech', 'spei', 'oxxo',
    'todito', 'paycash', 'payproc', 'lobbygateway', 'superpay',
    'opzyem', 'jetspay', 'ampay',
    # PL
    'blik', 'payway', 'payhost', 'payroutehub',
    # Crypto
    'oxapay', 'cryptobot', 'freekassa', 'nicepay', 'nirvanapay', 'norepay', 'r45pay',
    # CF Turnstile / DataDome (anti-bot, не PSP — но flagged для контекста)
    # 'cloudflare', 'datadome', 'turnstile', 'recaptcha', 'qrator',
    # bookmaker-internal
    'cryptocurrencies2', 'cryptocurrencies', 'crypto_internal',
    'lyrapayzen', 'lyra-payzen',
]


# CSS class patterns — sportingbet-br style
CSS_CLASS_PATTERNS = [
    re.compile(rb'\.payment-method-([\w-]+)', re.I),
    re.compile(rb'\.([\w-]+)-info', re.I),
    re.compile(rb'\.([\w-]+)-payment', re.I),
    re.compile(rb'data-psp[="]+([\w-]+)', re.I),
    re.compile(rb'data-agent[="]+([\w-]+)', re.I),
    re.compile(rb'data-system[="]+([\w-]+)', re.I),
    re.compile(rb'data-gatewayid[="]+([\w-]+)', re.I),
]

# JS string patterns — webpack chunks
JS_STRING_PATTERNS = [
    re.compile(rb'"([\w_]{3,30})"\s*:\s*[\'"][\w/-]*payment', re.I),
    re.compile(rb'name\s*:\s*[\'"]([\w_]{3,30})[\'"]', re.I),
    re.compile(rb'provider[\'"]?\s*[:=]\s*[\'"]([\w_-]{3,30})[\'"]', re.I),
    re.compile(rb'agent[\'"]?\s*[:=]\s*[\'"]([\w_-]{3,30})[\'"]', re.I),
    re.compile(rb'(?:psp|gateway|method)_(?:code|id|name)[\'"]?\s*[:=]\s*[\'"]([\w_-]{3,30})[\'"]', re.I),
    # URL patterns: https://{provider}.com/, https://api.{provider}.io
    re.compile(rb'https?://(?:[\w-]+\.)?([\w-]{3,20})\.(?:com|io|ai|net|org|in|br|mx|ru|tech|store|app|cloud|live)\b', re.I),
]

# Domain patterns
DOMAIN_PATTERNS = [
    re.compile(rb'(?:href|src|action|url|endpoint)[\s=][\'"](https?://(?:[\w-]+\.){1,3}(?:com|io|ai|net|org|in|br|mx|ru|tech|store|app|cloud|live))', re.I),
]


def _http_get(
    url: str,
    geo: str = 'IN',
    profile: str = 'chrome131_android',
    use_bridge: bool = False,
    timeout: int = 25,
) -> tuple[int, bytes, dict]:
    """Single HTTP GET через TLS impersonation. Returns (status, body, headers)."""
    if os.environ.get('ANTIBLOCK_USE_BRIDGE') == '1':
        use_bridge = True

    is_android = 'android' in profile
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Linux; Android 14; SM-A165F) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36'
            if is_android else
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-IN,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
    }

    if use_bridge:
        port = LOCAL_BRIDGE_PORTS.get(geo.upper())
        if not port:
            raise RuntimeError(f'No bridge port for geo={geo}')
        proxies = {'http': f'socks5h://127.0.0.1:{port}', 'https': f'socks5h://127.0.0.1:{port}'}
        r = cffi_req.get(url, impersonate=profile, timeout=timeout, proxies=proxies, headers=headers)
    else:
        client = TLSScoutClient(soax_geo=geo, profile=profile, timeout=timeout)
        r = client.get(url, headers=headers)
    return r.status_code, r.content, dict(r.headers)


def extract_resource_urls(html: bytes, base_url: str) -> dict[str, list[str]]:
    """Extract <script src> и <link rel='stylesheet' href> из HTML."""
    js_pattern = re.compile(rb'<script[^>]+src=["\']([^"\']+)["\']', re.I)
    css_pattern = re.compile(rb'<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\']([^"\']+)["\']', re.I)
    css_pattern2 = re.compile(rb'<link[^>]+href=["\']([^"\']+\.css[^"\']*)["\'][^>]*rel=["\']stylesheet', re.I)

    js_urls = []
    for m in js_pattern.findall(html):
        try:
            full = urljoin(base_url, m.decode('utf-8', errors='ignore'))
            js_urls.append(full)
        except Exception:
            pass

    css_urls = []
    for pat in (css_pattern, css_pattern2):
        for m in pat.findall(html):
            try:
                full = urljoin(base_url, m.decode('utf-8', errors='ignore'))
                if full not in css_urls:
                    css_urls.append(full)
            except Exception:
                pass

    return {'js': js_urls, 'css': css_urls}


def filter_payment_chunks(urls: list[str]) -> list[str]:
    """Keep only chunks с keywords payment/cashbox/finance."""
    keywords = ['payment', 'cashbox', 'finance', 'deposit', 'cashier', 'wallet', 'fin', 'kassa']
    out = []
    for u in urls:
        ul = u.lower()
        if any(k in ul for k in keywords):
            out.append(u)
    return out


def extract_psps_from_bytes(content: bytes) -> dict[str, list[str]]:
    """Extract PSP candidates from CSS/JS bytes."""
    found_psps = set()
    found_domains = set()

    # 1. Scan for CSS class patterns
    for pat in CSS_CLASS_PATTERNS:
        for m in pat.findall(content):
            try:
                m_str = m.decode('utf-8', errors='ignore').lower().strip('-_')
                if len(m_str) >= 3 and len(m_str) <= 30:
                    if m_str in KNOWN_PSPS:
                        found_psps.add(m_str)
            except Exception:
                pass

    # 2. Scan for JS string patterns
    for pat in JS_STRING_PATTERNS:
        for m in pat.findall(content):
            try:
                m_str = m.decode('utf-8', errors='ignore').lower().strip('-_')
                if m_str in KNOWN_PSPS:
                    found_psps.add(m_str)
            except Exception:
                pass

    # 3. Direct keyword grep — самый надёжный
    content_lower = content.lower()
    for psp in KNOWN_PSPS:
        if psp.encode('ascii') in content_lower:
            found_psps.add(psp)

    # 4. Extract URLs (могут быть payment domain endpoints)
    for pat in DOMAIN_PATTERNS:
        for m in pat.findall(content):
            try:
                domain_url = m.decode('utf-8', errors='ignore').lower()
                # Extract netloc
                parsed = urlparse(domain_url)
                if parsed.hostname and not parsed.hostname.startswith(('www.', 'cdn.', 'static.')):
                    found_domains.add(parsed.hostname)
            except Exception:
                pass

    return {
        'psps': sorted(found_psps),
        'domains': sorted(d for d in found_domains if any(k in d for k in KNOWN_PSPS) or 'pay' in d or 'cash' in d),
    }


def scrape_site(
    homepage_url: str,
    geo: str = 'IN',
    profile: str = 'chrome131_android',
    use_bridge: bool = False,
    max_chunks: int = 30,
    timeout: int = 25,
) -> dict[str, Any]:
    """Scrape PSP candidates from a site без браузера.

    1. GET homepage
    2. Find все JS/CSS chunks
    3. Filter to payment-related chunks
    4. Download up to max_chunks of them (parallel-ready future)
    5. Regex-scan each for PSP keywords + domains
    6. Aggregate results
    """
    # 1. Homepage
    status, html, _hdrs = _http_get(homepage_url, geo=geo, profile=profile, use_bridge=use_bridge, timeout=timeout)
    if status != 200:
        raise RuntimeError(f'Homepage HTTP {status}')

    base = homepage_url

    # 2. Extract resource URLs
    res = extract_resource_urls(html, base)
    js_urls = filter_payment_chunks(res['js'])
    css_urls = filter_payment_chunks(res['css'])

    # Если payment chunks не нашли — пробуем все CSS (sportingbet-br main bundle часто main.css)
    if not js_urls and not css_urls:
        js_urls = res['js'][:max_chunks // 2]
        css_urls = res['css'][:max_chunks // 2]
    elif not css_urls:
        css_urls = [u for u in res['css'] if 'main' in u.lower() or 'app' in u.lower()][:5]

    chunks_to_fetch = (css_urls + js_urls)[:max_chunks]

    # Аггрегаты
    all_psps = set()
    all_domains = set()
    chunk_results = []
    homepage_findings = extract_psps_from_bytes(html)
    all_psps.update(homepage_findings['psps'])
    all_domains.update(homepage_findings['domains'])

    # 3-5. Download + scan каждый chunk
    for chunk_url in chunks_to_fetch:
        try:
            cstatus, cbody, _ = _http_get(chunk_url, geo=geo, profile=profile, use_bridge=use_bridge, timeout=timeout)
            if cstatus != 200:
                chunk_results.append({'url': chunk_url, 'status': cstatus, 'psps': []})
                continue
            findings = extract_psps_from_bytes(cbody)
            all_psps.update(findings['psps'])
            all_domains.update(findings['domains'])
            chunk_results.append({
                'url': chunk_url,
                'status': cstatus,
                'size_kb': len(cbody) // 1024,
                'psps': findings['psps'],
            })
        except Exception as e:
            chunk_results.append({'url': chunk_url, 'error': str(e)[:100], 'psps': []})

    return {
        'homepage_url': homepage_url,
        'homepage_size_kb': len(html) // 1024,
        'js_urls_found': len(res['js']),
        'css_urls_found': len(res['css']),
        'chunks_filtered_payment': len(chunks_to_fetch),
        'chunks_scanned': len([c for c in chunk_results if c.get('status') == 200]),
        'unique_psps': len(all_psps),
        'psps': sorted(all_psps),
        'domains_with_psp_hints': sorted(all_domains),
        'chunk_details': chunk_results,
    }


def cli_main():
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(prog='anti_block.scrape.bundle')
    parser.add_argument('url', help='Homepage URL (e.g. https://sportingbet.bet.br/)')
    parser.add_argument('--geo', default='IN')
    parser.add_argument('--profile', default='chrome131_android')
    parser.add_argument('--use-bridge', action='store_true')
    parser.add_argument('--max-chunks', type=int, default=30)
    parser.add_argument('--summary', action='store_true', help='Skip chunk_details in output')
    args = parser.parse_args()

    try:
        result = scrape_site(
            args.url, geo=args.geo, profile=args.profile,
            use_bridge=args.use_bridge, max_chunks=args.max_chunks,
        )
    except Exception as e:
        print(f'FAIL: {e}', file=sys.stderr)
        sys.exit(2)

    if args.summary:
        result.pop('chunk_details', None)
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    cli_main()
