"""TLS helpers for corporate SSL inspection (Windows certificate stores)."""

from __future__ import annotations

from crawler.logutil import logger

_injected = False


def inject_system_certificates() -> None:
    """Prefer the OS/corporate trust store over certifi-only verification."""
    global _injected
    if _injected:
        return
    try:
        import truststore

        truststore.inject_into_ssl()
        _injected = True
    except Exception:  # noqa: BLE001 - optional; robots/httpx have a fallback
        logger.debug("System certificate store was not injected; using default TLS.")
