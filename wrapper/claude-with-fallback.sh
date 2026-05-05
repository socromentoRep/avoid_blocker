#!/bin/bash
# Claude CLI wrapper with two-account rate-limit fallback.
#
# Runs the `claude` CLI under one of two CLAUDE_CONFIG_DIR profiles. If the
# primary account hits a rate limit, sets a flag file and retries on the
# secondary account in the same invocation. Subsequent runs skip an account
# whose flag has not yet expired.
#
# Configuration via env vars:
#   CLAUDE_CONFIG_DIR_1     path to primary account config dir         (required)
#   CLAUDE_CONFIG_DIR_2     path to secondary account config dir       (required)
#   CLAUDE_ACCOUNT2_TOKEN   OAuth token for secondary account          (required)
#   CLAUDE_PRIMARY_ACCOUNT  which account is primary: "1" or "2"       (default: "2")
#   CLAUDE_RL_DURATION_SEC  fallback flag expiry in seconds            (default: 18000 = 5h)
#   CLAUDE_FALLBACK_LOG     path to fallback event log                 (default: /tmp/claude-fallback.log)
#   CLAUDE_NOTIFY_CMD       optional notification command, called as
#                           `$CLAUDE_NOTIFY_CMD "<message>"`            (optional)
#   NO_PROMPT_CACHE         if "1", append a cache-busting system prompt (default: 0)
#
# stdout from the underlying `claude` CLI is forwarded directly to this
# wrapper's stdout (no buffering) so a SIGKILL on the wrapper does not lose
# the in-progress streaming response.

set -o pipefail

CONFIG1="${CLAUDE_CONFIG_DIR_1:?CLAUDE_CONFIG_DIR_1 must be set}"
CONFIG2="${CLAUDE_CONFIG_DIR_2:?CLAUDE_CONFIG_DIR_2 must be set}"
ACCOUNT2_TOKEN="${CLAUDE_ACCOUNT2_TOKEN:?CLAUDE_ACCOUNT2_TOKEN must be set}"
PRIMARY="${CLAUDE_PRIMARY_ACCOUNT:-2}"
RL_DURATION="${CLAUDE_RL_DURATION_SEC:-18000}"
LOG="${CLAUDE_FALLBACK_LOG:-/tmp/claude-fallback.log}"
RL_FLAG1="/tmp/claude-acc1-ratelimited"
RL_FLAG2="/tmp/claude-acc2-ratelimited"

notify() {
    [ -n "${CLAUDE_NOTIFY_CMD:-}" ] && [ -x "$CLAUDE_NOTIFY_CMD" ] || return 0
    "$CLAUDE_NOTIFY_CMD" "$1" 2>/dev/null || true
}

is_flag_active() {
    local flag="$1"
    [ -f "$flag" ] || return 1
    local now ts
    now=$(date +%s)
    ts=$(cat "$flag" 2>/dev/null)
    if [[ "$ts" =~ ^[0-9]+$ ]] && [ "$now" -lt "$ts" ]; then
        return 0
    fi
    rm -f "$flag"
    return 1
}

pick_account() {
    local f1=0 f2=0
    is_flag_active "$RL_FLAG1" && f1=1
    is_flag_active "$RL_FLAG2" && f2=1

    if [ "$PRIMARY" = "1" ]; then
        if   [ $f1 -eq 0 ]; then echo "1"
        elif [ $f2 -eq 0 ]; then echo "2"
        else echo "BOTH_LIMITED"
        fi
    else
        if   [ $f2 -eq 0 ]; then echo "2"
        elif [ $f1 -eq 0 ]; then echo "1"
        else echo "BOTH_LIMITED"
        fi
    fi
}

run_claude() {
    local account="$1"; shift
    local stderr_file="$1"; shift

    local cache_bust_args=()
    if [ "${NO_PROMPT_CACHE:-0}" = "1" ]; then
        local bust_id
        bust_id=$(cat /proc/sys/kernel/random/uuid 2>/dev/null || date +%s%N)
        cache_bust_args=(--append-system-prompt "cachebust-${bust_id}")
    fi

    if [ "$account" = "1" ]; then
        CLAUDE_CONFIG_DIR="$CONFIG1" \
            claude --no-session-persistence "${cache_bust_args[@]}" "$@" 2>"$stderr_file"
    else
        CLAUDE_CONFIG_DIR="$CONFIG2" CLAUDE_CODE_OAUTH_TOKEN="$ACCOUNT2_TOKEN" \
            claude --no-session-persistence "${cache_bust_args[@]}" "$@" 2>"$stderr_file"
    fi
    return $?
}

detect_rate_limit() {
    grep -qiE "out of extra usage|usage limit|rate limit exceeded|rate_limit|hit your limit|hit.+limit.+reset|limit.+reset.+(am|pm).+UTC" <<< "$1"
}

detect_auth_error() {
    grep -qi "unauthorized\|invalid.*token\|authentication.*failed\|invalid_grant" <<< "$1"
}

mark_rate_limited() {
    local account="$1"
    local reset_epoch=$(( $(date +%s) + RL_DURATION ))
    if [ "$account" = "1" ]; then
        echo "$reset_epoch" > "$RL_FLAG1"
    else
        echo "$reset_epoch" > "$RL_FLAG2"
    fi
    echo "[$(date '+%Y-%m-%d %H:%M')] Account $account rate limited (reset epoch=$reset_epoch)" >> "$LOG"
    notify "⚠️ Claude acc${account} rate limited, fallback"
}

# === MAIN ===
ACCOUNT=$(pick_account)

if [ "$ACCOUNT" != "BOTH_LIMITED" ]; then
    echo "[claude-wrapper] using acc${ACCOUNT}" >&2
fi

if [ "$ACCOUNT" = "BOTH_LIMITED" ]; then
    echo "Both accounts rate limited." >&2
    notify "⛔ Both Claude accounts rate limited!"
    exit 75
fi

STDERR_FILE=$(mktemp -t claude-fb-stderr.XXXXXX)

run_claude "$ACCOUNT" "$STDERR_FILE" "$@"
EXIT=$?
STDERR_CONTENT=$(cat "$STDERR_FILE" 2>/dev/null || true)
rm -f "$STDERR_FILE"

if detect_auth_error "$STDERR_CONTENT"; then
    notify "❌ Claude auth error: acc${ACCOUNT}"
    echo "Auth error on account $ACCOUNT" >&2
    exit 1
fi

if detect_rate_limit "$STDERR_CONTENT"; then
    mark_rate_limited "$ACCOUNT"
    OTHER=$(pick_account)
    if [ "$OTHER" = "BOTH_LIMITED" ]; then
        echo "Both accounts rate limited after fallback." >&2
        exit 75
    fi
    echo "[$(date '+%Y-%m-%d %H:%M')] Fallback from acc$ACCOUNT to acc$OTHER" >> "$LOG"

    STDERR_FILE=$(mktemp -t claude-fb-stderr.XXXXXX)
    run_claude "$OTHER" "$STDERR_FILE" "$@"
    EXIT=$?
    STDERR_CONTENT=$(cat "$STDERR_FILE" 2>/dev/null || true)
    rm -f "$STDERR_FILE"

    if detect_auth_error "$STDERR_CONTENT"; then
        notify "❌ Claude auth error: acc${OTHER}"
        exit 1
    fi
    if detect_rate_limit "$STDERR_CONTENT"; then
        mark_rate_limited "$OTHER"
        echo "Both accounts rate limited." >&2
        exit 75
    fi
fi

exit $EXIT
