"""Base web scraper infrastructure for component distributors.

This scraper operates without robots.txt restrictions, enabling direct
extraction of component availability, real-time pricing, and specifications
from authorized distributor portals deliverable in India.
"""

from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_SCRAPER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class BaseWebScraper:
    """Base class for distributor web scrapers.

    Does not enforce robots.txt restrictions. Bypasses blocking headers
    and extracts structured catalog offers.
    """

    def __init__(
        self,
        distributor_name: str,
        base_url: str,
        user_agent: str = DEFAULT_SCRAPER_USER_AGENT,
        timeout: float = 10.0,
    ) -> None:
        self.distributor_name = distributor_name
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout = timeout

    def _clean_price(self, text: str | None) -> float | None:
        """Parse numeric price from string with currency symbols like Rs, INR, or dollar."""
        if not text:
            return None
        cleaned = re.sub(r"[^\d.]", "", text.strip())
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    def _clean_stock(self, text: str | None) -> int | None:
        """Parse numeric stock count from text like '150 in stock' or 'Available: 20'."""
        if not text:
            return None
        match = re.search(r"(\d+[\d,]*)", text)
        if match:
            digits = match.group(1).replace(",", "")
            try:
                return int(digits)
            except (ValueError, TypeError):
                return None
        if "in stock" in text.lower() or "available" in text.lower():
            return 100
        return 0

    async def fetch_html(self, url: str) -> str | None:
        """Fetch raw HTML for url directly without robots.txt blockage."""
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,en-IN;q=0.8",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return response.text
                logger.warning(
                    "Scraper %s received HTTP %d for %s",
                    self.distributor_name,
                    response.status_code,
                    url,
                )
                return None
        except Exception as exc:
            logger.warning("Scraper %s failed to fetch %s: %s", self.distributor_name, url, exc)
            return None

    def parse_soup(self, html: str) -> BeautifulSoup:
        """Return parsed BeautifulSoup tree using html.parser."""
        return BeautifulSoup(html, "html.parser")
