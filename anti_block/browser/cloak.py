"""CloakBrowser launcher — open-source replacement для Dolphin Anty.

CloakBrowser 0.3.26 — Chromium с C++ patches на уровне source-code.
Sync Playwright API (не asyncio).

Use cases:
- TLS-protected JS challenges (Qrator, CloudFlare Bot Fight Mode)
- CF Turnstile paywidget pages
- DataDome interstitial JS check
- Any JS-level WAF challenge

CLI:
    python3 -m anti_block.browser.cloak <url> --geo IN [--persist /path]
"""
from __future__ import annotations

import os
from typing import Any

from cloakbrowser import launch as cloak_launch


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


def fetch_page(
    url: str,
    geo: str = 'IN',
    timeout: int = 60,
    persist_dir: str | None = None,
    wait_after_load: int = 5,
    use_bridge: bool = True,
) -> dict[str, Any]:
    """Open URL через CloakBrowser, return HTML/title/cookies."""
    if os.environ.get('ANTIBLOCK_USE_BRIDGE') == '1':
        use_bridge = True

    proxy_config = None
    if use_bridge:
        port = LOCAL_BRIDGE_PORTS.get(geo.upper())
        if port:
            proxy_config = {'server': f'socks5://127.0.0.1:{port}'}

    launch_kwargs = {
        'headless': True,
        'humanize': True,
    }
    if proxy_config:
        launch_kwargs['proxy'] = proxy_config
    if persist_dir:
        launch_kwargs['user_data_dir'] = persist_dir

    browser = cloak_launch(**launch_kwargs)
    try:
        if persist_dir:
            # persistent context — single context with userDataDir
            context = browser  # cloak returns context for user_data_dir mode
            page = context.new_page() if hasattr(context, 'new_page') else browser.pages[0]
        else:
            context = browser.new_context()
            page = context.new_page()

        result: dict[str, Any] = {'url': url}
        try:
            response = page.goto(url, wait_until='domcontentloaded', timeout=timeout * 1000)
            result['status'] = response.status if response else 0
        except Exception as e:
            result['status'] = 0
            result['error'] = str(e)[:200]
            return result

        # Wait for JS challenge (Qrator/CF)
        page.wait_for_timeout(wait_after_load * 1000)

        try:
            html = page.content()
        except Exception:
            html = ''
        try:
            title = page.title()
        except Exception:
            title = ''
        try:
            cookies = context.cookies() if not persist_dir else browser.cookies()
        except Exception:
            cookies = []

        # Storage dump
        try:
            storage = page.evaluate("""() => {
                const items = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i);
                    items[k] = localStorage.getItem(k);
                }
                return items;
            }""")
        except Exception:
            storage = {}

        result.update({
            'final_url': page.url,
            'html_size': len(html),
            'html_preview': html[:1500],
            'title': title,
            'cookies_count': len(cookies),
            'cookies_relevant': [
                {'name': c.get('name'), 'value': str(c.get('value', ''))[:40]}
                for c in cookies if any(k in c.get('domain', '') for k in [url.split('/')[2].replace('www.', '')])
            ][:20],
            'storage_keys': list(storage.keys())[:30] if isinstance(storage, dict) else [],
        })
        return result
    finally:
        try:
            browser.close()
        except Exception:
            pass


def cli_main():
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(prog='anti_block.browser.cloak')
    parser.add_argument('url')
    parser.add_argument('--geo', default='IN')
    parser.add_argument('--no-bridge', action='store_true')
    parser.add_argument('--timeout', type=int, default=60)
    parser.add_argument('--wait', type=int, default=5)
    parser.add_argument('--persist', help='Persistent profile directory')
    args = parser.parse_args()

    try:
        result = fetch_page(
            args.url,
            geo=args.geo,
            use_bridge=not args.no_bridge,
            timeout=args.timeout,
            wait_after_load=args.wait,
            persist_dir=args.persist,
        )
    except Exception as e:
        print(f'FAIL: {type(e).__name__}: {e}', file=sys.stderr)
        sys.exit(2)
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    cli_main()
