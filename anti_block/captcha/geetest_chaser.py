"""Geetest v4 solver — обёртка над chaser-gt (Rust binary).

chaser-gt — open-source MIT solver с auto-deobfuscation, rquest TLS-impersonation
Chrome 131. Использован для:
- 1win Paytm redirect (Geetest v4)
- 1win-flowlink MTN PSP redirect (Geetest v4 на mpayment_ci_mtn)

Workflow:
1. Browser scout доходит до captcha challenge
2. Извлекает captcha_id из страницы (обычно в JS init или data-attr)
3. Вызывает GeetestChaser.solve(captcha_id, risk_type, proxy_url)
4. Получает токен → inject обратно в форму через page.evaluate
5. Form submit проходит, redirect к PSP captured

Подробности risk_type:
- slide  : ползунок (самый частый)
- gobang : 5-в-ряд клик
- icon   : выбор иконок
- ai     : невидимая (Enterprise)
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Bin path — собран через cargo build --release --example geetest-solve
# Path to chaser-gt binary. Build via captcha/install_chaser_gt.sh.
# Override via env var: CHASER_GT_BIN=/path/to/geetest-solve
import os as _os
DEFAULT_BIN = Path(_os.environ.get("CHASER_GT_BIN", _os.path.expanduser("~/chaser-gt/target/release/examples/geetest-solve")))


@dataclass
class GeetestSolution:
    captcha_id: str
    lot_number: str
    pass_token: str
    gen_time: str
    captcha_output: str

    @classmethod
    def from_json(cls, raw: str) -> 'GeetestSolution':
        d = json.loads(raw)
        return cls(
            captcha_id=d['captcha_id'],
            lot_number=d['lot_number'],
            pass_token=d['pass_token'],
            gen_time=d['gen_time'],
            captcha_output=d['captcha_output'],
        )

    def as_form_payload(self) -> dict[str, str]:
        """Стандартный shape для inject в Geetest v4 callback."""
        return {
            'captcha_id': self.captcha_id,
            'lot_number': self.lot_number,
            'pass_token': self.pass_token,
            'gen_time': self.gen_time,
            'captcha_output': self.captcha_output,
        }


class GeetestSolveError(Exception):
    pass


class GeetestChaser:
    """Solver wrapper. Использует chaser-gt Rust binary через subprocess."""

    def __init__(self, bin_path: Path = DEFAULT_BIN, timeout: int = 60):
        if not bin_path.exists():
            raise FileNotFoundError(
                f'chaser-gt binary not found: {bin_path}. '
                f'Build it: cd /home/deploy/chaser-gt && '
                f'cargo build --release --example geetest-solve'
            )
        self.bin = bin_path
        self.timeout = timeout

    def solve(
        self,
        captcha_id: str,
        risk_type: str = 'slide',
        proxy_url: str | None = None,
    ) -> GeetestSolution:
        """Решает Geetest v4 captcha, возвращает токены для inject в форму.

        :param captcha_id: ID который сайт передаёт в Geetest init JS (обычно
            в `data-captcha-id` или window.initGeetest({captcha_id: ...})).
        :param risk_type: slide | gobang | icon | ai
        :param proxy_url: optional SOAX/SOCKS5 — для match с IP браузера, чтобы
            Geetest server-side check не вернул FAIL по IP mismatch.
        :return: GeetestSolution с токенами для inject в callback.
        """
        cmd: list[str] = [str(self.bin), captcha_id, risk_type]
        if proxy_url:
            cmd.extend(['--proxy', proxy_url])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise GeetestSolveError(f'chaser-gt timeout after {self.timeout}s')

        if result.returncode != 0:
            raise GeetestSolveError(
                f'chaser-gt exit {result.returncode}: {result.stderr.strip()[:300]}'
            )

        stdout = result.stdout.strip()
        if not stdout:
            raise GeetestSolveError('chaser-gt returned empty stdout')

        try:
            return GeetestSolution.from_json(stdout)
        except (json.JSONDecodeError, KeyError) as e:
            raise GeetestSolveError(
                f'invalid JSON from chaser-gt: {e}. stdout={stdout[:300]}'
            )


def cli_main():
    """CLI entry point: python3 -m anti_block.captcha.geetest_chaser <id> <type>."""
    import argparse
    parser = argparse.ArgumentParser(prog='anti_block.captcha.geetest_chaser')
    parser.add_argument('captcha_id', help='Geetest captcha_id from page')
    parser.add_argument(
        'risk_type', choices=['slide', 'gobang', 'icon', 'ai'],
        help='Captcha type (default: slide)',
    )
    parser.add_argument(
        '--proxy', help='Proxy URL (http://... or socks5://...)',
    )
    parser.add_argument(
        '--bin', default=str(DEFAULT_BIN), help='Path to chaser-gt binary',
    )
    args = parser.parse_args()

    chaser = GeetestChaser(bin_path=Path(args.bin))
    sol = chaser.solve(args.captcha_id, args.risk_type, proxy_url=args.proxy)
    print(json.dumps(sol.as_form_payload(), indent=2))


if __name__ == '__main__':
    cli_main()
