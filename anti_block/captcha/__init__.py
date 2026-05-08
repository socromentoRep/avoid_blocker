"""Captcha solvers — wrappers around free OSS solvers.

Modules:
- geetest_chaser: wraps chaser-gt (Rust binary, MIT license)
                  https://github.com/0xchasercat/chaser-gt
                  Solves Geetest v3/v4 (slide / icon / gobang / ai/AI)
                  Install: bash captcha/install_chaser_gt.sh
- hcaptcha:       wraps korolossamy/hcaptcha-ai-solver (Python, no API keys)
                  https://github.com/korolossamy/hcaptcha-ai-solver
                  Install: bash captcha/install_hcaptcha_solver.sh

Trade-offs vs paid services (CapSolver, 2Captcha):
+ \047free / no API keys\047
+ runs locally
- 85-95% success rate (vs 99%+ paid)
- updates may lag behind captcha-engine changes (need to git pull / fork)

For production-grade traffic we recommend paid solvers; for research/recon — OSS.
"""
