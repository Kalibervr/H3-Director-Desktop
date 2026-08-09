"""Tests for local-service URL validation."""

from __future__ import annotations

import pytest

from server_utils.loopback_url import LoopbackURLValidationError, require_loopback_http_url


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://localhost:8188/", "http://localhost:8188"),
        ("https://LOCALHOST./api/", "https://localhost/api"),
        ("http://127.0.0.1:11434", "http://127.0.0.1:11434"),
        ("http://127.42.1.9:8188", "http://127.42.1.9:8188"),
        ("http://[::1]:8188/", "http://[::1]:8188"),
    ],
)
def test_accepts_only_literal_loopback_hosts(value: str, expected: str) -> None:
    assert require_loopback_http_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "localhost:8188",
        "ftp://localhost:8188",
        "http://0.0.0.0:8188",
        "http://192.168.1.10:8188",
        "http://example.com:8188",
        "http://localhost.evil.example:8188",
        "http://user:password@localhost:8188",
        "http://localhost:8188?target=remote",
        "http://localhost:8188/#fragment",
        "http://localhost:99999",
    ],
)
def test_rejects_non_loopback_or_ambiguous_urls(value: str) -> None:
    with pytest.raises(LoopbackURLValidationError):
        require_loopback_http_url(value)
