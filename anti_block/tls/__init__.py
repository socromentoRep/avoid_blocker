"""TLS-impersonation HTTP client (curl_cffi + Chrome 131 Android).

Public API:
    from anti_block.tls import TLSScoutClient, fetch
"""
from .client import TLSScoutClient, fetch, ANDROID_CHROME_131_HEADERS

__all__ = ['TLSScoutClient', 'fetch', 'ANDROID_CHROME_131_HEADERS']
