"""anti_block.proxy.soax_direct — per-call SOAX SOCKS5 session URL builder + retry helper.

Bridges 11080-11090 (soax-bridge.service) хороши для long-running scan flows
с одним sessionid. Но когда SOAX session получил HTTP 500 / ERR_TUNNEL (target
сервер забанил конкретный SOAX exit IP, или session был flagged), нужно сменить
sessionid и попробовать снова — это автоматически выдаст другой residential IP.

Этот модуль:
1. `soax_url(geo, sessionid=None)` — собирает SOAX socks5 URL с произвольным sessionid.
2. `get_with_retry(url, geo, max_retries=3)` — вызывает curl_cffi с auto-rotation на каждой попытке.

Пример использования (CLI):
  python3 -m anti_block.proxy.soax_direct get https://linebet.com/ --geo IN --retries 5

Создан 2026-05-08 (fix #63) после batch 79: linebet получил HTTP 500 SOAX session
ps_linebet_in_j7zkr1 → cashier недоступен. С rotation попыток было бы достаточно
1-2 retry чтобы попасть на чистый exit IP.
"""
import argparse
import os
import secrets
import sys
import time
from typing import Optional, Tuple

SOAX_PASSWORD_DEFAULT = ""  # set via SOAX_RES_PASSWORD env var
_HOST = os.environ.get("SOAX_RES_HOST", "proxy.soax.com")
_PORT = os.environ.get("SOAX_RES_PORT", "5000")
SOAX_HOST = f"{_HOST}:{_PORT}"
SOAX_PACKAGE_RAW = os.environ.get("SOAX_RES_PACKAGE", "")  # required: your SOAX package id from soax.com dashboard
# SOAX_PACKAGE used as username prefix "package-{ID}-country-..."
SOAX_PACKAGE = f"package-{SOAX_PACKAGE_RAW}" if SOAX_PACKAGE_RAW and not SOAX_PACKAGE_RAW.startswith("package-") else (SOAX_PACKAGE_RAW or "")


def soax_url(geo: str, sessionid: Optional[str] = None, length: int = 300, password: Optional[str] = None) -> str:
    """Build SOAX SOCKS5 URL with optional custom sessionid.

    geo:        ISO country code (IN/BR/RS/etc), case-insensitive.
    sessionid:  if None — random hex(8). Use the same sessionid across calls
                для sticky session; pass new one для rotation.
    length:     sessionlength в секундах (default 300 = 5 min).
    """
    if not sessionid:
        sessionid = secrets.token_hex(8)
    pw = password or os.environ.get('SOAX_RES_PASSWORD') or SOAX_PASSWORD_DEFAULT
    user = f'{SOAX_PACKAGE}-country-{geo.lower()}-sessionid-{sessionid}-sessionlength-{length}'
    return f'socks5h://{user}:{pw}@{SOAX_HOST}'


def get_with_retry(
    url: str,
    geo: str = 'IN',
    max_retries: int = 3,
    profile: str = 'chrome131_android',
    timeout: int = 30,
    sleep_between: float = 1.0,
    headers: Optional[dict] = None,
) -> Tuple[int, bytes, dict]:
    """Fetch URL, rotating SOAX sessionid on each attempt.

    Returns (status, content_bytes, response_headers_dict).
    Raises last exception if all attempts fail.
    """
    from curl_cffi import requests

    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        sid = f'retry{attempt}{secrets.token_hex(4)}'
        proxy = soax_url(geo=geo, sessionid=sid)
        try:
            r = requests.get(
                url,
                proxy=proxy,
                impersonate=profile,
                timeout=timeout,
                headers=headers or {},
            )
            print(f'  attempt {attempt+1}/{max_retries} sessionid={sid}: status={r.status_code}', file=sys.stderr)
            if r.status_code < 500:
                return r.status_code, r.content, dict(r.headers)
            last_error = RuntimeError(f'HTTP {r.status_code}')
        except Exception as exc:
            last_error = exc
            print(f'  attempt {attempt+1}/{max_retries} sessionid={sid}: ERROR {type(exc).__name__}: {str(exc)[:120]}', file=sys.stderr)
        if attempt + 1 < max_retries:
            time.sleep(sleep_between)
    raise last_error if last_error else RuntimeError('all retries exhausted')


def main() -> int:
    ap = argparse.ArgumentParser(
        description='SOAX direct fetch with sessionid auto-rotation on failure.',
    )
    ap.add_argument('action', choices=['get', 'url'], help='get URL with rotation, or just print soax url for given geo')
    ap.add_argument('target', help='URL (for action=get) or geo code (for action=url)')
    ap.add_argument('--geo', default='IN', help='SOAX geo (default IN)')
    ap.add_argument('--retries', type=int, default=3)
    ap.add_argument('--profile', default='chrome131_android')
    ap.add_argument('--sessionid', help='Use specific sessionid (overrides rotation)')
    ap.add_argument('--print-headers', action='store_true')
    ap.add_argument('--print-body-bytes', type=int, default=2000, help='Truncate body to N bytes (default 2000)')
    args = ap.parse_args()

    if args.action == 'url':
        # action=url + target=geo
        print(soax_url(args.target, sessionid=args.sessionid))
        return 0

    # action=get
    try:
        status, body, hdrs = get_with_retry(
            url=args.target,
            geo=args.geo,
            max_retries=args.retries,
            profile=args.profile,
        )
    except Exception as exc:
        print(f'FAIL after {args.retries} retries: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1

    print(f'STATUS: {status}')
    if args.print_headers:
        print('HEADERS:')
        for k, v in hdrs.items():
            print(f'  {k}: {v}')
    print('BODY:')
    print(body[:args.print_body_bytes].decode('utf-8', errors='replace'))
    if len(body) > args.print_body_bytes:
        print(f'... (truncated, total {len(body)} bytes)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
