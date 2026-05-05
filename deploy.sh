#!/bin/bash
# avoid_blocker installer.
#
# Copies the cheatsheet hook and the account-fallback wrapper to local
# directories and runs syntax + smoke checks. Idempotent.
#
# Configurable via env vars:
#   HOOKS_DIR    where to install the hook  (default: $HOME/.claude/hooks)
#   WRAPPER_DIR  where to install wrapper   (default: $HOME/bin)
#
# Does NOT modify any settings.json — wiring is left to the operator.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOKS_DIR="${HOOKS_DIR:-$HOME/.claude/hooks}"
WRAPPER_DIR="${WRAPPER_DIR:-$HOME/bin}"

mkdir -p "$HOOKS_DIR" "$WRAPPER_DIR"

echo "[*] Installing hook to $HOOKS_DIR/anti-block-inject.js"
cp "$REPO_DIR/hooks/anti-block-inject.js" "$HOOKS_DIR/anti-block-inject.js"
chmod +x "$HOOKS_DIR/anti-block-inject.js"
node -c "$HOOKS_DIR/anti-block-inject.js"
echo "    syntax OK"

echo "[*] Installing wrapper to $WRAPPER_DIR/claude-with-fallback.sh"
cp "$REPO_DIR/wrapper/claude-with-fallback.sh" "$WRAPPER_DIR/claude-with-fallback.sh"
chmod +x "$WRAPPER_DIR/claude-with-fallback.sh"
bash -n "$WRAPPER_DIR/claude-with-fallback.sh"
echo "    syntax OK"

echo
echo "[*] Smoke test hook (no env vars set → should exit silently)"
out=$(echo '{"cwd":"/tmp","hook_event_name":"SessionStart"}' \
        | node "$HOOKS_DIR/anti-block-inject.js" 2>&1)
if [ -z "$out" ]; then
    echo "    no output — guard correctly skipped (ANTI_BLOCK_HOOK_CHEATSHEET unset)"
else
    echo "    unexpected output: $out" >&2
    exit 1
fi

echo "[*] Smoke test hook (with env → should emit additionalContext)"
tmp=$(mktemp)
echo "# test cheatsheet" > "$tmp"
out=$(ANTI_BLOCK_HOOK_CHEATSHEET="$tmp" \
        echo '{"cwd":"/tmp","hook_event_name":"SessionStart"}' \
        | ANTI_BLOCK_HOOK_CHEATSHEET="$tmp" node "$HOOKS_DIR/anti-block-inject.js")
rm -f "$tmp"
if echo "$out" | grep -q '"hookEventName":"SessionStart"' \
        && echo "$out" | grep -q 'test cheatsheet'; then
    echo "    cheatsheet injected correctly"
else
    echo "    smoke test failed: $out" >&2
    exit 1
fi

echo
echo "Done. Next steps:"
echo "  1. Wire the hook into your settings.json (see README.md)"
echo "  2. Set ANTI_BLOCK_HOOK_CHEATSHEET to your cheatsheet path"
echo "  3. For wrapper: export CLAUDE_CONFIG_DIR_{1,2} + CLAUDE_ACCOUNT2_TOKEN"
