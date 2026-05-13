"""anti_block.forms.cli — unified dispatcher for Hermes Bash invocations.

Single entry point so the skill can keep tool invocations compact:

    python3 -m anti_block.forms.cli geo --provider <name> --url <url>
    python3 -m anti_block.forms.cli recaptcha-v2 --audio-url <URL>
    python3 -m anti_block.forms.cli scripts <name>   # print JS file content to stdout

Why a dispatcher: every Bash subprocess pays ~150ms Python startup. Hermes
can pipe the JS source straight into `mcp__playwright__browser_evaluate`
without an extra file-read step.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent / "scripts"
SCRIPT_NAMES = {
    "fingerprint":   "fingerprint_overrides.js",
    "autoconsent":   "autoconsent_inject.js",
    "form-inspect":  "form_inspector.js",
}


def cmd_scripts(args: argparse.Namespace) -> int:
    """Print JS bundle to stdout for direct pipe into browser_evaluate."""
    name = args.name
    if name == "list":
        for k in sorted(SCRIPT_NAMES):
            print(f"{k}: {SCRIPT_NAMES[k]}")
        return 0
    if name not in SCRIPT_NAMES:
        print(f"unknown script: {name!r}; available: {sorted(SCRIPT_NAMES)}", file=sys.stderr)
        return 2
    path = SCRIPT_DIR / SCRIPT_NAMES[name]
    if not path.exists():
        print(f"file missing: {path}", file=sys.stderr)
        return 3
    sys.stdout.write(path.read_text())
    return 0


def cmd_geo(args: argparse.Namespace) -> int:
    from anti_block.forms.geo_lookup import lookup_geo
    import json
    res = lookup_geo(provider=args.provider or "", url=args.url or "")
    print(json.dumps(res, ensure_ascii=False))
    return 0


def cmd_recaptcha_v2(args: argparse.Namespace) -> int:
    from anti_block.forms.recaptcha_v2 import solve_audio
    import json
    res = solve_audio(args.audio_url, proxy=args.proxy, language=args.language)
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res.get("ok") else 1


def cmd_label(args: argparse.Namespace) -> int:
    from anti_block.forms.lang_aliases import match_label_to_field, detect_language
    import json
    if args.detect_lang:
        print(json.dumps({"text": args.label[:120], "lang": detect_language(args.label)}, ensure_ascii=False))
    else:
        field = match_label_to_field(args.label)
        print(json.dumps({"label": args.label, "field": field}, ensure_ascii=False))
    return 0


def cmd_hcaptcha_hsw(args: argparse.Namespace) -> int:
    from anti_block.forms.hcaptcha_hsw import get_hsw_token
    import json
    res = get_hsw_token(args.rqdata, args.host, endpoint=args.endpoint, timeout=args.timeout)
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res.get("ok") else 1


def cmd_compare(args: argparse.Namespace) -> int:
    from anti_block.forms.compare import load, render
    from pathlib import Path
    baseline = load(args.baseline)
    after = load(args.after)
    md = render(baseline, after)
    Path(args.out).write_text(md)
    print(md)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="anti_block.forms.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("geo", help="provider/url → geo + bridge port")
    sp.add_argument("--provider", default="")
    sp.add_argument("--url", default="")
    sp.set_defaults(func=cmd_geo)

    sp = sub.add_parser("recaptcha-v2", help="reCAPTCHA v2 audio-challenge transcriber")
    sp.add_argument("--audio-url", required=True)
    sp.add_argument("--proxy", default=None)
    sp.add_argument("--language", default="en-US")
    sp.set_defaults(func=cmd_recaptcha_v2)

    sp = sub.add_parser("scripts", help="print JS bundle (fingerprint|autoconsent|form-inspect|list)")
    sp.add_argument("name", help="one of: fingerprint, autoconsent, form-inspect, list")
    sp.set_defaults(func=cmd_scripts)

    sp = sub.add_parser("label", help="match form-field label to profile field (multi-lang)")
    sp.add_argument("label", help="label/placeholder/name text from form field")
    sp.add_argument("--detect-lang", action="store_true", help="instead detect page language from given text")
    sp.set_defaults(func=cmd_label)

    sp = sub.add_parser("hcaptcha-hsw", help="get HSW token from local Flask service (for hCaptcha rqdata variant)")
    sp.add_argument("--rqdata", required=True)
    sp.add_argument("--host", required=True)
    sp.add_argument("--endpoint", default="http://127.0.0.1:5000/hsw")
    sp.add_argument("--timeout", type=int, default=30)
    sp.set_defaults(func=cmd_hcaptcha_hsw)

    sp = sub.add_parser("compare", help="diff two form_test_report.json (T0 baseline vs T1 after)")
    sp.add_argument("--baseline", required=True)
    sp.add_argument("--after", required=True)
    sp.add_argument("--out", default="/tmp/form_test_compare.md")
    sp.set_defaults(func=cmd_compare)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
