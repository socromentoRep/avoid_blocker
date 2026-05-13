#!/usr/bin/env python3
"""anti_block.forms.compare — diff two form_test_report.json (T0 baseline vs T1 after-build).

Compute pass-rate delta, per-site status changes, anti-block contribution metrics.
Produce a markdown report ready for ~/Desktop.

Usage:
    /opt/payment-scout/.venv-antiblock/bin/python3 -m anti_block.forms.compare \
        --baseline /tmp/form_test_report_baseline.json \
        --after    /tmp/form_test_report.json \
        --out      /tmp/form_test_compare.md
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


STATUS_RANK = {
    "filled_no_submit": 5,   # best
    "filled_partial":   4,
    "captcha_blocked":  3,   # was blocked → fillable now is improvement
    "no_form_found":    2,
    "blocked_403":      1,
    "error":            0,   # worst
}


def load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"providers": [], "summary": {}, "_missing": True, "_path": str(p)}
    try:
        return json.loads(p.read_text())
    except Exception as e:
        return {"providers": [], "summary": {}, "_error": str(e), "_path": str(p)}


def index_by_url(report: dict) -> dict[str, dict]:
    out = {}
    for p in report.get("providers", []):
        url = p.get("url") or p.get("name")
        if url:
            out[url] = p
    return out


def render(baseline: dict, after: dict) -> str:
    md = []
    md.append("# Form-filler T0 vs T1 — comparison report\n")

    b_summary = baseline.get("summary", {}) or {}
    a_summary = after.get("summary", {}) or {}

    b_total = b_summary.get("total") or len(baseline.get("providers", []))
    a_total = a_summary.get("total") or len(after.get("providers", []))
    b_ok = b_summary.get("filled_ok", 0)
    a_ok = a_summary.get("filled_ok", 0)

    def pct(n, t):
        return f"{(100 * n / t):.1f}%" if t else "n/a"

    md.append("## Aggregate\n")
    md.append("| Metric | T0 (baseline) | T1 (after build) | Δ |")
    md.append("|---|---|---|---|")
    md.append(f"| Total | {b_total} | {a_total} | — |")
    md.append(f"| filled_ok | {b_ok} ({pct(b_ok, b_total)}) | {a_ok} ({pct(a_ok, a_total)}) | {a_ok - b_ok:+d} |")

    for k in ("no_form", "captcha_blocked", "blocked_403", "errors", "consent_dismissed"):
        bv = b_summary.get(k, 0)
        av = a_summary.get(k, 0)
        md.append(f"| {k} | {bv} | {av} | {av - bv:+d}" + " |")
    md.append("")

    if b_total and a_total:
        delta_pct = (100 * a_ok / a_total) - (100 * b_ok / b_total)
        md.append(f"**Pass-rate delta: {delta_pct:+.1f} pp** (T0 {pct(b_ok, b_total)} → T1 {pct(a_ok, a_total)})")
        md.append("")

    # Decision threshold (per FormFiller-AntiBlock-Plan §7).
    if a_total:
        ap = (100 * a_ok / a_total)
        if ap >= 70:
            verdict = "✅ **OSS достаточно**. Pass-rate ≥ 70%."
        elif ap >= 50:
            verdict = "⚠️ **Marginal**. Pass-rate 50-70%. Рассмотреть humancursor + HSW Flask."
        else:
            verdict = "🛑 **OSS не достаточно**. Pass-rate < 50%. Рекомендуется paid (CapSolver $50/мес)."
        md.append(f"### Verdict\n{verdict}\n")

    # Per-site diff.
    b_idx = index_by_url(baseline)
    a_idx = index_by_url(after)
    all_urls = sorted(set(b_idx) | set(a_idx))
    md.append("## Per-site delta\n")
    md.append("| URL | T0 status | T1 status | Δ status | T1 fingerprint | T1 consent | T1 captcha |")
    md.append("|---|---|---|---|---|---|---|")
    improved = same = regressed = 0
    for u in all_urls:
        b = b_idx.get(u) or {}
        a = a_idx.get(u) or {}
        bs = b.get("status", "—")
        as_ = a.get("status", "—")
        b_rank = STATUS_RANK.get(bs, -1)
        a_rank = STATUS_RANK.get(as_, -1)
        if a_rank > b_rank:
            delta_marker = "⬆️"
            improved += 1
        elif a_rank == b_rank:
            delta_marker = "="
            same += 1
        else:
            delta_marker = "⬇️"
            regressed += 1
        fp = "?"
        if isinstance(a.get("fingerprint_applied"), list):
            fp = f"{len(a['fingerprint_applied'])}/8"
        consent = a.get("consent_action") or "—"
        if a.get("consent_cmp"):
            consent = f"{consent}({a['consent_cmp']})"
        cap = a.get("captcha") or "—"
        if a.get("captcha_solved"):
            cap += " ✓"
        # Truncate URL display
        u_short = u if len(u) <= 50 else u[:47] + "..."
        md.append(f"| `{u_short}` | {bs} | {as_} | {delta_marker} | {fp} | {consent} | {cap} |")
    md.append("")
    md.append(f"**Movements:** improved {improved}, same {same}, regressed {regressed}")
    md.append("")

    # Anti-block contribution.
    md.append("## Anti-block contribution analysis\n")

    # How many T1 successes had fingerprint/consent applied?
    a_providers = after.get("providers", [])
    fp_applied_n = sum(1 for p in a_providers if isinstance(p.get("fingerprint_applied"), list) and p["fingerprint_applied"])
    consent_dismissed_n = sum(1 for p in a_providers if p.get("consent_action") in ("rejected", "accepted"))
    captcha_solved_n = sum(1 for p in a_providers if p.get("captcha_solved"))
    md.append(f"- Fingerprint overrides applied: **{fp_applied_n}** / {a_total} sites")
    md.append(f"- Cookie consent dismissed: **{consent_dismissed_n}** / {a_total}")
    md.append(f"- Captcha solved: **{captcha_solved_n}** / {a_total}")
    md.append("")

    # CMP distribution in T1.
    cmps = Counter(p.get("consent_cmp") for p in a_providers if p.get("consent_cmp"))
    if cmps:
        md.append("**CMPs detected (T1):**")
        for cmp_name, n in cmps.most_common():
            md.append(f"- {cmp_name}: {n}")
        md.append("")

    # Captcha types in T1.
    caps = Counter(p.get("captcha") for p in a_providers if p.get("captcha"))
    if caps:
        md.append("**Captcha types (T1):**")
        for cap_type, n in caps.most_common():
            md.append(f"- {cap_type}: {n}")
        md.append("")

    # Geo decisions distribution.
    geos = Counter()
    for p in a_providers:
        gd = p.get("geo_decision") or {}
        gv = gd.get("geo") or "global"
        geos[gv] += 1
    if geos:
        md.append("**Geo decisions (T1):**")
        for g, n in geos.most_common():
            md.append(f"- {g}: {n}")
        md.append("")

    # Failures detail (T1).
    failures = [p for p in a_providers if p.get("status") not in ("filled_no_submit", "filled_partial")]
    if failures:
        md.append("## T1 failures detail\n")
        md.append("| Site | URL | Status | Captcha | Error |")
        md.append("|---|---|---|---|---|")
        for p in failures[:20]:
            name = (p.get("name") or "?")[:30]
            url = (p.get("url") or "")[:50]
            st = p.get("status", "—")
            cap = p.get("captcha") or "—"
            err = (p.get("error") or "—")[:60]
            md.append(f"| {name} | `{url}` | {st} | {cap} | {err} |")
        md.append("")

    return "\n".join(md)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, help="path to T0 report json")
    ap.add_argument("--after", required=True, help="path to T1 report json")
    ap.add_argument("--out", default="/tmp/form_test_compare.md")
    args = ap.parse_args()

    baseline = load(args.baseline)
    after = load(args.after)

    if baseline.get("_missing") or after.get("_missing"):
        print(f"warn: one or both reports missing", file=sys.stderr)
    if baseline.get("_error"):
        print(f"warn baseline parse error: {baseline['_error']}", file=sys.stderr)
    if after.get("_error"):
        print(f"warn after parse error: {after['_error']}", file=sys.stderr)

    md = render(baseline, after)
    Path(args.out).write_text(md)
    print(f"wrote {args.out} ({len(md)} bytes)", file=sys.stderr)
    # Also echo to stdout for piping
    sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
