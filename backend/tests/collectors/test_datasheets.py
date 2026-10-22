"""Tests of the datasheet downloader (robots.txt, delay, PDF validation)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest
import respx

from collectors.datasheets import DatasheetDownloader
from shared.config import REPO_ROOT, Settings

FIXTURES = REPO_ROOT / "contracts" / "fixtures" / "pdfs"

HOST = "https://datasheets.example.invalid"
ROBOTS = f"{HOST}/robots.txt"

ROBOTS_ALLOWED = """
User-agent: *
Disallow: /private/
"""

ROBOTS_DENIED = """
User-agent: *
Disallow: /
"""


class RecordingSleep:
    """A sleep that only records the requested delay."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def _downloader(settings: Settings, sleep: RecordingSleep | None = None) -> DatasheetDownloader:
    return DatasheetDownloader(
        settings,
        sleep=sleep or RecordingSleep(),
        clock=lambda: 0.0,
    )


@pytest.mark.asyncio
async def test_an_allowed_path_is_downloaded(settings: Settings) -> None:
    pdf = (FIXTURES / "synthetic_mosfet.pdf").read_bytes()
    with respx.mock:
        robots = respx.get(ROBOTS).mock(return_value=httpx.Response(200, text=ROBOTS_ALLOWED))
        document = respx.get(f"{HOST}/IRF3205S.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf, headers={"Content-Type": "application/pdf"}
            )
        )
        downloader = _downloader(settings)
        source = await downloader.download_async(f"{HOST}/IRF3205S.pdf", "mosfet-irf3205s")

    assert robots.call_count == 1
    assert document.call_count == 1
    assert source is not None
    assert source.type.value == "pdf"
    assert source.file_hash == hashlib.sha256(pdf).hexdigest()
    assert source.source_id == f"pdf-{source.file_hash}"
    assert source.page_count == 2
    assert source.local_path is not None
    assert Path(source.local_path).is_file()
    assert downloader.local_path(source.source_id) == source.local_path
    assert downloader.page_count(source.source_id) == 2


@pytest.mark.asyncio
async def test_a_disallowed_path_is_refused_and_never_requested(settings: Settings) -> None:
    with respx.mock:
        respx.get(ROBOTS).mock(return_value=httpx.Response(200, text=ROBOTS_ALLOWED))
        document = respx.get(f"{HOST}/private/secret.pdf").mock(
            return_value=httpx.Response(200, content=b"%PDF-1.4 nope")
        )
        downloader = _downloader(settings)
        source = await downloader.download_async(f"{HOST}/private/secret.pdf")

    assert source is None
    assert document.call_count == 0


@pytest.mark.asyncio
async def test_a_host_that_forbids_everything_is_refused(settings: Settings) -> None:
    with respx.mock:
        respx.get(ROBOTS).mock(return_value=httpx.Response(200, text=ROBOTS_DENIED))
        document = respx.get(f"{HOST}/IRF3205S.pdf").mock(
            return_value=httpx.Response(200, content=b"%PDF-1.4")
        )
        downloader = _downloader(settings)
        source = await downloader.download_async(f"{HOST}/IRF3205S.pdf")

    assert source is None
    assert document.call_count == 0


@pytest.mark.asyncio
async def test_the_robots_answer_is_cached_for_the_host(settings: Settings) -> None:
    pdf = (FIXTURES / "synthetic_mosfet.pdf").read_bytes()
    with respx.mock:
        robots = respx.get(ROBOTS).mock(return_value=httpx.Response(200, text=ROBOTS_ALLOWED))
        respx.get(f"{HOST}/a.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf, headers={"Content-Type": "application/pdf"}
            )
        )
        respx.get(f"{HOST}/b.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf, headers={"Content-Type": "application/pdf"}
            )
        )
        downloader = _downloader(settings)
        await downloader.download_async(f"{HOST}/a.pdf")
        await downloader.download_async(f"{HOST}/b.pdf")

    assert robots.call_count == 1


@pytest.mark.asyncio
async def test_the_delay_between_two_requests_to_one_host_is_honoured(settings: Settings) -> None:
    pdf = (FIXTURES / "synthetic_mosfet.pdf").read_bytes()
    sleep = RecordingSleep()
    with respx.mock:
        respx.get(ROBOTS).mock(return_value=httpx.Response(200, text=ROBOTS_ALLOWED))
        respx.get(f"{HOST}/a.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf, headers={"Content-Type": "application/pdf"}
            )
        )
        respx.get(f"{HOST}/b.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf, headers={"Content-Type": "application/pdf"}
            )
        )
        downloader = _downloader(settings, sleep)
        await downloader.download_async(f"{HOST}/a.pdf")
        await downloader.download_async(f"{HOST}/b.pdf")

    assert sleep.delays
    assert all(delay >= settings.download_delay_seconds for delay in sleep.delays)


@pytest.mark.asyncio
async def test_a_body_that_is_not_a_pdf_is_rejected(settings: Settings) -> None:
    with respx.mock:
        respx.get(ROBOTS).mock(return_value=httpx.Response(200, text=ROBOTS_ALLOWED))
        respx.get(f"{HOST}/error.pdf").mock(
            return_value=httpx.Response(200, text="<html><body>404</body></html>")
        )
        downloader = _downloader(settings)
        source = await downloader.download_async(f"{HOST}/error.pdf")

    assert source is None
    assert list(Path(settings.pdf_dir).glob("*.pdf")) == []


@pytest.mark.asyncio
async def test_a_broken_pdf_is_rejected(settings: Settings) -> None:
    with respx.mock:
        respx.get(ROBOTS).mock(return_value=httpx.Response(200, text=ROBOTS_ALLOWED))
        respx.get(f"{HOST}/broken.pdf").mock(
            return_value=httpx.Response(200, content=b"%PDF-1.4 broken")
        )
        downloader = _downloader(settings)
        source = await downloader.download_async(f"{HOST}/broken.pdf")

    assert source is None


@pytest.mark.asyncio
async def test_a_scanned_pdf_is_reported_as_scanned(settings: Settings) -> None:
    pdf = (FIXTURES / "synthetic_scanned.pdf").read_bytes()
    with respx.mock:
        respx.get(ROBOTS).mock(return_value=httpx.Response(200, text=ROBOTS_ALLOWED))
        respx.get(f"{HOST}/scanned.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf, headers={"Content-Type": "application/pdf"}
            )
        )
        downloader = _downloader(settings)
        source = await downloader.download_async(f"{HOST}/scanned.pdf")

    assert source is not None
    assert downloader.is_scanned(source.source_id) is True


@pytest.mark.asyncio
async def test_a_pdf_with_a_text_layer_is_not_scanned(settings: Settings) -> None:
    pdf = (FIXTURES / "synthetic_mosfet.pdf").read_bytes()
    with respx.mock:
        respx.get(ROBOTS).mock(return_value=httpx.Response(200, text=ROBOTS_ALLOWED))
        respx.get(f"{HOST}/text.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf, headers={"Content-Type": "application/pdf"}
            )
        )
        downloader = _downloader(settings)
        source = await downloader.download_async(f"{HOST}/text.pdf")

    assert source is not None
    assert downloader.is_scanned(source.source_id) is False


@pytest.mark.asyncio
async def test_parts_that_share_one_datasheet_share_one_source_id(settings: Settings) -> None:
    pdf = (FIXTURES / "synthetic_mosfet.pdf").read_bytes()
    with respx.mock:
        respx.get(ROBOTS).mock(return_value=httpx.Response(200, text=ROBOTS_ALLOWED))
        respx.get(f"{HOST}/a.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf, headers={"Content-Type": "application/pdf"}
            )
        )
        respx.get(f"{HOST}/b.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf, headers={"Content-Type": "application/pdf"}
            )
        )
        downloader = _downloader(settings)
        first = await downloader.download_async(f"{HOST}/a.pdf", "mosfet-a")
        second = await downloader.download_async(f"{HOST}/b.pdf", "mosfet-b")

    assert first is not None
    assert second is not None
    assert first.source_id == second.source_id
    assert first.file_hash == second.file_hash
    groups = downloader.group_by_hash([first, second])
    assert len(groups) == 1
    assert len(groups[first.file_hash]) == 2


@pytest.mark.asyncio
async def test_a_failed_download_is_logged_and_returns_none(settings: Settings) -> None:
    with respx.mock:
        respx.get(ROBOTS).mock(return_value=httpx.Response(200, text=ROBOTS_ALLOWED))
        respx.get(f"{HOST}/missing.pdf").mock(return_value=httpx.Response(404))
        downloader = _downloader(settings)
        source = await downloader.download_async(f"{HOST}/missing.pdf")

    assert source is None


@pytest.mark.asyncio
async def test_a_missing_robots_txt_allows_the_download(settings: Settings) -> None:
    pdf = (FIXTURES / "synthetic_mosfet.pdf").read_bytes()
    with respx.mock:
        respx.get(ROBOTS).mock(return_value=httpx.Response(404))
        document = respx.get(f"{HOST}/a.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf, headers={"Content-Type": "application/pdf"}
            )
        )
        downloader = _downloader(settings)
        source = await downloader.download_async(f"{HOST}/a.pdf")

    assert document.call_count == 1
    assert source is not None


@pytest.mark.asyncio
async def test_the_user_agent_is_sent(settings: Settings) -> None:
    pdf = (FIXTURES / "synthetic_mosfet.pdf").read_bytes()
    with respx.mock:
        respx.get(ROBOTS).mock(return_value=httpx.Response(200, text=ROBOTS_ALLOWED))
        document = respx.get(f"{HOST}/a.pdf").mock(
            return_value=httpx.Response(
                200, content=pdf, headers={"Content-Type": "application/pdf"}
            )
        )
        downloader = _downloader(settings)
        await downloader.download_async(f"{HOST}/a.pdf")

    assert document.calls[0].request.headers["User-Agent"] == settings.user_agent
    assert "contact" in settings.user_agent
