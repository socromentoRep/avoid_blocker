"""SOAX direct client — per-call sessionid rotation на tunnel error.

Public API:
    from anti_block.proxy.soax_direct import soax_url, get_with_retry
"""
from .soax_direct import soax_url, get_with_retry, SOAX_HOST, SOAX_PACKAGE

__all__ = ["soax_url", "get_with_retry", "SOAX_HOST", "SOAX_PACKAGE"]
