#!/usr/bin/env python3
"""CLI для TLS-impersonation scout. HTTP-only fallback против WAF на TLS handshake.

Usage:
    python3 -m anti_block.tls.cli check                # тест fingerprint через tls.peet.ws
    python3 -m anti_block.tls.cli get <url> [--geo IN] # GET request
    python3 -m anti_block.tls.cli get <url> --no-proxy # без SOAX

Exit codes:
    0 — success
    2 — connection error (TLS handshake failed = WAF blocking)
    3 — HTTP 4xx/5xx
    4 — invalid args
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from anti_block.tls import TLSScoutClient


def cmd_check(args):
    if getattr(args, "no_proxy", False):
        os.environ["SOAX_RES_PACKAGE"] = ""
        os.environ["SOAX_RES_PASSWORD"] = ""
    client = TLSScoutClient(soax_geo=args.geo, profile=args.profile)
    try:
        fp = client.fingerprint_check()
    except Exception as e:
        print(f'FAIL: {e}', file=sys.stderr)
        sys.exit(2)
    print(json.dumps({
        'profile': args.profile,
        'soax_geo': args.geo,
        'observed_ja3_hash': fp.get('ja3_hash'),
        'observed_ja4': fp.get('ja4'),
        'observed_http2_akamai': (
            fp.get('http2', {}).get('akamai_fingerprint_hash')
            if isinstance(fp.get('http2'), dict) else None
        ),
        'user_agent_seen': fp.get('user_agent'),
        'donate': 'https://tls.peet.ws',
    }, indent=2))


def cmd_get(args):
    if getattr(args, "no_proxy", False):
        os.environ["SOAX_RES_PACKAGE"] = ""
        os.environ["SOAX_RES_PASSWORD"] = ""
    client = TLSScoutClient(soax_geo=args.geo, profile=args.profile)
    try:
        r = client.get(args.url, timeout=args.timeout)
    except Exception as e:
        print(f'FAIL: {type(e).__name__}: {e}', file=sys.stderr)
        sys.exit(2)
    if r.status_code >= 400:
        print(f'HTTP {r.status_code}', file=sys.stderr)
        print(r.text[:500], file=sys.stderr)
        sys.exit(3)
    print(json.dumps({
        'url': args.url,
        'status': r.status_code,
        'final_url': str(r.url),
        'body_preview': r.text[:1500],
        'body_size': len(r.text),
        'headers': dict(r.headers),
    }, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(prog='anti_block.tls.cli')
    parser.add_argument('--no-proxy', action='store_true', help='Direct connection без SOAX (для тестов)')
    parser.add_argument('--profile', default='chrome131_android', help='curl_cffi impersonate profile')
    parser.add_argument('--geo', default='IN', help='SOAX country code (ISO2)')
    sub = parser.add_subparsers(dest='cmd', required=True)

    import argparse as _ap
    p_check = sub.add_parser('check', help='Verify fingerprint via tls.peet.ws')
    p_check.add_argument('--geo', default=_ap.SUPPRESS)
    p_check.add_argument('--profile', default=_ap.SUPPRESS)
    p_check.add_argument('--no-proxy', action='store_true', default=_ap.SUPPRESS)

    p_get = sub.add_parser('get', help='GET request with TLS impersonation')
    p_get.add_argument('url')
    p_get.add_argument('--timeout', type=int, default=30)
    p_get.add_argument('--geo', default=_ap.SUPPRESS)
    p_get.add_argument('--profile', default=_ap.SUPPRESS)
    p_get.add_argument('--no-proxy', action='store_true', default=_ap.SUPPRESS)

    args = parser.parse_args()
    if args.cmd == 'check':
        cmd_check(args)
    elif args.cmd == 'get':
        cmd_get(args)


if __name__ == '__main__':
    main()
