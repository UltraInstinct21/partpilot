"""India Multi-Source Distributor Hub.

Coordinates web scraping across major component distributors deliverable in India:
1. element14 India (Avnet/Farnell group, Bangalore distribution center)
2. Robu.in (Macfos Ltd, Pune central warehouse)
3. Evelta Electronics (Bangalore / Mumbai domestic logistics)

Scrapes directly without robots.txt constraints, collecting INR pricing,
real-time stock in India, and local delivery lead times.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path

from collectors.scrapers.element14 import Element14Scraper
from collectors.scrapers.evelta import EveltaScraper
from collectors.scrapers.robu import RobuScraper
from shared.schemas import Offer

logger = logging.getLogger(__name__)


class IndiaSourcesHub:
    """Multi-source web scraper coordinator for distributors delivering to India."""

    def __init__(self) -> None:
        self.scrapers = [
            Element14Scraper(),
            RobuScraper(),
            EveltaScraper(),
        ]

    async def scrape_all_sources_for_part(
        self, mpn: str, part_id: str | None = None
    ) -> list[Offer]:
        """Scrape all Indian sources in parallel for an MPN."""
        tasks = [scraper.scrape_part(mpn, part_id=part_id) for scraper in self.scrapers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        offers: list[Offer] = []
        for res in results:
            if isinstance(res, Offer):
                offers.append(res)
            elif isinstance(res, Exception):
                logger.warning("Scraper failed during collection: %s", res)
        return offers


def populate_india_offers_in_db(db_path: str | Path) -> int:
    """Populate database with scraped offers from India distributors.

    Connects to the SQLite database and adds element14 India, Robu.in,
    and Evelta Electronics offers for each indexed part.
    """
    db_file = Path(db_path)
    if not db_file.is_file():
        logger.error("Database file not found at %s", db_path)
        return 0

    hub = IndiaSourcesHub()
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    parts = cur.execute(
        "SELECT part_id, mpn FROM parts ORDER BY part_id ASC"
    ).fetchall()

    total_added = 0
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        for part_id, mpn in parts:
            offers = loop.run_until_complete(hub.scrape_all_sources_for_part(mpn, part_id=part_id))
            for offer in offers:
                existing = cur.execute(
                    "SELECT offer_id FROM offers WHERE part_id = ? AND distributor = ?",
                    (part_id, offer.distributor),
                ).fetchone()

                if existing:
                    cur.execute(
                        """
                        UPDATE offers
                        SET stock = ?, unit_price = ?, currency = ?, sku = ?, url = ?, lead_time_days = ?
                        WHERE offer_id = ?
                        """,
                        (
                            offer.stock,
                            offer.unit_price,
                            offer.currency,
                            offer.sku,
                            offer.url,
                            offer.lead_time_days,
                            existing[0],
                        ),
                    )
                else:
                    new_offer_id = f"offer-{part_id}-{offer.distributor}"
                    cur.execute(
                        """
                        INSERT INTO offers (offer_id, part_id, distributor, sku, stock, unit_price, currency, price_breaks, lead_time_days, fetched_at, url)
                        VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?, CURRENT_TIMESTAMP, ?)
                        """,
                        (
                            new_offer_id,
                            part_id,
                            offer.distributor,
                            offer.sku,
                            offer.stock,
                            offer.unit_price,
                            offer.currency,
                            offer.lead_time_days,
                            offer.url,
                        ),
                    )
                    total_added += 1
        conn.commit()
    finally:
        conn.close()
        loop.close()

    return total_added


if __name__ == "__main__":
    import sys

    target_db = sys.argv[1] if len(sys.argv) > 1 else "data/partpilot.db"
    count = populate_india_offers_in_db(target_db)
    print(f"Successfully populated {count} Indian distributor offers into {target_db}")
