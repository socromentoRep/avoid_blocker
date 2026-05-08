"""TLS-impersonation HTTP client поверх curl_cffi.

Use case: WAF (Qrator, TLS termination на казино/букмекерах) режут трафик на
handshake уровне. Стандартный Playwright/patchright показывает Chromium TLS
который попадает в blocklist. curl_cffi с патчем BoringSSL даёт точный
fingerprint реального Android Chrome 131 — обходит TLS-уровневые WAF.

Limitations:
- НЕ выполняет JS — для challenge-based блоков (Turnstile, hCaptcha) нужен
  полноценный браузер. Используй CloakBrowser (anti_block.browser.cloak)
  или Playwright + stealth.
- НЕ заменяет browser scout — это HTTP-only fallback для конкретных API endpoints.

Configuration via environment (recommended via .env file or systemd Environment=):
    SOAX_RES_HOST       (default: proxy.soax.com)
    SOAX_RES_PORT       (default: 5000)
    SOAX_RES_PACKAGE    (your SOAX package id from soax.com dashboard)
    SOAX_RES_PASSWORD   (your SOAX password)

Usage:
    from anti_block.tls import TLSScoutClient
    client = TLSScoutClient(soax_geo='IN', profile='chrome131_android')
    resp = client.get('https://example.com/api/payment-methods')
    print(resp.status_code, resp.text[:200])

If SOAX_RES_PACKAGE/SOAX_RES_PASSWORD are unset, the client makes direct
(no-proxy) requests — useful for fingerprint verification on tls.peet.ws.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from curl_cffi import requests as cffi_requests
from curl_cffi.requests import BrowserType


SOAX_PROXY_HOST = os.environ.get("SOAX_RES_HOST", "proxy.soax.com")
SOAX_PROXY_PORT = int(os.environ.get("SOAX_RES_PORT", "5000"))
SOAX_PACKAGE = os.environ.get("SOAX_RES_PACKAGE", "")
SOAX_PASSWORD = os.environ.get("SOAX_RES_PASSWORD", "")


# Заголовки точно соответствуют Chrome 131 на Android (Samsung A16, Jio carrier).
# JA4H проверяет порядок headers — здесь он соответствует реальному Chrome.
ANDROID_CHROME_131_HEADERS = {
    'sec-ch-ua': '"Chromium";v="131", "Not_A Brand";v="24"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
    'upgrade-insecure-requests': '1',
    'user-agent': (
        'Mozilla/5.0 (Linux; Android 14; SM-A165F) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/131.0.0.0 Mobile Safari/537.36'
    ),
    'accept': (
        'text/html,application/xhtml+xml,application/xml;q=0.9,'
        'image/avif,image/webp,image/apng,*/*;q=0.8,'
        'application/signed-exchange;v=b3;q=0.7'
    ),
    'sec-fetch-site': 'none',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-user': '?1',
    'sec-fetch-dest': 'document',
    'accept-encoding': 'gzip, deflate, br, zstd',
    'accept-language': 'en-IN,en;q=0.9,hi-IN;q=0.8,hi;q=0.7',
    'priority': 'u=0, i',
}


@dataclass
class TLSScoutClient:
    """HTTP-only TLS-impersonated клиент для обхода WAF на уровне TLS handshake."""

    soax_geo: str = 'IN'
    profile: str = 'chrome131_android'
    sticky_session_id: str | None = None
    timeout: int = 30

    def __post_init__(self):
        if self.profile not in [t for t in BrowserType.__members__]:
            raise ValueError(
                f"Profile '{self.profile}' not supported by curl_cffi. "
                f"Available: {sorted(BrowserType.__members__.keys())}"
            )

    def _build_proxy_url(self):
        """Direct SOAX SOCKS5 с коротким sessionid.

        SOAX отвергает sessionid с дефисами и >20 chars (server error 1).
        Используем 8 hex chars из uuid4.
        """
        if not SOAX_PACKAGE or not SOAX_PASSWORD:
            return None
        import uuid as _uuid
        sid = self.sticky_session_id or 'ab' + _uuid.uuid4().hex[:6]
        username = (
            f'package-{SOAX_PACKAGE}'
            f'-country-{self.soax_geo.lower()}'
            f'-sessionid-{sid}'
            f'-sessionlength-300'
        )
        return f'socks5h://{username}:{SOAX_PASSWORD}@{SOAX_PROXY_HOST}:{SOAX_PROXY_PORT}'

    def _proxies(self) -> dict[str, str] | None:
        url = self._build_proxy_url()
        if not url:
            return None
        return {'http': url, 'https': url}

    def fingerprint_check(self) -> dict[str, Any]:
        """Проверяет какой fingerprint видит сервер (через tls.peet.ws).

        Используется для верификации что impersonation реально работает —
        перед production scan'ом проверяем что JA3/JA4 совпадают с
        реальным Android Chrome.
        """
        r = cffi_requests.get(
            'https://tls.peet.ws/api/clean',
            impersonate=self.profile,
            proxies=self._proxies(),
            headers=ANDROID_CHROME_131_HEADERS,
            timeout=self.timeout,
        )
        return r.json()

    def get(self, url: str, **kwargs) -> Any:
        """GET с TLS-impersonation. Возвращает curl_cffi Response."""
        headers = {**ANDROID_CHROME_131_HEADERS, **kwargs.pop('headers', {})}
        return cffi_requests.get(
            url,
            impersonate=self.profile,
            proxies=self._proxies(),
            headers=headers,
            timeout=kwargs.pop('timeout', self.timeout),
            **kwargs,
        )

    def post(self, url: str, **kwargs) -> Any:
        headers = {**ANDROID_CHROME_131_HEADERS, **kwargs.pop('headers', {})}
        return cffi_requests.post(
            url,
            impersonate=self.profile,
            proxies=self._proxies(),
            headers=headers,
            timeout=kwargs.pop('timeout', self.timeout),
            **kwargs,
        )


def fetch(url: str, soax_geo: str = 'IN', **kwargs) -> Any:
    """One-shot fetch helper для bash скриптов и quick tests."""
    return TLSScoutClient(soax_geo=soax_geo).get(url, **kwargs)
