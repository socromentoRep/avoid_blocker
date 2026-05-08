#!/bin/bash
# install_chaser_gt.sh — clone and build chaser-gt (Rust Geetest v3/v4 solver, MIT license).
#
# After install, set env var:
#   export CHASER_GT_BIN=$HOME/chaser-gt/target/release/examples/geetest-solve
#
# Or use the default location ($HOME/chaser-gt/...) which the wrapper picks up.
#
# Usage:
#   bash captcha/install_chaser_gt.sh                    # default: $HOME/chaser-gt
#   INSTALL_DIR=/opt/chaser-gt bash captcha/install_chaser_gt.sh
#
# Requirements:
#   - git, curl
#   - Rust toolchain (will be installed via rustup if missing)

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/chaser-gt}"
REPO_URL="https://github.com/0xchasercat/chaser-gt.git"

echo "[chaser-gt] Install dir: $INSTALL_DIR"

# Check / install Rust
if ! command -v cargo >/dev/null 2>&1; then
    echo "[chaser-gt] cargo not found — installing rustup..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
    # shellcheck source=/dev/null
    source "$HOME/.cargo/env"
fi

# Clone or pull
if [ ! -d "$INSTALL_DIR" ]; then
    echo "[chaser-gt] Cloning $REPO_URL ..."
    git clone "$REPO_URL" "$INSTALL_DIR"
else
    echo "[chaser-gt] Pulling latest..."
    cd "$INSTALL_DIR" && git pull
fi

# Build release binary
cd "$INSTALL_DIR"
echo "[chaser-gt] Building release binary (cargo build --release --example geetest-solve)..."
cargo build --release --example geetest-solve

BIN_PATH="$INSTALL_DIR/target/release/examples/geetest-solve"
if [ ! -x "$BIN_PATH" ]; then
    echo "[chaser-gt] FAIL: binary not found at $BIN_PATH" >&2
    exit 1
fi

echo
echo "[chaser-gt] Build OK. Binary: $BIN_PATH"
echo
echo "Set env var (add to ~/.bashrc or systemd Environment=):"
echo "    export CHASER_GT_BIN=\"$BIN_PATH\""
echo
echo "Test:"
echo "    python3 -m anti_block.captcha.geetest_chaser <captcha_id> ai"
