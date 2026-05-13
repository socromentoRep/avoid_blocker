"""Smoke tests for anti_block.forms (v0.2.0+).

Covers all 6 CLI subcommands + module imports + handler-level functions.

Run:
    /opt/payment-scout/.venv-antiblock/bin/python3 -m unittest -v \
        anti_block.forms.tests.test_smoke

Or quick:
    /opt/payment-scout/.venv-antiblock/bin/python3 \
        /opt/payment-scout/payment-scout/anti_block/forms/tests/test_smoke.py
"""
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

VENV_PY = "/opt/payment-scout/.venv-antiblock/bin/python3"
CWD = "/opt/payment-scout"


def cli(*args, timeout: int = 15) -> dict:
    """Run anti_block.forms.cli and parse JSON stdout."""
    cmd = [VENV_PY, "-m", "anti_block.forms.cli", *args]
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=CWD, timeout=timeout)
    if out.returncode not in (0, 1):  # 1 = expected for failed-solve, both fine
        raise RuntimeError(f"CLI failed rc={out.returncode}: {out.stderr}")
    try:
        return json.loads(out.stdout) if out.stdout.strip() else {}
    except json.JSONDecodeError:
        return {"_raw": out.stdout, "_stderr": out.stderr}


def cli_raw(*args, timeout: int = 15) -> subprocess.CompletedProcess:
    """Run CLI and return raw subprocess result."""
    cmd = [VENV_PY, "-m", "anti_block.forms.cli", *args]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=CWD, timeout=timeout)


class GeoLookupTest(unittest.TestCase):
    def test_keyword_provider_india(self):
        r = cli("geo", "--provider", "bharatpe", "--url", "https://bharatpe.com/contact/")
        self.assertEqual(r["geo"], "IN")
        self.assertEqual(r["bridge_port"], 11080)
        self.assertEqual(r["source"], "keyword")

    def test_global_provider_returns_no_geo(self):
        r = cli("geo", "--provider", "paysafe", "--url", "https://paysafe.com/contact/")
        self.assertIsNone(r["geo"])
        self.assertIsNone(r["bridge_port"])

    def test_tld_only(self):
        r = cli("geo", "--url", "https://example.de/kontakt")
        self.assertEqual(r["geo"], "DE")
        self.assertEqual(r["bridge_port"], 11085)

    def test_keyword_mx(self):
        r = cli("geo", "--provider", "conekta", "--url", "https://conekta.com/")
        self.assertEqual(r["geo"], "MX")

    def test_unsafe_provider_name_rejected(self):
        r = cli("geo", "--provider", "bobby'); DROP TABLE--", "--url", "")
        self.assertIsNone(r["geo"])


class ScriptsDispatcherTest(unittest.TestCase):
    def test_list_includes_all(self):
        r = cli_raw("scripts", "list")
        self.assertEqual(r.returncode, 0)
        for name in ("fingerprint", "autoconsent", "form-inspect"):
            self.assertIn(name, r.stdout)

    def test_fingerprint_script_is_valid_js(self):
        r = cli_raw("scripts", "fingerprint")
        self.assertEqual(r.returncode, 0)
        body = r.stdout
        self.assertIn("navigator", body)
        self.assertIn("webdriver", body)
        self.assertIn("(() =>", body)

    def test_autoconsent_no_submit_phrases(self):
        r = cli_raw("scripts", "autoconsent")
        self.assertEqual(r.returncode, 0)
        body = r.stdout
        self.assertIn("FORBIDDEN", body)
        self.assertIn("submit", body)
        self.assertIn("Reject all", body)

    def test_autoconsent_has_26_detectors(self):
        r = cli_raw("scripts", "autoconsent")
        # Each CMP detector starts with `{ name: '`
        count = r.stdout.count("{ name: '")
        self.assertGreaterEqual(count, 25, f"expected ≥25 CMP detectors, got {count}")

    def test_form_inspect_returns_iife(self):
        r = cli_raw("scripts", "form-inspect")
        self.assertEqual(r.returncode, 0)
        body = r.stdout
        self.assertIn("recaptcha_v2", body)
        self.assertIn("hcaptcha", body)
        self.assertIn("turnstile", body)
        self.assertIn("forms", body)

    def test_form_inspect_has_honeypot_detection(self):
        r = cli_raw("scripts", "form-inspect")
        self.assertIn("honeypot", r.stdout)
        self.assertIn("isHoneypot", r.stdout)

    def test_unknown_script_returns_nonzero(self):
        r = cli_raw("scripts", "nonexistent")
        self.assertNotEqual(r.returncode, 0)


class LangAliasesTest(unittest.TestCase):
    def test_match_german_vorname(self):
        r = cli("label", "Vorname")
        self.assertEqual(r["field"], "first_name")

    def test_match_spanish_apellidos(self):
        r = cli("label", "Apellidos")
        self.assertEqual(r["field"], "last_name")

    def test_match_french_telephone(self):
        r = cli("label", "Téléphone")
        self.assertEqual(r["field"], "phone")

    def test_match_russian_imya(self):
        r = cli("label", "Ваше имя")
        self.assertEqual(r["field"], "first_name")

    def test_match_consent_phrase(self):
        r = cli("label", "I agree to the privacy policy")
        self.assertEqual(r["field"], "consent")

    def test_match_unknown_returns_null(self):
        r = cli("label", "Random text that matches nothing in our aliases dictionary")
        self.assertIsNone(r["field"])

    def test_detect_lang_de(self):
        r = cli("label", "--detect-lang", "Kontaktieren Sie uns - Datenschutz und Sicherheit der Daten und Privatsphäre der Benutzer")
        self.assertEqual(r["lang"], "DE")


class HsWClientTest(unittest.TestCase):
    """Test the HSW client returns structured response.
    Does not require the HSW service to actually work (service may be down)."""

    def test_invalid_endpoint_returns_unreachable(self):
        r = cli("hcaptcha-hsw", "--rqdata", "foo", "--host", "example.com",
                "--endpoint", "http://127.0.0.1:1/hsw", "--timeout", "3", timeout=10)
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "service_unreachable")

    def test_real_endpoint_returns_structured(self):
        """Service may return 'service_failed' (invalid JWT) — that's OK."""
        r = cli("hcaptcha-hsw", "--rqdata", "foo", "--host", "example.com",
                "--timeout", "5", timeout=15)
        self.assertIn("ok", r)
        self.assertIn("error", r) if not r.get("ok") else None


class CompareTest(unittest.TestCase):
    def setUp(self):
        self.baseline = "/tmp/_test_baseline.json"
        self.after = "/tmp/_test_after.json"
        self.out = "/tmp/_test_compare.md"
        Path(self.baseline).write_text(json.dumps({
            "providers": [
                {"name": "x", "url": "http://x.com", "status": "filled_no_submit"},
                {"name": "y", "url": "http://y.com", "status": "captcha_blocked"},
            ],
            "summary": {"total": 2, "filled_ok": 1, "captcha_blocked": 1},
        }))
        Path(self.after).write_text(json.dumps({
            "providers": [
                {"name": "x", "url": "http://x.com", "status": "filled_no_submit", "fingerprint_applied": ["webdriver", "hardware"], "consent_action": "rejected", "consent_cmp": "OneTrust"},
                {"name": "y", "url": "http://y.com", "status": "filled_no_submit", "captcha": "recaptcha_v2", "captcha_solved": True},
            ],
            "summary": {"total": 2, "filled_ok": 2},
        }))

    def tearDown(self):
        for p in (self.baseline, self.after, self.out):
            try:
                os.unlink(p)
            except OSError:
                pass

    def test_compare_renders_markdown(self):
        r = cli_raw("compare", "--baseline", self.baseline, "--after", self.after, "--out", self.out)
        self.assertEqual(r.returncode, 0)
        body = r.stdout
        self.assertIn("Form-filler T0 vs T1", body)
        self.assertIn("Pass-rate delta", body)
        self.assertIn("Verdict", body)
        # 2 sites went from 1 success to 2 success — +50pp improvement
        self.assertIn("✅", body)  # verdict marker for ≥70%

    def test_compare_writes_file(self):
        cli_raw("compare", "--baseline", self.baseline, "--after", self.after, "--out", self.out)
        self.assertTrue(Path(self.out).exists())
        content = Path(self.out).read_text()
        self.assertIn("Per-site delta", content)


class ImportSanityTest(unittest.TestCase):
    def test_all_submodules_import(self):
        cmd = [
            VENV_PY, "-c",
            "import anti_block.forms; "
            "from anti_block.forms import geo_lookup, recaptcha_v2, cli, lang_aliases, hcaptcha_hsw, compare; "
            "print('OK', anti_block.forms.__version__)"
        ]
        out = subprocess.run(cmd, capture_output=True, text=True, cwd=CWD, timeout=10)
        self.assertEqual(out.returncode, 0, f"stderr: {out.stderr}")
        self.assertIn("OK", out.stdout)


class RecaptchaSolverShapeTest(unittest.TestCase):
    def test_invalid_audio_url_returns_structured_error(self):
        r = cli("recaptcha-v2", "--audio-url", "https://invalid.example.com/no.mp3", timeout=20)
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "download_failed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
