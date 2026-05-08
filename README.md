# avoid_blocker

Toolkit for bypassing anti-bot blockers (Cloudflare WAF, DataDome, Akamai
Bot Manager, Geetest, hCaptcha, TLS-level filtering) without paying for
2captcha / CapSolver / ScrapingBee. Python + Node.js, MIT-license OSS
solvers under the hood.

Built for long-running Claude Code agent sessions that scrape/probe
casinos, e-commerce, fintech sites — but the tools are project-agnostic
and usable from any Python automation pipeline.

## Status

**Alpha**. Battle-tested in one production project (PaymentScout — gambling
PSP intelligence). Not all blockers covered; some require manual
configuration per project (especially registration captchas requiring
HSW tokens).

## What's inside

```
avoid_blocker/
├── hooks/anti-block-inject.js      # Claude Code hook — injects cheatsheet
├── wrapper/claude-with-fallback.sh # Claude CLI wrapper — acc1↔acc2 fallback
├── anti_block/                     # ← The actual bypass tools (Python)
│   ├── tls/                        # TLS-fingerprint impersonation (curl_cffi)
│   ├── proxy/                      # SOAX direct + sessionid rotation
│   ├── browser/                    # CloakBrowser launcher + DOM helpers
│   ├── scrape/                     # JS bundle parsing, SSR state decoders
│   └── captcha/                    # OSS Geetest + hCaptcha solver wrappers
├── captcha/
│   ├── install_chaser_gt.sh        # Geetest v3/v4 solver (Rust, MIT)
│   └── install_hcaptcha_solver.sh  # hCaptcha solver (Python, no API keys)
├── warmup/                         # Cookie warmup runner (anti-WAF)
├── setup/setup_soax_bridges.sh     # Local SOCKS5 bridges for SOAX residential
├── examples/                       # cheatsheet template + Claude settings example
├── deploy.sh                       # Hook + wrapper installer (idempotent)
└── requirements.txt
```

## Quick start

### 1. Install Python deps

```bash
pip install -r requirements.txt
```

### 2. Configure your residential proxy (SOAX example)

If you use SOAX residential proxies (or any SOCKS5 provider with username-
based geo routing), set up local SOCKS5 bridges so chromium-based browsers
(which don't support SOCKS5 with auth) can connect:

```bash
export SOAX_RES_PASSWORD="your-soax-password"
export SOAX_RES_PACKAGE="your-soax-package-id"
bash setup/setup_soax_bridges.sh
```

This starts gost listeners on `127.0.0.1:11080-11090` (one per geo).
The script prints the env var to set:

```bash
export ANTIBLOCK_BRIDGE_PORTS="IN:11080,BR:11082,DE:11085,GB:11088,..."
```

If you use a different proxy provider — write a similar bridge-setup
script. The tools here only need:
- `ANTIBLOCK_BRIDGE_PORTS` env var (geo→port mapping), or
- `SOAX_RES_PACKAGE` + `SOAX_RES_PASSWORD` env vars (for direct SOCKS5 auth via curl_cffi).

### 3. Install captcha solvers (optional)

```bash
bash captcha/install_chaser_gt.sh           # Geetest (Rust)
bash captcha/install_hcaptcha_solver.sh     # hCaptcha (Python)
```

### 4. Use as a Python module

```python
# TLS impersonation HTTP-only fetch (bypasses Qrator, TLS-WAFs)
from anti_block.tls import TLSScoutClient
client = TLSScoutClient(soax_geo='IN')
resp = client.get('https://target-with-tls-waf.com/api/data')

# Per-call SOAX session rotation (when current IP got banned)
from anti_block.proxy.soax_direct import get_with_retry
status, body, headers = get_with_retry('https://target.com/', geo='IN', max_retries=5)

# Decode Aramuz cloaking platform state (find real backend behind redirect chain)
from anti_block.scrape.aramuz_state import decode_pinia_state, extract_endpoints
state = decode_pinia_state(html)
endpoints = extract_endpoints(state)  # → {PIQ_HOST, API_HOST, merchantId, ...}

# Solve Geetest v4
from anti_block.captcha.geetest_chaser import GeetestChaser
solution = GeetestChaser().solve(captcha_id, risk_type='ai', proxy_url=soax_url)

# Solve hCaptcha
from anti_block.captcha.hcaptcha import solve_hcaptcha
result = solve_hcaptcha(sitekey, host, proxy='socks5h://127.0.0.1:11088')
```

### 5. Use as CLI

```bash
# Verify TLS fingerprint matches real Android Chrome 131
python3 -m anti_block.tls.cli check --geo IN

# GET request via TLS impersonation
python3 -m anti_block.tls.cli get https://example.com/ --geo IN

# Direct SOAX call with auto session rotation on tunnel error
python3 -m anti_block.proxy.soax_direct get https://example.com/ --geo IN --retries 5

# Decode window._pinia state from Aramuz-cloaked casino mirror
python3 -m anti_block.scrape.aramuz_state https://mirror-domain.com/ --geo RS --use-bridge

# Solve Geetest captcha (returns JSON token)
python3 -m anti_block.captcha.geetest_chaser <captcha_id> ai

# Solve hCaptcha
python3 -m anti_block.captcha.hcaptcha <sitekey> <host> --proxy socks5h://127.0.0.1:11088
```

## Two layers of how this works

### Layer 1 — Avoidance (most important)

For Cloudflare / DataDome / Akamai — we **don't solve captchas**, we
**avoid them appearing in the first place**.

Three mechanisms:

1. **Cookie warmup cron** (`warmup/cookie_warmup.sh`) — every 6 hours
   opens homepage in anti-detect browser profile, simulates browsing,
   keeps `cf_clearance` / `_abck` / `dd_session` cookies fresh.
   WAF trusts the session and skips the challenge for production scans.

2. **Anti-detect browser** (`anti_block/browser/cloak.py`, CloakBrowser
   open-source) — Chromium with C++-level fingerprint patches that
   simulates a real device. Open homepage in-flight to grab cookies if
   no persistent profile available.

3. **TLS-fingerprint impersonation** (`anti_block/tls/`) — `curl_cffi` with
   exact Android Chrome 131 JA3/JA4. Some WAFs reject only on TLS
   handshake; with correct fingerprint, you pass through to the API
   directly without ever loading JS.

### Layer 2 — Solving (when avoidance fails)

For Geetest and hCaptcha — when avoidance doesn't work and a captcha
modal actually appears — we use **free OSS solvers that run locally**:

- **chaser-gt** (Rust, MIT) — solves Geetest v3/v4 (slide / icon /
  gobang / AI). Same approach as paid services, just published in OSS.
  https://github.com/0xchasercat/chaser-gt
- **hcaptcha-ai-solver** (Python) — uses tls_client + ML motion data
  generation. No API keys.
  https://github.com/korolossamy/hcaptcha-ai-solver

Trade-offs vs paid (2captcha / CapSolver):
- ✅ Free, no API keys
- ✅ Runs locally
- ❌ 85-95% success rate (vs 99% for paid)
- ❌ May lag behind captcha-engine updates (OSS gets patched, but with delay)

For research / reconnaissance pipelines (low-volume) — OSS is fine.
For high-traffic production arbitrage — paid is more reliable.

## Hook + wrapper (existing infrastructure layer)

Pre-existing in this repo, unchanged by the toolkit additions:

- **`hooks/anti-block-inject.js`** — Claude Code hook that injects
  a project-specific cheatsheet (markdown file) into every agent session
  via `additionalContext`. Configure via env vars:

  ```
  ANTI_BLOCK_HOOK_CHEATSHEET=/path/to/your-cheatsheet.md   # required
  ANTI_BLOCK_HOOK_CWD_PREFIX=/path/to/your/project          # only fire for this project
  ANTI_BLOCK_HOOK_PROBE_PATH=/path/to/anti_block            # sanity-check that toolkit installed
  ```

  The cheatsheet should map blockers → tool/command. Example:
  `examples/cheatsheet.example.md`.

- **`wrapper/claude-with-fallback.sh`** — runs `claude` CLI with two
  `CLAUDE_CONFIG_DIR` profiles, switches on rate-limit detection.
  See `README.md` section in main repo for env var setup.

- **`deploy.sh`** — copies hook + wrapper into `~/.claude/hooks/` and
  `~/bin/`. Does NOT touch your `settings.json` or install Python deps.
  Run `pip install -r requirements.txt` separately if you use the
  `anti_block/` toolkit.

## What's NOT covered

These blockers require either paid services or manual workarounds:

| Blocker | Status |
|---|---|
| reCAPTCHA v2/v3 (Google) | No free OSS solver works reliably in 2026. Use VNC manual or pay 2captcha/CapSolver. |
| Akamai `_abck` (sensor_data generation) | Free path is "real Chrome via CDP-clean tools" (nodriver, patchright, rebrowser-playwright). For 99% generation needs paid (capsolver $3-5/1k). |
| PerimeterX `_px3` | Same as Akamai — free via real-Chrome-fingerprint, paid for guaranteed gen. |
| FunCaptcha (Arkose Labs) | Paid CapSolver-only currently. |
| Server-side IP block of ALL datacenter ASN | Need residential ISP-tier proxy (BrightData/IPRoyal/etc, paid $5-15/GB) or DIY Raspberry Pi at someone's home. |
| Mobile carrier IP requirement | Need 4G mobile proxy (Proxidize DIY $50-100/IP, AirProxy etc). |

For each of these — fallback to manual VNC interaction or pay the
provider. Document them in your cheatsheet so the agent doesn't loop on
unsolvable cases.

## Architecture for project integration

```
Your scraper / agent
        ↓ (when blocker hit)
   anti_block.<module>.<tool>
        ↓ (Python or shell call)
   ┌─────────┬──────────┬──────────┬───────────┐
   │ TLS     │ Browser  │ Solvers  │ Proxy     │
   │ ja3/4   │ Cloak    │ chaser-gt│ SOAX      │
   │ curl_cffi│ Camoufox │ hCaptcha │ rotation  │
   └─────────┴──────────┴──────────┴───────────┘
                          ↓
                   Bridge :11080-11090 (gost)
                          ↓
                   SOAX residential / mobile
```

Connect Claude Code agent: drop `cheatsheet.md` in your project, point
the hook at it via `ANTI_BLOCK_HOOK_CHEATSHEET` env var, and your agent
will see all available tools at session start.

## License

Hook + wrapper: no license set (internal tooling). The `anti_block/`
Python tools — feel free to use under any permissive terms.

External OSS solvers retain their own licenses:
- chaser-gt: MIT
- hcaptcha-ai-solver: see repo
- CloakBrowser: see repo
- curl_cffi: MIT

## Contributing

Add new blocker bypasses? PRs welcome. Keep them:
- Free / OSS only (paid API wrappers belong in your project, not here)
- Project-agnostic (no hardcoded paths, geo lists, brand-specific URLs)
- Documented (one-line use case + code example)
