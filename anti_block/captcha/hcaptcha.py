"""anti_block.captcha.hcaptcha — hCaptcha free OSS solver wrapper.

Backed by korolossamy/hcaptcha-ai-solver (BSD-style, no paid API keys required,
uses tls_client + ThreadPoolExecutor + AI-style motion data generation).

Install via: bash captcha/install_hcaptcha_solver.sh (clones to ~/hcaptcha-ai-solver by default).

Usage (CLI):
  python3 -m anti_block.captcha.hcaptcha <sitekey> <host> [--proxy URL]

Usage (Python):
  from anti_block.captcha.hcaptcha import solve_hcaptcha
  result = solve_hcaptcha(sitekey, host, proxy='socks5h://...')

Returns dict with 'token' key (h-captcha-response value) on success, or raises
RuntimeError on failure.

Created 2026-05-08 (fix #67) — для регистрационных форм казино где появляется
hCaptcha (typical case: registration form with sitekey present, submit disabled
until the captcha is solved). Replaces the need for VNC manual solving.

ВАЖНО: solver разработан для Discord-style hCaptcha. На казино может работать
по-разному — HSW token generation (нужен Discord-specific) пропущен здесь;
если казино требует HSW — надо запустить hsw_api.py service отдельно
(см. $HCAPTCHA_SOLVER_PATH/hsw_api.py).
"""
import argparse
import json
import os
import sys

# Path to hcaptcha-ai-solver clone. Run captcha/install_hcaptcha_solver.sh first.
# Override via env var: HCAPTCHA_SOLVER_PATH=/path/to/hcaptcha-ai-solver
import os as _os
HCAPTCHA_SOLVER_PATH = _os.environ.get("HCAPTCHA_SOLVER_PATH", _os.path.expanduser("~/hcaptcha-ai-solver"))

if HCAPTCHA_SOLVER_PATH not in sys.path:
    sys.path.insert(0, HCAPTCHA_SOLVER_PATH)


def solve_hcaptcha(sitekey: str, host: str, proxy: str = None, rqdata: str = None) -> dict:
    """Solve hCaptcha challenge.

    sitekey: hCaptcha site key (extracted from page DOM, e.g. data-sitekey attr)
    host:    target hostname (e.g. 'baxterbet.com')
    proxy:   optional SOCKS5/HTTP proxy URL (use SOAX bridge for IP-binding)
    rqdata:  optional rqdata blob from page (passed to solver if present)

    Returns dict with token + meta. Raises RuntimeError on failure.
    """
    try:
        from modules.solver import Solver
    except ImportError as exc:
        raise RuntimeError(
            f'Cannot import Solver from {HCAPTCHA_SOLVER_PATH}/modules. '
            f'Verify clone exists. Error: {exc}'
        )

    kwargs = {'sitekey': sitekey, 'host': host}
    if proxy:
        kwargs['proxy'] = proxy
    if rqdata:
        kwargs['rqdata'] = rqdata

    try:
        result = Solver(**kwargs).solve()
    except Exception as exc:
        raise RuntimeError(f'hCaptcha solve failed: {type(exc).__name__}: {exc}')

    if not result:
        raise RuntimeError('Solver returned empty/None — check stdout logs above')
    return result if isinstance(result, dict) else {'token': str(result)}


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Solve hCaptcha via OSS korolossamy/hcaptcha-ai-solver. Free, no API keys.',
    )
    ap.add_argument('sitekey', help='hCaptcha site key (data-sitekey from page DOM)')
    ap.add_argument('host', help='Target hostname (e.g. baxterbet.com)')
    ap.add_argument('--proxy', help='SOCKS5/HTTP proxy URL (e.g. socks5h://127.0.0.1:11087 для RS bridge)')
    ap.add_argument('--rqdata', help='Optional rqdata blob from page')
    args = ap.parse_args()

    try:
        result = solve_hcaptcha(args.sitekey, args.host, proxy=args.proxy, rqdata=args.rqdata)
    except RuntimeError as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
