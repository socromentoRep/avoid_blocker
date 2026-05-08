#!/bin/bash
# cookie_warmup.sh — generic cookie warmup runner для anti-detect browser profiles.
#
# Идея: WAF (Cloudflare Turnstile, DataDome device-check, Akamai _abck) доверяют
# сессии "с историей". Если профиль регулярно открывает homepage сайта с residential
# IP, имитирует human-like browsing (scroll, dwell, navigation), закрывает —
# cookies (cf_clearance, dd_session, _abck, h_token) обновляются и WAF не выдаёт
# challenge при следующем "production" использовании этого профиля.
#
# Запускается через cron каждые 6 часов. Идеально планировать на промежутки
# между production использованием профилей (например 03/09/15/21 UTC если
# production cron 06/12/18 UTC).
#
# Требования:
# - Anti-detect browser с persistent profiles (например Dolphin Anty, GoLogin,
#   AdsPower, или OSS Camoufox с --user-data-dir).
# - Скрипт ниже сделан под Dolphin Anty API (Local API на 127.0.0.1:3001),
#   но легко адаптируется под любой profile-based browser.
# - Playwright или Puppeteer для управления страницей через CDP endpoint.
#
# Configuration:
# - Edit SITE_URLS array below: profile_id → homepage URL.
# - Set DOLPHIN_API_HOST env var if not localhost:3001.
#
# Logs: /var/log/cookie-warmup.log (or env LOG_FILE)
#
# Skip if production batch is currently running (configurable via PROD_RUNNING_CHECK env).

set -u

LOG_FILE="${LOG_FILE:-/var/log/cookie-warmup.log}"
LOCK_FILE="${LOCK_FILE:-/tmp/cookie-warmup.lock}"
DOLPHIN_API_HOST="${DOLPHIN_API_HOST:-127.0.0.1:3001}"
WARMUP_JS="${WARMUP_JS:-$(dirname "$0")/warmup_browser.js}"

# Map profile name → site homepage. Edit this for your project.
declare -A SITE_URLS=(
    # [profile_name_in_dolphin]="https://homepage_url.com"
    # Example:
    #   [my-site-1]="https://example1.com"
    #   [my-site-2]="https://example2.com"
)

# Skip warmup if a production batch is running.
# Define PROD_RUNNING_CHECK as a command that returns 0 if batch in progress.
PROD_RUNNING_CHECK="${PROD_RUNNING_CHECK:-}"

log() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >> "$LOG_FILE"
}

# Lock to prevent overlap
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    log "Another warmup instance running, skip."
    exit 0
fi

if [ -n "$PROD_RUNNING_CHECK" ] && eval "$PROD_RUNNING_CHECK"; then
    log "Production batch detected, skip warmup."
    exit 0
fi

if [ ${#SITE_URLS[@]} -eq 0 ]; then
    log "No SITE_URLS configured, nothing to do. Edit cookie_warmup.sh."
    exit 0
fi

log "=== Warmup start ==="

for profile in "${!SITE_URLS[@]}"; do
    url="${SITE_URLS[$profile]}"
    log "warmup profile=$profile url=$url"

    # 1. Start Dolphin profile via Local API
    start_resp=$(curl -sS -X GET "http://$DOLPHIN_API_HOST/v1.0/browser_profiles/$profile/start?automation=1" --max-time 30 || echo "{}")
    cdp_endpoint=$(echo "$start_resp" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('automation', {}).get('wsEndpoint', ''))" 2>/dev/null || echo "")
    if [ -z "$cdp_endpoint" ]; then
        log "  FAIL: cannot start profile $profile (response: $start_resp)"
        continue
    fi

    # 2. Run warmup script via Node + Playwright (or Puppeteer)
    if [ -f "$WARMUP_JS" ]; then
        timeout 90 node "$WARMUP_JS" --cdp "$cdp_endpoint" --url "$url" >> "$LOG_FILE" 2>&1 || log "  WARN: warmup script timed out for $profile"
    else
        # Fallback: just open URL via curl-style CDP (no full browser session)
        log "  WARMUP_JS not found at $WARMUP_JS, skip browser-side warmup"
    fi

    # 3. Stop profile
    curl -sS -X GET "http://$DOLPHIN_API_HOST/v1.0/browser_profiles/$profile/stop" --max-time 30 > /dev/null
    log "  done profile=$profile"
done

log "=== Warmup end ==="
