"""Anti-block extensions for Hermes form-filler.

This subpackage extends `anti_block` with helpers specifically for filling
out contact forms on PSP corporate websites (NOT casino sites).

Key differences from the scan pipeline:
  - Forms are typically on global corporate sites — direct DC IP works
    for ~60-80% of cases. SOAX is conditional, not always-on.
  - The blockers we hit are: CloudFront 403 (geo), reCAPTCHA v2 on submit,
    cookie consent overlays hiding the form, custom WAFs on regional PSPs.
  - We never click submit. The skill enforces fill-only.

Public entry points:
  - autoconsent_inject (forms.autoconsent)  — dismiss cookie banners
  - lookup_geo         (forms.geo_lookup)   — provider name → geo + bridge port
  - inspect_form       (forms.form_inspector) — find forms + captchas
  - solve_recaptcha_v2 (forms.recaptcha_v2) — audio-based reCAPTCHA solver

Usage from Hermes skill:
    bash -c "/opt/payment-scout/.venv-antiblock/bin/python3 -m \
        anti_block.forms.<module> ..."

Or via the unified CLI dispatcher (forms.cli).
"""

__version__ = "0.1.0"
