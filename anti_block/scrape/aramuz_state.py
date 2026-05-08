"""anti_block.scrape.aramuz_state — decode Aramuz cloaking platform's window._pinia state.

Aramuz wraps real casino brands behind cloaking domains (e.g. 42bonuskong54.com →
wynixio6.com → retrobet.live). The real backend config (PIQ_HOST, API_HOST,
merchantId, country gate) is stored in window._pinia SSR state as a base64-encoded
JSON payload, sometimes prefixed with arbitrary leading chars or LZString-compressed.

Created after observing several Aramuz-cloaked iGaming sites where each scan
required ad-hoc base64+LZString decoding of window._pinia. This module codifies
the pattern so any pipeline can run:

    python3 -m anti_block.scrape.aramuz_state https://example-aramuz-mirror.com/ --geo RS

Outputs a JSON dict with extracted endpoints. Exit 0 on success, non-zero if
no Pinia state found.
"""
import argparse
import base64
import json
import re
import sys
from typing import Optional

try:
    import lzstring
except ImportError:
    lzstring = None


_PINIA_RE = re.compile(
    r'window\._pinia\s*=\s*[\'"]([A-Za-z0-9+/=_\-\\\\\\\\]+?)[\'"]',
    re.MULTILINE
)
_FALLBACK_RE = re.compile(
    r'window\._pinia\s*=\s*JSON\.parse\([\'"]([^\'"]+)[\'"]\)',
    re.MULTILINE
)


def _try_b64_with_offsets(payload: str) -> Optional[dict]:
    """Try base64-decode at offset 0, then 2, then search for 'eyJ' (=='{"' base64) magic."""
    candidates = [0, 2]
    eyj_idx = payload.find('eyJ')
    if eyj_idx >= 0 and eyj_idx not in candidates:
        candidates.append(eyj_idx)
    for off in candidates:
        try:
            blob = payload[off:]
            # Pad if needed
            blob += '=' * (-len(blob) % 4)
            decoded = base64.b64decode(blob).decode('utf-8', errors='replace')
            if decoded.startswith('{') or decoded.startswith('['):
                return json.loads(decoded)
        except Exception:
            continue
    return None


def _try_lzstring(payload: str) -> Optional[dict]:
    """Try LZString.decompressFromBase64 at multiple offsets (commonly 0 or 2)."""
    if lzstring is None:
        return None
    ls = lzstring.LZString()
    for off in (0, 2):
        try:
            blob = payload[off:]
            decompressed = ls.decompressFromBase64(blob)
            if not decompressed:
                continue
            if decompressed.startswith('{') or decompressed.startswith('['):
                return json.loads(decompressed)
        except Exception:
            continue
    return None


def decode_pinia_state(html_text: str) -> Optional[dict]:
    """Extract and decode window._pinia state. Returns dict or None.

    Tries strategies in order: plain JSON.parse(...), base64 (offset 0/2/eyJ), then LZString.
    """
    m = _FALLBACK_RE.search(html_text)
    if m:
        try:
            inner = m.group(1).encode().decode('unicode_escape')
            return json.loads(inner)
        except Exception:
            pass

    m = _PINIA_RE.search(html_text)
    if not m:
        return None
    payload = m.group(1)

    state = _try_b64_with_offsets(payload)
    if state is not None:
        return state

    state = _try_lzstring(payload)
    if state is not None:
        return state

    return None


_INTERESTING_KEY_FRAGMENTS = (
    'PIQ_HOST', 'API_HOST', 'CROSS_AUTH', 'WL_SLUG',
    'cashier', 'merchant', 'partner', 'rotator',
    'siteIsAllowed', 'country',
)
_INTERESTING_KEY_SUBSTRS = ('HOST', 'URL', 'ENDPOINT')


def extract_endpoints(state: dict, max_str_len: int = 200) -> dict:
    """Walk state dict; return flat {dotted.path: value} for keys that look like endpoints/config."""
    out: dict = {}

    def walk(obj, path: str = ''):
        if isinstance(obj, dict):
            for k, v in obj.items():
                kp = f'{path}.{k}' if path else str(k)
                interesting = (
                    k in _INTERESTING_KEY_FRAGMENTS
                    or any(s in str(k) for s in _INTERESTING_KEY_SUBSTRS)
                    or any(s.lower() in str(k).lower() for s in _INTERESTING_KEY_FRAGMENTS)
                )
                if interesting and isinstance(v, (str, int, float, bool)) and v is not None:
                    sval = str(v)
                    if 0 < len(sval) <= max_str_len:
                        out[kp] = v
                walk(v, kp)
        elif isinstance(obj, list):
            for i, item in enumerate(obj[:50]):
                walk(item, f'{path}[{i}]')

    walk(state)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Decode Aramuz cloaking platform window._pinia state — extracts PIQ_HOST/API_HOST/merchantId.',
    )
    ap.add_argument('url', help='URL to fetch (use mirror or canonical site domain)')
    ap.add_argument('--geo', default='IN', help='SOAX geo for TLS bridge (default: IN)')
    ap.add_argument('--profile', default='chrome131_android', help='TLS impersonation profile')
    ap.add_argument('--print-state', action='store_true', help='Print full decoded state JSON (truncated to 5KB)')
    ap.add_argument('--use-bridge', action='store_true', help='Use SOAX local bridge (default off — use direct SOAX socks5)')
    ap.add_argument('--from-file', metavar='PATH', help='Skip HTTP fetch; decode from local HTML file')
    args = ap.parse_args()

    if args.from_file:
        html = open(args.from_file, encoding='utf-8', errors='replace').read()
    else:
        from anti_block.tls.client import get as tls_get
        try:
            status, html, _hdrs = tls_get(args.url, geo=args.geo, profile=args.profile, use_bridge=args.use_bridge, timeout=30)
        except Exception as exc:
            print(f'TLS fetch failed: {exc}', file=sys.stderr)
            return 3
        if status != 200:
            print(f'HTTP {status} fetching {args.url}', file=sys.stderr)
            return 1

    state = decode_pinia_state(html)
    if state is None:
        print('No window._pinia state decoded (tried plain b64, offset-2, eyJ-magic, LZString)', file=sys.stderr)
        return 2

    if args.print_state:
        full = json.dumps(state, indent=2, ensure_ascii=False)
        sys.stdout.write(full[:5000])
        if len(full) > 5000:
            sys.stdout.write('\n... (truncated)\n')

    endpoints = extract_endpoints(state)
    print(json.dumps(endpoints, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
