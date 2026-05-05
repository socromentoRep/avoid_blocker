# anti-block toolkit — example cheat-sheet

Replace the contents below with your own. Aim for 1–2k tokens total.
The point is to give the agent a fast reference of the tools you have
already built so it does not improvise under pressure.

## Tools

| problem                          | tool / shortcut                                                  |
|----------------------------------|------------------------------------------------------------------|
| TLS-level WAF (Qrator, etc.)     | `python -m mytools.tls.cli --geo XX get https://example.com/...` |
| JS challenge (CF Turnstile, etc.)| `python -m mytools.browser.cloak https://example.com/`           |
| Captcha (Geetest v4)             | `bash mytools/captcha/<flow>-solve.sh`                           |
| Public methods endpoint          | `python -m mytools.scrape.<platform>`                            |
| Static asset parsing             | `python -m mytools.scrape.bundle <url>`                          |

## Stable identifiers

Some captcha flows use a static `captchaId` — collect them here so the
agent can reuse a known-good token instead of solving a fresh one
every run:

| flow                      | shortcut                          | captchaId            |
|---------------------------|-----------------------------------|----------------------|
| `<flow_a>` deposit redirect | `<flow_a>-solve.sh`             | `<32-char hex>`      |
| `<flow_b>` paywidget       | `<flow_b>-solve.sh`              | `<32-char hex>`      |

## Pre-fetched hints

If your pipeline runs an unblock probe before each agent run, point the
agent at the cached output instead of refetching:

```
cat <project_root>/data/.scan-hints/<target>.json
```

(Make sure this directory is **not** in your hook's deny-list.)

## Decision tree

- ⛔ HTTP 401 / 403 + JS challenge HTML → `browser.cloak`
- ⛔ HTTP 424 on a captcha-protected endpoint → captcha shortcut above
- ⛔ TLS handshake error / self-signed cert → `tls.cli`
- ⛔ Login wall on a known platform → public methods endpoint, skip UI
- ⛔ JS bundle parsing 30+ chunks → `scrape.bundle`

## Principle

If a standard `page.goto` / `curl` failed once, **do not retry it 10
times**. Drop into one of the tools above. Tokens and wall-clock are
both cheaper than blind retries.
