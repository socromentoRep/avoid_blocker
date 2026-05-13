# anti_block.forms — Form-filler anti-block extensions

Anti-block helpers specifically for the **Hermes form-filler skill** (outreach contact-form fills on PSP corporate websites). Separate from the casino scan stack (`anti_block.browser.cloak`, `anti_block.tls.cli`, etc.) because the threat model is different:

| Aspect | Casino scan | Form-filler |
|---|---|---|
| Target sites | online gambling (geo-restricted, aggressive WAF) | corporate PSPs (mostly global, softer WAF) |
| Primary proxy | SOAX residential per geo (always on) | direct DC IP first, SOAX conditional |
| Captcha frequency | reCAPTCHA rare (17/week, all v2) | reCAPTCHA on submit common; cookie banners always |
| Submit action | Yes (fund deposit flow) | **NEVER** — fill-only test mode |
| Browser stack | Claude Code + patchright via mcpslim-bridge | Hermes built-in browser tool (agent-browser / camofox) |

## Modules

### `anti_block.forms.geo_lookup`
Resolve a provider name / URL → ISO country → SOAX bridge port. Used to decide *whether and from which geo* to retry a request after a direct DC-IP attempt failed with 403/429.

```bash
python3 -m anti_block.forms.geo_lookup --provider bharatpe --url https://bharatpe.com/contact
# → {"geo": "IN", "source": "keyword", "bridge_port": 11080, "socks5_url": "socks5://127.0.0.1:11080"}

python3 -m anti_block.forms.geo_lookup --provider paysafe --url https://paysafe.com/
# → {"geo": null, "source": "none", "bridge_port": null}  # global PSP, no proxy needed
```

Resolution order: `providers.country` DB column → URL ccTLD → keyword heuristic.

### `anti_block.forms.recaptcha_v2`
Audio-challenge transcriber for reCAPTCHA v2. Does **not** spawn a second browser — caller (Hermes skill) extracts the audio URL from the running browser session and pipes it here. Pipeline: download `.mp3` (via `curl_cffi` for TLS-imp.) → convert to 16kHz WAV (`pydub`) → transcribe (`SpeechRecognition` / Google Speech free API).

```bash
python3 -m anti_block.forms.recaptcha_v2 \
  --audio-url "https://www.google.com/recaptcha/api2/payload?..." \
  --proxy socks5://127.0.0.1:11080
# → {"ok": true, "text": "the quick brown fox", "duration_s": 4.2}
```

Reliability: 55-70% on vanilla reCAPTCHA v2. **Not** designed for reCAPTCHA Enterprise (gambling sites) — those need paid solvers.

### `anti_block.forms.cli`
Unified dispatcher for Bash invocations from the skill. Three subcommands:

```bash
# 1. Geo lookup (re-exports forms.geo_lookup)
python3 -m anti_block.forms.cli geo --provider <name> --url <url>

# 2. reCAPTCHA v2 (re-exports forms.recaptcha_v2)
python3 -m anti_block.forms.cli recaptcha-v2 --audio-url <URL>

# 3. Print JS bundle to stdout (for direct pipe into browser_evaluate)
python3 -m anti_block.forms.cli scripts fingerprint    # anti-fingerprint overrides
python3 -m anti_block.forms.cli scripts autoconsent    # cookie banner dismisser
python3 -m anti_block.forms.cli scripts form-inspect   # form + captcha detector
python3 -m anti_block.forms.cli scripts list           # show available
```

### `anti_block.forms.scripts/`

| File | Purpose |
|---|---|
| `fingerprint_overrides.js` | Apply navigator/WebGL/connection overrides to defeat trivial bot checks. Mirrors `prompts/shared/_anti-fingerprint.md`. Idempotent. |
| `autoconsent_inject.js` | Hand-rolled cookie consent dismisser. Detects 15 top CMPs (OneTrust, Cookiebot, Iubenda, Didomi, cmplz, Borlabs, Quantcast, Osano, Klaro, Usercentrics, CivicUK, Sourcepoint, CookieYes, Termly, TrustArc + generic). Clicks **Reject all** preferentially, else Accept all. **Never** clicks submit/send. |
| `form_inspector.js` | Returns structured forms[] + captcha.{recaptcha_v2/v3, hcaptcha, turnstile, geetest, friendly_captcha} + iframes + JS frameworks detected. Tuned for corporate contact forms (label-driven mapping). |

## Hermes skill integration

The form-filler skill `outreach-form-test` (in `~/.hermes/skills/`) uses these modules via Bash + browser_evaluate per the workflow in its SKILL.md:

1. **Pre-flight**: `forms.cli geo` → know which geo to retry from if direct fails.
2. **Navigate** → direct DC IP first.
3. **Inject fingerprint** via `forms.cli scripts fingerprint` piped to `browser_evaluate`.
4. **Dismiss consent** via `forms.cli scripts autoconsent` piped to `browser_evaluate`.
5. **Inspect** via `forms.cli scripts form-inspect` — get fields + captcha.
6. **Fill** (no submit) using browser_type / browser_select_option / browser_click.
7. **Captcha (if vanilla v2 invisible)**: `forms.cli recaptcha-v2 --audio-url ...`.
8. **Screenshot** + move on.

## Architecture decisions

- **Why audio-only reCAPTCHA solver?** sarperavci/GoogleRecaptchaBypass and PyPasser spawn a second DrissionPage Chromium — conflicts with Hermes running browser. Audio-only reuses existing infra (just `curl_cffi` + `pydub` + `speech_recognition`).
- **Why hand-rolled autoconsent?** ddg/autoconsent is 400KB bundle, many corp PSP sites use non-standard markup not in autoconsent rules. Hand-rolled is 8KB, covers 15 CMPs, deterministic.
- **Why no Camofox by default?** Hermes browser tool supports Camofox-browser via `CAMOFOX_URL` env. Not enabled by default — turn on if pass rate < 70% on test runs.
- **Why no second MCP server?** Hermes uses built-in `tools/browser_tool.py`, not MCP. Our helpers integrate via Bash + `browser_evaluate` — no Hermes config changes.

## Testing

Smoke tests live in `tests/`:

```bash
# Geo lookup smoke
python3 -m anti_block.forms.cli geo --provider bharatpe --url https://bharatpe.com/contact
python3 -m anti_block.forms.cli geo --url https://provider.de/kontakt

# Scripts dispatcher
python3 -m anti_block.forms.cli scripts list
python3 -m anti_block.forms.cli scripts fingerprint | head -3
```

End-to-end test through Hermes skill is documented in `~/Desktop/FormFiller-AntiBlock-Plan-2026-05-13.md` (T0 baseline + T1 after build).

## Dependencies

Already in `.venv-antiblock`:
- `curl_cffi` (TLS impersonation for audio download)
- `pydub` (mp3 → wav conversion)
- `SpeechRecognition` (Google Speech free API)
- `ffmpeg` (system-wide, used by pydub)

Installed 2026-05-13: SpeechRecognition 3.16.1 + pydub 0.25.1.

## Version

`__version__ = "0.1.0"` — initial drop, 2026-05-13.

## Changelog

- **0.1.0 (2026-05-13)**: initial. M0-M8 from Master Plan. Audio-only reCAPTCHA, hand-rolled autoconsent, 15-CMP coverage, DB+TLD+keyword geo lookup, anti-fingerprint mirroring scan-side.
