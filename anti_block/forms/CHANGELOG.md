# Changelog — anti_block.forms

## 0.3.0 (2026-05-13 — evening, after real-world testing)

End-to-end submit testing на реальных сайтах + findings from production-like
runs. Skill hardening против известных Hermes/OpenAI квирков.

### Verified in production-like conditions
- **Stage 0 — testing playgrounds (8 сайтов через Hermes)**: 8/8 = 100% pass.
  Полный workflow: navigate → fingerprint → autoconsent → form-inspect →
  fill → submit → verify. Реальный Cookiebot dismissed на lambdatest.
- **Stage 0.5 — corporate sites (10 целей, 6 обработано до safety block)**:
  - `autoconsent` подтверждён на live Cookiebot, OneTrust (выявлено в pre-flight),
    Osano, GenericRoleDialog
  - `fingerprint_overrides` — 8/8 applied на всех 14 pre-flight сайтах
  - `form_inspector` обнаружил reCAPTCHA v3 на mailchimp + потенциально v2 на
    hubspot (lazy-loaded — не виден в первом inspect)

### Found in production-like testing — known issues
- **OpenAI gpt-5.4 safety filter блокирует** попытки Hermes создавать
  background CORS proxy servers (`/tmp/cors_server.py`) для XHR bypass.
  Cancel'ит ВСЮ сессию. **Mitigation**: skills updated с явным запретом
  таких подходов.
- **Hermes built-in browser tool имена ОТЛИЧАЮТСЯ от MCP-стиля**:
  `browser_console` вместо `browser_evaluate`, `browser_vision` вместо
  `browser_take_screenshot`. **Mitigation**: skills updated с корректными
  именами.
- **Pre-flight inaccurate для lazy-loaded captcha**: standalone playwright
  pre-flight на hubspot.com показал `captcha=-`, но Hermes-side обнаружил
  reCAPTCHA v2. Captcha loads после первой interaction.
  **Mitigation**: skills updated — после первого inspect повторять через 3-5s
  если в page text появилось "protected by reCAPTCHA".
- **CLI args** — Hermes иногда вызывал CLI без required args (получал
  `usage:` help). **Mitigation**: skills указывают правильные примеры.

### Updated
- **3 SKILL.md updated** with HARD RULES section (added 2026-05-13):
  - `outreach-form-corporate-submit/SKILL.md` (168 → 219 lines)
  - `outreach-form-real-submit/SKILL.md` (168 → 209 lines)
  - `outreach-form-test/SKILL.md` (261 → 300 lines)
- Все 3 теперь содержат:
  - Точные имена Hermes built-in tools
  - Hard ban на background CORS proxy
  - Правильные CLI examples
  - Lazy-loaded captcha re-inspect rule

### Added (new artefacts)
- **`outreach-form-corporate-submit` skill** (new) — для real corporate
  sites stress test (CRM/cloud/dev tools, не PSP). Email auto-bounce
  через example.com. 10 целей с pre-flight data.
- **`/tmp/forms_preflight.py`** — standalone playwright проверка 14 целей
  → JSON отчёт + recommendations table.

## 0.2.0 (2026-05-13 — afternoon hardening)

Before-T0 hardening pass. Multi-language forms, honeypot avoidance, HSW
captcha, comparison reporting.

### Added
- **`anti_block.forms.lang_aliases`** — 8 languages (EN/DE/FR/ES/PT/IT/RU/PL),
  18 profile fields × 5-10 patterns each = ~130 regex aliases.
- **`anti_block.forms.hcaptcha_hsw`** — thin client for local Flask HSW service.
- **`anti_block.forms.compare`** — T0 vs T1 diff with verdict.
- **CLI subcommands**: `label`, `hcaptcha-hsw`, `compare` (total 6).
- **Honeypot detection** in `form_inspector.js` — 4 heuristics.
- **9 additional CMP detectors** (total 26): CookieScript, Cookiehub, Crownpeak,
  Piwik PRO, Ezoic, AdRoll, Termly v2, StripeCustom, GenericRoleDialog.
- **Smoke tests**: 12 → 25 cases (all green).

### Infrastructure
- **systemd unit `hcaptcha-hsw.service`** on `:5000`, enabled on boot.
- Dependencies: Flask 3.1.3, httpx 0.28.1, PyJWT 2.12.1.
- `test_profile.yaml` 23 → 120 lines (all 30 form categories covered).

## 0.1.0 (2026-05-13 — morning initial drop)

Initial M0-M8 package + Hermes skill integration.

### Added
- `geo_lookup.py`, `recaptcha_v2.py` (audio-only solver), `cli.py`
- 3 JS bundles: `fingerprint_overrides.js`, `autoconsent_inject.js`
  (15 CMPs initially), `form_inspector.js` (6 captcha types)
- 12 smoke tests
- `outreach-form-test` skill updated 123 → 261 lines with TB-1..TB-6 toolbox
- Dependencies: SpeechRecognition 3.16.1, pydub 0.25.1

---

## Bonus tooling (2026-05-13 evening)

### `scripts/recover_summary.py` (new, in `/opt/payment-scout/scripts/`)

Recovery tool для случая когда `reports/YYYY-MM-DD-summary.md` не дописан
(Claude hit Anthropic rate limit / crash во время Edit summary шага).

Читает БД scans + scan_providers + YAML `data/sites/<slug>.yaml` и
генерирует markdown-entry в формате matching существующие записи.

Usage:
```bash
# preview what's missing for a given date
python3 scripts/recover_summary.py --date 2026-05-13 --dry-run

# recover only specific sites
python3 scripts/recover_summary.py --date 2026-05-13 --site ivybet-de --site spinaura-fr

# recover all missing
python3 scripts/recover_summary.py --date 2026-05-13
```

Idempotent: skip sites already present (matched by `^## <slug>` heading).

### Why needed
- Claude обновляет `reports/YYYY-MM-DD-summary.md` сам через Edit-tool
  как один из последних шагов scan workflow.
- Когда Claude hit Anthropic rate limit (acc1/acc2 seven_day_sonnet RL) —
  он завершает текущий scan, БД + scan_providers + YAML заполняются ingest-ом,
  но **summary.md update Claude не успевает** перед kill.
- **2026-05-13**: 19 scans в БД за день, но в summary.md попали только 2.
  17 missing — все из-за RL hit'ов acc1/acc2 в течение дня.
- БД данные корректные — `recover_summary.py` догенеривает entries из БД.

### Output format

Header marked `(recovered)` для traceability:
```
## ivybet-de (scan_id=1710 — partial — recovered)
- **URL:** ...
- **Platform:** ...
- **Source:** recover_summary.py (post-RL recovery)
### Providers
| Provider | Confidence | Methods |
| ... | ... | ... |
### Scan notes (from yaml)
```

Так понятно что entry post-fact восстановлен (не Claude live во время scan).

---

## fix #79 (2026-05-13 evening late) — anti_block.forms integrated в enrichment skill

### Trigger
В первых 2 iter'ах nightly-enrichment-blast обнаружено **13 mentions cookie banner**
(Cookiebot и др.), 6 × HTTP 403, 6 × cloudflare, 6 × captcha — Hermes сталкивался
с блокерами, но **anti_block.forms toolkit не был подключён к `enrichment` skill**.

Пример: на tranzzo.com Hermes видел "This website uses cookies" dialog на **каждой**
из 5 navigated страниц (homepage, /contact, /contacts, /about, /igaming) — модал
перекрывал контент, Hermes не закрывал.

### Changes
- `/home/deploy/.hermes/skills/enrichment/SKILL.md` (production, 3246 → 3352 lines)
  - Backup: `SKILL.md.bak-pre-antiblock-20260513`
  - Добавлен new section "🛡️ ANTI-BLOCK TOOLBOX (added 2026-05-13 evening)"
  - TB-1: autoconsent (most important — Hermes должен dismiss banner FIRST после navigate)
  - TB-2: anti-fingerprint overrides
  - TB-3: form inspector для structured form data
  - TB-4: conditional SOAX retry на 403 / region-block
  - TB-5: multi-language field label matching
  - Decision tree per encounter type
  - SAFE MODE rules для enrichment (no submit, no background servers)

### Idempotent rollout
- Production blast running (PID 3824400) НЕ перезапускался
- Hermes reads skill at start of each iter — обновление подхватится в Iter 4+
  (текущая Iter 3 заканчивается ~21:42 UTC, Iter 4 стартует ~21:45)
- Backwards-compatible: addendum только добавляет tools, не меняет existing logic

### Expected impact
- Cookie banner mentions: 13/2 iters → ожидаемо 0/iter (autoconsent dismiss'ит)
- HTTP 403 with possible SOAX recovery via TB-4 (tls.cli with geo)
- Captcha-protected forms: правильно записываются как channel=form (не submit attempt)

### Verification после Iter 4
```bash
# Compare blocker mention counts iter 3 (без addendum) vs iter 4+ (с addendum)
python3 -c "import json; d=json.load(open('<iter4_session>')); print(sum(1 for m in d['messages'] if 'cookie' in str(m).lower()))"
```
