#!/bin/bash
# install_hcaptcha_solver.sh — clone korolossamy/hcaptcha-ai-solver
# (free Python hCaptcha solver, no API keys required, uses tls_client + ML).
#
# After install, set env var:
#   export HCAPTCHA_SOLVER_PATH=$HOME/hcaptcha-ai-solver
#
# Usage:
#   bash captcha/install_hcaptcha_solver.sh                       # default $HOME/hcaptcha-ai-solver
#   INSTALL_DIR=/opt/hcaptcha-solver bash captcha/install_hcaptcha_solver.sh
#
# Requirements:
#   - git
#   - Python 3.10+
#   - pip (will install: tls_client, scipy, numpy)

set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/hcaptcha-ai-solver}"
REPO_URL="https://github.com/korolossamy/hcaptcha-ai-solver.git"
PYTHON="${PYTHON:-python3}"

echo "[hcaptcha-solver] Install dir: $INSTALL_DIR"

# Clone or pull
if [ ! -d "$INSTALL_DIR" ]; then
    echo "[hcaptcha-solver] Cloning $REPO_URL ..."
    git clone "$REPO_URL" "$INSTALL_DIR"
else
    echo "[hcaptcha-solver] Pulling latest..."
    cd "$INSTALL_DIR" && git pull
fi

# Install Python deps
echo "[hcaptcha-solver] Installing Python deps (tls_client, scipy, numpy)..."
"$PYTHON" -m pip install --user tls_client scipy numpy

# Sanity check imports
"$PYTHON" -c "import tls_client; from scipy import interpolate; import numpy; print('deps OK')"

cd "$INSTALL_DIR"
"$PYTHON" -c "
import sys
sys.path.insert(0, '$INSTALL_DIR')
from modules.solver import Solver
print('Solver imports OK')
"

echo
echo "[hcaptcha-solver] Install OK."
echo
echo "Set env var (add to ~/.bashrc or systemd Environment=):"
echo "    export HCAPTCHA_SOLVER_PATH=\"$INSTALL_DIR\""
echo
echo "Test:"
echo "    python3 -m anti_block.captcha.hcaptcha <sitekey> <host> --proxy socks5h://..."
echo
echo "NOTE: For sites requiring HSW token (Discord-style), additionally start"
echo "      $INSTALL_DIR/hsw_api.py as a Flask service. Most casino registration"
echo "      forms work without it."
