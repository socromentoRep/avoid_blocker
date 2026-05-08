# avoid_blocker

**Free OSS toolkit** для обхода anti-bot блокеров (Cloudflare WAF, DataDome, Akamai
Bot Manager, Geetest, hCaptcha, TLS-fingerprint фильтры) — **без paid API
сервисов** типа 2captcha / CapSolver / ScrapingBee / ZenRows.

Использует только open-source компоненты (MIT/BSD licenses) которые работают
**локально**. Все captcha solvers и antidetect browser в комплекте — clone +
build, никаких подписок и API keys.

Работает как Python библиотека или CLI, плюс Claude Code hook + wrapper
для AI-агентных пайплайнов.

## TL;DR — что ты получаешь бесплатно

Все компоненты toolkit'а — **free OSS**:

| Что | Какой OSS под капотом | Стоимость |
|---|---|---|
| TLS impersonation (Chrome 131 Android) | `curl_cffi` (MIT) | $0 |
| Anti-detect browser | `cloakbrowser` (MIT) — Chromium с C++ source-level патчами | $0 |
| Geetest v3/v4 solver | `chaser-gt` (Rust, MIT) | $0 |
| hCaptcha solver | `korolossamy/hcaptcha-ai-solver` (Python) | $0 |
| Aramuz cloaking decoder | own code | $0 |
| JS bundle parser | own code | $0 |
| Cookie warmup runner | own bash + Playwright | $0 |
| Claude Code session hook | own JS | $0 |
| Account fallback wrapper | own bash | $0 |

Единственное что не входит в репо но **может** понадобиться (опционально):
- **Residential / mobile proxy** — для качественного IP. Можно free options
  (mobile DIY на старом Android, free residential pools, VPN), можно платных
  ($50-170/мес за SOAX/BrightData/IPRoyal). Toolkit работает **с любым**
  SOCKS5/HTTP proxy — задаёшь через env vars.
- **VPS** — любой Linux/WSL, $5/мес от любого хостера или свой домашний box.

## Что это покрывает

| Блокер | Подход | Tool |
|---|---|---|
| TLS-fingerprint WAF (Qrator, custom) | curl_cffi с Chrome 131 Android | `anti_block.tls.cli` |
| Cloudflare Turnstile / Bot Fight Mode | Cookie warmup + CloakBrowser | `warmup/`, `anti_block.browser.cloak` |
| DataDome device check | CloakBrowser + per-call SOAX rotation | `anti_block.browser.cloak`, `anti_block.proxy.soax_direct` |
| Akamai `_abck` (basic) | CloakBrowser с реальным Chrome fingerprint | `anti_block.browser.cloak` |
| Geetest v3 / v4 (slide / icon / AI) | OSS chaser-gt Rust solver | `anti_block.captcha.geetest_chaser` |
| hCaptcha (включая registration forms) | OSS hcaptcha-ai-solver | `anti_block.captcha.hcaptcha` |
| Aramuz / cloaking redirects | Pinia LZString state decoder | `anti_block.scrape.aramuz_state` |
| Hidden form fields (registration submit disabled) | DOM inspector JS snippet | `anti_block.browser.inspect_form.js` |
| 1xbet platform public xpay endpoint | API client | `anti_block.scrape.xpay` |
| SOAX session HTTP 500 / banned IP | Per-call sessionid rotation | `anti_block.proxy.soax_direct` |

**Что НЕ покрывает** (нужны paid сервисы или manual workarounds):
- reCAPTCHA v2/v3/Enterprise (Google) — нет рабочего free OSS solver'а 2026.
  Use VNC manual или paid 2captcha/CapSolver.
- Akamai с serious sensor_data validation, PerimeterX `_px3`, FunCaptcha
  (Arkose) — paid solvers (CapSolver $3-5/1k) для гарантированной генерации.
- Server-side block ВСЕХ datacenter ASN — нужен residential ISP-tier proxy
  (paid $5-15/GB) или DIY (Raspberry Pi на чьём-то домашнем интернете).

## Quick start (минимальный free setup)

Достаточно: Linux/macOS/WSL с Python 3.10+, Node.js, Rust toolchain (rustup).
Всё опциональное добавляется когда понадобится.

```bash
# 1. Clone
git clone https://github.com/socromentoRep/avoid_blocker.git
cd avoid_blocker

# 2. Python deps (free OSS pip packages)
pip install -r requirements.txt

# 3. Captcha solvers (clone OSS репо + build, free)
bash captcha/install_chaser_gt.sh           # Geetest, Rust binary
bash captcha/install_hcaptcha_solver.sh     # hCaptcha, Python clone

# 4. (Optional) Local proxy bridges if you have SOCKS5+auth provider
#    See setup/setup_soax_bridges.sh — adapt to any provider
```

Готово. Всё что в `anti_block/` теперь импортируемо как Python пакет.

### Use as Python library

```python
# 1. TLS impersonation (no proxy required for direct sites)
from anti_block.tls import TLSScoutClient
client = TLSScoutClient(soax_geo='IN')  # geo only matters if you set env vars
resp = client.get('https://example.com/api/data')

# 2. Aramuz cloaking platform decode (works on any input HTML)
from anti_block.scrape.aramuz_state import decode_pinia_state, extract_endpoints
state = decode_pinia_state(html_string)
endpoints = extract_endpoints(state)  # {PIQ_HOST, API_HOST, merchantId, ...}

# 3. Geetest v4 solve (free, no API keys)
from anti_block.captcha.geetest_chaser import GeetestChaser
solution = GeetestChaser().solve(captcha_id, risk_type='ai')

# 4. hCaptcha solve (free, no API keys)
from anti_block.captcha.hcaptcha import solve_hcaptcha
result = solve_hcaptcha(sitekey, host)  # proxy optional

# 5. CloakBrowser (free MIT, anti-detect Chromium)
from anti_block.browser.cloak import fetch_page
result = fetch_page('https://target.com/', geo='IN')  # geo only used if bridge configured
```

### Use as CLI

```bash
# Verify TLS fingerprint matches real Chrome 131 Android
python3 -m anti_block.tls.cli check --no-proxy

# GET request via TLS impersonation
python3 -m anti_block.tls.cli get https://example.com/

# Decode Aramuz Pinia state from HTML
python3 -m anti_block.scrape.aramuz_state https://target.com/ --geo IN

# Solve Geetest captcha
python3 -m anti_block.captcha.geetest_chaser <captcha_id> ai

# Solve hCaptcha
python3 -m anti_block.captcha.hcaptcha <sitekey> <host>
```

## С proxy (любой провайдер)

Toolkit работает с **любым** SOCKS5/HTTP proxy — provider-agnostic.

### Вариант A: SOAX residential (если у тебя есть аккаунт)

```bash
export SOAX_RES_PACKAGE="your-package-id"
export SOAX_RES_PASSWORD="your-password"
# Optional: SOAX_RES_HOST (default: proxy.soax.com), SOAX_RES_PORT (default: 5000)

# Start local SOCKS5 bridges (chromium can't auth SOCKS5, so we strip auth via gost):
bash setup/setup_soax_bridges.sh
# Output prints: export ANTIBLOCK_BRIDGE_PORTS="IN:11080,BR:11082,..."

# Now anti_block.tls/scrape/browser will route through bridges per geo
python3 -m anti_block.tls.cli get https://example.com/ --geo IN
```

### Вариант B: любой другой proxy (BrightData, IPRoyal, mobile DIY, VPN, etc)

Toolkit ожидает **либо** `SOAX_RES_*` env vars (для direct SOCKS5 with auth),
**либо** `ANTIBLOCK_BRIDGE_PORTS="GEO:port,GEO:port,..."` env var (для local
listeners без auth).

Если твой provider даёт SOCKS5 без auth (или auth через IP whitelist) — просто
запусти его на любом порту и укажи в `ANTIBLOCK_BRIDGE_PORTS`. Адаптируй
`setup/setup_soax_bridges.sh` если нужно поднять gost-listeners.

### Вариант C: совсем без proxy (для тестов)

Многие сайты пускают TLS-correct запросы без proxy. Просто пропусти env var
setup — `TLSScoutClient` сделает direct connection, `cookie_warmup.sh`
будет работать с твоим обычным IP.

## Cookie warmup — free path

Cookie warmup поддерживает любой anti-detect browser с persistent profiles.
Default рекомендация — **CloakBrowser** (free MIT, уже в `requirements.txt`).
Если используешь Dolphin Anty / GoLogin / AdsPower / Camoufox — также работает.

```bash
# 1. Edit warmup/cookie_warmup.sh — fill SITE_URLS array with your sites:
#    [profile_name]="https://homepage.com"

# 2. Add to cron (every 6 hours, between your scan batches):
crontab -e
# 0 3,9,15,21 * * * /path/to/avoid_blocker/warmup/cookie_warmup.sh

# 3. (Optional) Add Dolphin Anty integration if you use it.
#    For CloakBrowser-only setup, edit warmup_browser.js to use:
#    `chromium.launchPersistentContext('/path/to/profile')` instead of CDP connect.
```

Если не хочешь возиться с anti-detect browser — toolkit и без warmup пройдёт
многие WAFs через TLS impersonation + free residential alternative.

## Claude Code agent integration (для AI-pipeline'ов)

Если ты используешь Claude Code (Cursor / native CLI) для автоматизации
scout / scrape — есть hook который инжектит project-specific cheatsheet в
каждую агентную сессию.

```bash
# 1. Install hook + wrapper:
bash deploy.sh    # копирует hooks/ + wrapper/ в ~/.claude/hooks и ~/bin

# 2. Set env var pointing to YOUR cheatsheet:
export ANTI_BLOCK_HOOK_CHEATSHEET=/path/to/your-cheatsheet.md
export ANTI_BLOCK_HOOK_CWD_PREFIX=/path/to/your/project

# 3. Wire hook in ~/.claude/settings.json (see examples/settings.minimal.json)

# 4. Write cheatsheet — Site→Tool quick map for your project.
#    Template: examples/cheatsheet.example.md
#    Goal: keep it ~1-2k tokens, point to commands not paragraphs.
```

При следующем запуске Claude Code session увидит cheatsheet как
`additionalContext` и будет использовать tools без блужданий.

`wrapper/claude-with-fallback.sh` отдельно — оборачивает `claude` CLI
переключателем acc1↔acc2 при rate-limit (если у тебя несколько аккаунтов).

## Архитектура

```
Your scraper / agent / Claude Code
        │
        ▼  (when blocker hit)
   anti_block.<module>.<tool>
        │
   ┌────┴────┬─────────┬──────────┬──────────┐
   │  TLS    │ Browser │ Solvers  │  Proxy   │
   │ ja3/ja4 │ Cloak   │ chaser-gt│ rotation │
   │curl_cffi│         │ hCaptcha │          │
   └────┬────┴────┬────┴────┬─────┴────┬─────┘
        │         │         │          │
        └─────────┴─────────┴──────────┘
                  │
            (env-driven)
                  │
        ┌─────────┴─────────┐
        │ Local bridges     │  ANTIBLOCK_BRIDGE_PORTS="GEO:port,..."
        │ (gost SOCKS5)     │  
        └─────────┬─────────┘
                  │
        ┌─────────┴─────────┐
        │ Your proxy        │  SOCKS5/HTTP — anything: SOAX, BrightData,
        │ provider          │  IPRoyal, mobile DIY, VPN, free pools
        └───────────────────┘
```

## What's inside

```
avoid_blocker/
├── hooks/anti-block-inject.js      # Claude Code SessionStart hook
├── wrapper/claude-with-fallback.sh # Claude CLI acc1↔acc2 fallback
├── anti_block/                     # ── Bypass tools (Python) ──
│   ├── tls/                        #    TLS-fingerprint impersonation
│   ├── proxy/                      #    SOAX direct + sessionid rotation
│   ├── browser/                    #    CloakBrowser launcher + DOM helpers
│   ├── scrape/                     #    JS bundle / SSR state decoders
│   └── captcha/                    #    Free OSS solver wrappers
├── captcha/
│   ├── install_chaser_gt.sh        # Geetest solver clone+build (Rust)
│   └── install_hcaptcha_solver.sh  # hCaptcha solver clone (Python)
├── warmup/                         # Cookie warmup runner + Playwright
├── setup/setup_soax_bridges.sh     # Optional SOCKS5-with-auth bridges
├── examples/                       # cheatsheet template + Claude settings
├── deploy.sh                       # Hook + wrapper installer (idempotent)
└── requirements.txt
```

## Requirements

Minimum (для core tools):
- Python 3.10+
- `pip install -r requirements.txt`

Optional (на тулзу):
- Node.js — для `inspect_form.js` (через browser_evaluate) и `warmup_browser.js`
- Rust toolchain — для chaser-gt (auto-installed by `install_chaser_gt.sh` if missing)
- `gost` binary — для SOCKS5-with-auth bridges (https://github.com/ginuerzh/gost/releases)

## Contributing

PRs welcome. Keep contributions:
- **Free / OSS only** (paid API wrappers belong in your private project)
- **Project-agnostic** (no hardcoded paths, geo lists, or brand-specific logic
  — see how `xpay.py` keeps its registry as a starter you extend)
- **Documented** (one-line use case + code example in module docstring)

## License

Hook + wrapper: no license set (internal tooling, free to fork).
The `anti_block/` Python tools — feel free to use under any permissive terms.

External OSS dependencies retain their own licenses:
- chaser-gt: MIT
- hcaptcha-ai-solver: see repo
- CloakBrowser: MIT
- curl_cffi, lzstring, PyYAML: MIT/BSD
