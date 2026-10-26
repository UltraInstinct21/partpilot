"""Tests for WebDiscoveryService safety, domain filtering, and MPN validation."""

from __future__ import annotations

from unittest.mock import MagicMock

from services.web_search import (
    WebDiscoveryService,
    is_blocked,
    is_trusted_domain,
    validate_mpn,
)
from shared.schemas import Family


def test_is_blocked_identifies_adult_and_spam_terms() -> None:
    assert is_blocked("xhamster") is True
    assert is_blocked("https://xhamster19.com/search/xxxxxxxxxxx+bhabi") is True
    assert is_blocked("Watch xxx movies and bhabi videos") is True
    assert is_blocked("literotica stories") is True
    assert is_blocked("casino betting poker") is True

    # Legitimate electronic queries must NOT be blocked
    assert is_blocked("IRF3205") is False
    assert is_blocked("LM358 dual op-amp") is False
    assert is_blocked("STM32F401CCU6 microcontroller") is False
    assert is_blocked("ESP32-S3 Wi-Fi module") is False


def test_is_trusted_domain() -> None:
    assert is_trusted_domain("https://www.ti.com/lit/ds/symlink/lm358.pdf") is True
    assert is_trusted_domain("https://www.infineon.com/part/irf3205") is True
    assert is_trusted_domain("https://robu.in/product/esp32") is True
    assert is_trusted_domain("https://www.mouser.in/c/?q=LM358") is True
    assert is_trusted_domain("https://www.digikey.com/product/123") is True

    # Untrusted / adult / random domains
    assert is_trusted_domain("https://xhamster19.com/video") is False
    assert is_trusted_domain("https://www.literotica.com/s/story") is False
    assert is_trusted_domain("https://spammy-site.xyz/fake") is False


def test_validate_mpn_accepts_authentic_electronic_parts() -> None:
    valid_mpns = [
        "IRF3205",
        "IRF3205PBF",
        "LM358",
        "LM358DR",
        "ESP32",
        "ESP32-S3",
        "ESP32-S3-WROOM-1",
        "STM32F401CCU6",
        "STM32F103C8T6",
        "BSC030N08NS5",
        "Si7148DP",
        "NVMFS5C430NL",
        "2N2222",
        "1N4148",
        "NE555",
        "MAX232",
        "ATMEGA328P",
    ]
    for mpn in valid_mpns:
        assert validate_mpn(mpn) is True, f"Expected {mpn} to be valid MPN"


def test_validate_mpn_rejects_adult_spam_and_generic_phrases() -> None:
    invalid_tokens = [
        "XHAMSTER19",
        "HOLI-PARTY-AT-GOKULDHAM-FEAT-TMKOC",
        "FIELD-EFFECT",
        "POWER-ELECTRONICS",
        "HIGH-PERFORMANCE",
        "REAL-TIME",
        "RS-ONLINE",
        "TYPE-C",
        "LOW-POWER",
        "N-CHANNEL",
        "FULL-BRIDGE",
        "HALF-BRIDGE",
        "INDUSTRY-STANDARD",
        "WI-FI",
        "WIN10",
        "MP4",
        "USB3",
        "TOP10",
        "PAGE1",
        "DATASHEET",
        "APPLICATION-NOTE",
    ]
    for token in invalid_tokens:
        assert validate_mpn(token) is False, f"Expected {token} to be rejected as MPN"


def test_discover_rejects_blocked_queries_without_network_call() -> None:
    service = WebDiscoveryService("http://127.0.0.1:8080")
    # Should immediately return empty list without touching SearXNG
    results = service.discover("xxxxxxxxxxx bhabi porn videos")
    assert results == []

    results2 = service.discover("xhamster19")
    assert results2 == []


def test_discover_and_ingest_does_not_persist_unverified_stubs() -> None:
    repo = MagicMock()
    service = WebDiscoveryService("http://127.0.0.1:8080", repository=repo)

    # Mock discover to return a page that is a generic stub with no offers or pdf
    stub_page = {
        "title": "Some random text with ABC1234",
        "snippet": "Just a general discussion",
        "url": "https://random-forum.org/threads/123",
        "offers": [],
    }
    service.discover = MagicMock(return_value=[stub_page])  # type: ignore[assignment]

    records, pages = service.discover_and_ingest_with_results("ABC1234")
    # The page is exposed for context
    assert len(pages) == 1
    # But repo.add_part must NOT be called for unverified generic stub
    assert repo.add_part.call_count == 0
    assert len(records) == 0


def test_discover_and_ingest_persists_verified_component() -> None:
    repo = MagicMock()
    repo.add_part.side_effect = lambda part: part
    service = WebDiscoveryService("http://127.0.0.1:8080", repository=repo)

    verified_page = {
        "title": "IRF3205 HEXFET Power MOSFET Infineon",
        "snippet": "Advanced HEXFET Power MOSFETs from International Rectifier / Infineon. 55V 110A TO-220AB package.",
        "url": "https://www.infineon.com/dgdl/irf3205.pdf",
        "offers": [
            {"distributor": "Robu.in", "price": 45.0, "currency": "INR", "stock": 500}
        ],
    }
    service.discover = MagicMock(return_value=[verified_page])  # type: ignore[assignment]

    records, pages = service.discover_and_ingest_with_results("IRF3205")
    assert len(pages) == 1
    assert len(records) == 1
    assert records[0].mpn == "IRF3205"
    assert records[0].family == Family.MOSFET
    assert records[0].manufacturer == "Infineon"
    assert repo.add_part.call_count == 1
