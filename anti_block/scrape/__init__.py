"""Scrape modules — public API endpoints, JS bundle parsing, SSR state decoding.

Modules:
- aramuz_state: decode window._pinia base64+LZString state (Aramuz cloaking platform)
- bundle:       generic JS bundle parser (homepage → chunks → keywords/PSPs)
- xpay:         1xbet platform xpay public methods endpoint (1xbet/melbet/linebet/mostbet)
"""
