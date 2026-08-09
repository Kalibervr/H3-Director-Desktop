"""Validation for local HTTP service base URLs."""

from __future__ import annotations

from ipaddress import ip_address
from urllib.parse import urlsplit


class LoopbackURLValidationError(ValueError):
    """Raised when a configured local-service URL could leave the host."""


def require_loopback_http_url(value: str) -> str:
    """Return a normalized HTTP(S) base URL after proving its host is loopback."""
    candidate = value.strip()
    if not candidate:
        raise LoopbackURLValidationError("URL is required")

    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise LoopbackURLValidationError("URL is malformed") from exc

    if parsed.scheme not in {"http", "https"}:
        raise LoopbackURLValidationError("URL scheme must be http or https")
    if parsed.username is not None or parsed.password is not None:
        raise LoopbackURLValidationError("URL credentials are not allowed")
    if not parsed.hostname:
        raise LoopbackURLValidationError("URL host is required")
    if parsed.query or parsed.fragment:
        raise LoopbackURLValidationError("URL query and fragment are not allowed")

    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost":
        is_loopback = True
    else:
        try:
            is_loopback = ip_address(host).is_loopback
        except ValueError:
            is_loopback = False

    if not is_loopback:
        raise LoopbackURLValidationError("URL host must be loopback")

    path = parsed.path.rstrip("/")
    authority = f"[{host}]" if ":" in host else host
    if port is not None:
        authority = f"{authority}:{port}"
    return f"{parsed.scheme}://{authority}{path}"
