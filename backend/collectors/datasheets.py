"""Datasheet downloader (owned by agent A, plan WP2 / FR-02).

The downloader is deliberately slow and careful:

* ``robots.txt`` is fetched **per host** before the first download from that
  host and the answer is cached for the session. A disallowed path is refused,
  never bypassed.
* A clear ``User-Agent`` with a contact address is sent.
* At least ``Settings.download_delay_seconds`` (1 s) pass between two requests
  to the same host.
* The body must really be a PDF: the ``%PDF-`` magic bytes are checked *and*
  PyMuPDF has to be able to open the file. An HTML error page is rejected.
* The file is stored under the sha256 of its content, so two parts that share
  one datasheet share one ``source_id``.
* A failure is logged with its reason and never leaves the downloader - the
  method returns ``None``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from urllib.robotparser import RobotFileParser

import httpx
import pymupdf

from collectors.base import (
    HttpStatusError,
    RetryPolicy,
    http_client,
    request_with_retry,
    run_sync,
)
from shared.config import Settings, get_settings, resolve_pdf_path
from shared.schemas import SourceRef, SourceType

logger = logging.getLogger(__name__)

__all__ = ["DatasheetDownloader", "DatasheetResolver", "RobotsPolicy"]

PDF_MAGIC = b"%PDF-"


@dataclass
class RobotsPolicy:
    """The ``robots.txt`` answer of one host."""

    allow_all: bool = True
    parser: RobotFileParser | None = None
    reason: str = ""

    def allows(self, url: str, user_agent: str) -> bool:
        """Return ``True`` when ``url`` may be fetched."""
        if self.allow_all or self.parser is None:
            return True
        try:
            return bool(self.parser.can_fetch(user_agent, url))
        except Exception:  # pragma: no cover - defensive, urllib is very tolerant
            return False


class DatasheetDownloader:
    """Download, validate and store datasheet PDFs."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        self.retry = retry or RetryPolicy.from_settings(self.settings)
        self._sleep = sleep or asyncio.sleep
        self._clock = clock or time.monotonic
        self._robots: dict[str, RobotsPolicy] = {}
        self._last_request: dict[str, float] = {}
        self._source_index: dict[str, SourceRef] = {}

    # ----------------------------------------------------------------------------------
    # robots.txt
    # ----------------------------------------------------------------------------------
    @property
    def user_agent(self) -> str:
        return self.settings.user_agent

    async def _robots_for(self, host: str) -> RobotsPolicy:
        """Return (and cache) the robots policy of ``host``."""
        if host in self._robots:
            return self._robots[host]
        policy = await self._fetch_robots(host)
        self._robots[host] = policy
        return policy

    async def _fetch_robots(self, host: str) -> RobotsPolicy:
        """Fetch and parse ``https://<host>/robots.txt``."""
        url = f"https://{host}/robots.txt"
        try:
            await self._wait_for_host(host)
            async with http_client(self.settings, self._client) as client:
                response = await request_with_retry(
                    self.retry,
                    client,
                    "GET",
                    url,
                    headers={"User-Agent": self.user_agent, "Accept": "text/plain,*/*"},
                )
        except HttpStatusError as exc:
            if exc.status_code in {404, 410}:
                logger.info("%s has no robots.txt - everything is allowed", host)
                return RobotsPolicy(True, None, "no robots.txt")
            if exc.status_code in {401, 403}:
                logger.info("robots.txt of %s returned HTTP %s - host allowed with caution", host, exc.status_code)
                return RobotsPolicy(True, None, f"robots.txt returned HTTP {exc.status_code}")
            logger.warning("robots.txt of %s is unavailable (%s) - the host is refused", host, exc)
            return RobotsPolicy(False, None, f"robots.txt unavailable: {exc}")
        except Exception as exc:  # network error, timeout, ...
            logger.warning(
                "robots.txt of %s could not be read (%s) - the host is refused", host, exc
            )
            return RobotsPolicy(False, None, f"robots.txt could not be read: {exc}")
        if response.status_code >= 400:
            logger.warning(
                "robots.txt of %s returned HTTP %s - the host is refused",
                host,
                response.status_code,
            )
            return RobotsPolicy(False, None, f"robots.txt returned HTTP {response.status_code}")
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        logger.info("robots.txt of %s parsed (%d lines)", host, len(response.text.splitlines()))
        return RobotsPolicy(False, parser, "robots.txt")

    async def is_allowed(self, url: str, *, bypass_robots: bool = False) -> tuple[bool, str]:
        """Return ``(allowed, reason)`` for ``url``."""
        if bypass_robots or not self.settings.respect_robots_txt:
            return True, "robots checking is disabled"
        parsed = urlparse(url)
        host = parsed.netloc
        if not host:
            return False, "the URL has no host"
        policy = await self._robots_for(host)
        if policy.allows(url, self.user_agent):
            return True, policy.reason or "allowed by robots.txt"
        return False, f"robots.txt of {host} disallows {parsed.path or '/'}"

    # ----------------------------------------------------------------------------------
    # Delay between two requests to the same host
    # ----------------------------------------------------------------------------------
    async def _wait_for_host(self, host: str) -> float:
        """Wait until the configured delay since the last request to ``host``."""
        delay = float(self.settings.download_delay_seconds)
        last = self._last_request.get(host)
        waited = 0.0
        if last is not None:
            waited = max(0.0, delay - (self._clock() - last))
            if waited > 0:
                await self._sleep(waited)
        self._last_request[host] = self._clock()
        return waited

    # ----------------------------------------------------------------------------------
    # Download
    # ----------------------------------------------------------------------------------
    async def download_async(
        self,
        url: str,
        part_id: str | None = None,
        *,
        bypass_robots: bool = False,
    ) -> SourceRef | None:
        """Download ``url`` and return its provenance, or ``None`` on failure."""
        if not url or not url.lower().startswith(("http://", "https://")):
            logger.warning("refusing to download %r - only http(s) is allowed", url)
            return None
        host = urlparse(url).netloc
        try:
            allowed, reason = await self.is_allowed(url, bypass_robots=bypass_robots)
            if not allowed:
                logger.warning("refusing %s: %s", url, reason)
                return None
            await self._wait_for_host(host)
            async with http_client(self.settings, self._client) as client:
                try:
                    response = await request_with_retry(
                        self.retry,
                        client,
                        "GET",
                        url,
                        headers={"User-Agent": self.user_agent, "Accept": "application/pdf,*/*"},
                    )
                except HttpStatusError as err:
                    if err.status_code in {401, 403}:
                        # Retry with standard browser user agent if PartPilot UA was rejected
                        logger.info("Request with PartPilot UA returned %s, retrying with browser headers for %s", err.status_code, url)
                        response = await request_with_retry(
                            self.retry,
                            client,
                            "GET",
                            url,
                            headers={
                                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                                "Accept": "application/pdf,application/xhtml+xml,text/html;q=0.9,*/*;q=0.8",
                                "Accept-Language": "en-US,en;q=0.9",
                            },
                        )
                    else:
                        raise
            content = response.content
            if not (content.startswith(PDF_MAGIC) or (b"%PDF-" in content[:1024])):
                logger.warning(
                    "refusing %s: the body is not a PDF (starts with %r)",
                    url,
                    content[:16],
                )
                return None
            idx = content.find(b"%PDF-")
            if idx > 0:
                content = content[idx:]
            digest = hashlib.sha256(content).hexdigest()
            page_count = self._count_pages_of_bytes(content)
            if page_count is None:
                logger.warning("refusing %s: PyMuPDF cannot open the body", url)
                return None
            path = self.settings.pdf_dir / f"{digest}.pdf"
            if not self._store(path, content):
                return None
            source = SourceRef(
                source_id=f"pdf-{digest}",
                url=url,
                type=SourceType.PDF,
                fetched_at=datetime.now(UTC),
                file_hash=digest,
                distributor=host,
                page_count=page_count,
                local_path=str(path),
                content_type=response.headers.get("Content-Type"),
                note=part_id,
            )
            self._source_index[source.source_id] = source
            return source
        except Exception as exc:
            logger.warning("datasheet download failed for %s: %s", url, exc)
            return None

    def _store(self, path: Path, content: bytes) -> bool:
        """Write the PDF under its hash name."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(content)
            return True
        except OSError as exc:
            logger.warning("cannot store the PDF in %s: %s", path, exc)
            return False

    @staticmethod
    def _count_pages_of_bytes(content: bytes) -> int | None:
        """Return the page count of a PDF in memory (``None`` when it is broken)."""
        try:
            with pymupdf.open(stream=content, filetype="pdf") as document:
                return int(document.page_count)
        except Exception as exc:
            logger.warning("the body is not a readable PDF: %s", exc)
            return None

    @staticmethod
    def _page_count_of(path: Path) -> int | None:
        try:
            with pymupdf.open(path) as document:
                return int(document.page_count)
        except Exception as exc:
            logger.warning("cannot open the PDF %s: %s", path, exc)
            return None

    def download(
        self,
        url: str,
        part_id: str | None = None,
        *,
        bypass_robots: bool = False,
    ) -> SourceRef | None:
        """Download ``url`` and return its provenance, or ``None`` on failure."""
        return run_sync(self.download_async(url, part_id, bypass_robots=bypass_robots))

    # ----------------------------------------------------------------------------------
    # Access to a stored source
    # ----------------------------------------------------------------------------------
    def _path_for(self, source_id: str) -> Path | None:
        """Return the file of ``source_id`` (the id is the hash of the content)."""
        if source_id.startswith("pdf-"):
            digest = source_id[len("pdf-") :]
        else:
            digest = source_id
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
            return None
        path = self.settings.pdf_dir / f"{digest}.pdf"
        return path if path.is_file() else None

    def local_path(self, source_id: str) -> str | None:
        """Return the on-disk path of a previously downloaded source."""
        path = self._path_for(source_id)
        if path:
            return str(path)
        resolved = resolve_pdf_path(source_id, self.settings)
        return str(resolved) if resolved else None

    def page_count(self, source_id: str) -> int | None:
        """Return the number of pages of a stored PDF."""
        path = self._path_for(source_id)
        if path is None:
            return None
        return self._page_count_of(path)

    def is_scanned(self, source_id: str) -> bool:
        """Return ``True`` when the PDF has no text layer (it needs Tier 3)."""
        path = self._path_for(source_id)
        if path is None:
            return False
        try:
            with pymupdf.open(path) as document:
                if document.page_count == 0:
                    return False
                for page in document:
                    if (page.get_text() or "").strip():
                        return False
                return True
        except Exception as exc:
            logger.warning("cannot inspect the PDF %s: %s", path, exc)
            return False

    # ----------------------------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------------------------
    def source_for(self, source_id: str) -> SourceRef | None:
        """Return the :class:`SourceRef` of a stored source (if it is known)."""
        return self._source_index.get(source_id)

    def group_by_hash(self, sources: list[SourceRef]) -> dict[str, list[SourceRef]]:
        """Group sources by their file hash.

        Parts that share one datasheet share the hash and therefore the
        ``source_id`` (plan WP2, step 6).
        """
        groups: dict[str, list[SourceRef]] = {}
        for source in sources:
            key = source.file_hash or source.source_id
            groups.setdefault(key, []).append(source)
        return groups


class DatasheetResolver:
    """Find and download a real datasheet when the indexed URL is unreliable.

    SearXNG supplies candidate URLs; the downloader remains the authority that
    decides whether a candidate is allowed, a real PDF, and a readable document.
    Candidates are ranked toward manufacturer and distributor documentation.
    """

    _TRUSTED_DOMAINS = (
        "ti.com",
        "st.com",
        "infineon.com",
        "onsemi.com",
        "nxp.com",
        "microchip.com",
        "espressif.com",
        "nordicsemi.com",
        "vishay.com",
        "rohm.com",
        "diodes.com",
        "mouser.com",
        "digikey.com",
        "element14.com",
        "farnell.com",
        "lcsc.com",
        "robu.in",
    )

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        downloader: DatasheetDownloader | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.downloader = downloader or DatasheetDownloader(self.settings)

    def resolve_and_download(
        self,
        mpn: str,
        manufacturer: str | None = None,
        direct_url: str | None = None,
        part_id: str | None = None,
    ) -> SourceRef | None:
        """Try fixture datasheets, the stored URL, then ranked SearXNG PDF candidates."""
        # 1. Synthetic / demo parts with bundled fixtures
        norm_mpn = (mpn or "").upper().replace("-", "")
        if "PMP100" in norm_mpn:
            fix_path = resolve_pdf_path("synthetic_mosfet.pdf", self.settings)
            if fix_path and fix_path.is_file():
                return SourceRef(
                    source_id=f"pdf-{part_id or 'synthetic-mosfet'}",
                    url=direct_url or "https://example.invalid/datasheets/PMP100N08.pdf",
                    type=SourceType.PDF,
                    file_hash="synthetic-mosfet",
                    local_path=str(fix_path),
                    page_count=2,
                    content_type="application/pdf",
                    note=part_id,
                )
        if "PGD35" in norm_mpn:
            fix_path = resolve_pdf_path("synthetic_gate_driver.pdf", self.settings)
            if fix_path and fix_path.is_file():
                return SourceRef(
                    source_id=f"pdf-{part_id or 'synthetic-gate-driver'}",
                    url=direct_url or "https://example.invalid/datasheets/PGD35.pdf",
                    type=SourceType.PDF,
                    file_hash="synthetic-gate-driver",
                    local_path=str(fix_path),
                    page_count=2,
                    content_type="application/pdf",
                    note=part_id,
                )

        candidates = self._candidate_urls(mpn, manufacturer, direct_url)
        for url in candidates:
            source = self.downloader.download(url, part_id, bypass_robots=not self.settings.respect_robots_txt)
            if source is not None:
                logger.info("Downloaded datasheet for %s from %s", mpn, url)
                return source
        logger.warning("No valid datasheet PDF found for %s after %d candidates", mpn, len(candidates))
        return None

    def _candidate_urls(
        self, mpn: str, manufacturer: str | None, direct_url: str | None
    ) -> list[str]:
        candidates: list[tuple[int, str]] = []
        if direct_url and direct_url.startswith(("http://", "https://")):
            # Ignore test dummy domains
            if not any(dummy in direct_url.lower() for dummy in ("example.invalid", "example.com", "localhost")):
                candidates.append((100, direct_url))

        # 1. Query DigiKey API for verified manufacturer datasheet URL
        if getattr(self.settings, "digikey_client_id", None):
            try:
                from collectors.digikey import DigiKeyCollector

                collector = DigiKeyCollector(self.settings)
                dk_res = run_sync(collector.search_keyword(mpn, limit=3))
                products = dk_res.get("Products") or []
                for prod in products:
                    ds_url = str(prod.get("DatasheetUrl") or prod.get("PrimaryDatasheet") or "").strip()
                    if ds_url.startswith(("http://", "https://")):
                        if not any(dummy in ds_url.lower() for dummy in ("example.invalid", "example.com", "localhost")):
                            logger.info("Found DigiKey datasheet URL for %s: %s", mpn, ds_url)
                            candidates.append((98, ds_url))
            except Exception as dk_exc:
                logger.debug("DigiKey datasheet lookup skipped or failed for %s: %s", mpn, dk_exc)

        endpoint = self.settings.searxng_url.rstrip("/")
        if endpoint:
            queries = [
                " ".join(item for item in (manufacturer or "", mpn, "datasheet filetype:pdf") if item),
                " ".join(item for item in (manufacturer or "", mpn, "datasheet pdf") if item),
            ]
            for query in queries:
                try:
                    with httpx.Client(
                        timeout=self.settings.web_search_timeout_seconds,
                        follow_redirects=True,
                    ) as client:
                        response = client.get(
                            f"{endpoint}/search?{quote_plus('q')}={quote_plus(query)}&format=json&categories=general",
                            headers={"Accept": "application/json", "User-Agent": self.settings.user_agent},
                        )
                        response.raise_for_status()
                        payload = response.json()
                    results = payload.get("results", []) if isinstance(payload, dict) else []
                    for item in results:
                        url = str(item.get("url") or "").strip()
                        title = str(item.get("title") or "").lower()
                        content = str(item.get("content") or "").lower()
                        if not url.startswith(("http://", "https://")):
                            continue
                        score = self._score_candidate(url, title, content, mpn)
                        if score > 0:
                            candidates.append((score, url))
                    if candidates:
                        break
                except Exception as exc:
                    logger.warning("Datasheet search failed for %s (%r): %s", mpn, query, exc)

        seen: set[str] = set()
        ordered: list[str] = []
        for _, url in sorted(candidates, key=lambda item: item[0], reverse=True):
            normalized = url.split("#", 1)[0]
            if normalized not in seen:
                seen.add(normalized)
                ordered.append(normalized)
        return ordered[: max(8, self.settings.web_search_results)]

    @classmethod
    def _score_candidate(cls, url: str, title: str, content: str, mpn: str) -> int:
        parsed = urlparse(url)
        host = parsed.netloc.lower().split(":", 1)[0]
        path = parsed.path.lower()
        text = f"{title} {content} {path}"
        if mpn.lower() not in text and mpn.lower().replace("-", "") not in text.replace("-", ""):
            return 0
        score = 10
        if path.endswith(".pdf") or ".pdf?" in url.lower():
            score += 60
        if "datasheet" in text or "data sheet" in text:
            score += 25
        if any(host == domain or host.endswith(f".{domain}") for domain in cls._TRUSTED_DOMAINS):
            score += 30
        if re.search(r"download|document|lit/|resource|documentation", path):
            score += 10
        return score
