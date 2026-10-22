"""Manual collection script (NOT part of the test suite).

This script talks to the **real** distributor APIs. It reads the credentials
from the local ``.env`` file (server side only) and must never be executed by
CI. The test suite never imports this module.

Usage::

    # offline: only the bundled seed list and the disk cache
    python -m collectors.manual.collect_manual --dry-run

    # real run (needs PARTPILOT_DIGIKEY_* / PARTPILOT_NEXAR_* / PARTPILOT_MOUSER_*)
    python -m collectors.manual.collect_manual --family mosfet --limit 25
    python -m collectors.manual.collect_manual --mpn IRF3205S

The raw responses are written to ``data/raw/<collector>/<date>/<hash>.json``
(the same files the disk cache uses) and the normalised parts are written to
``data/collected/<date>.json``. ``data/`` is git-ignored, so no datasheet or
API answer is ever committed.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from collectors.base import CollectorError, MissingCredentialsError
from collectors.bundle import DefaultCollectorBundle
from collectors.datasheets import DatasheetDownloader
from collectors.seeds import build_seed_list, bundled_part_records, load_bundled_seed
from shared.config import Settings, get_settings
from shared.schemas import Family

logger = logging.getLogger("partpilot.manual")

MANUAL_WARNING = (
    "MANUAL SCRIPT - this talks to the real distributor APIs and spends part of "
    "your daily request budget (DigiKey 1000/day, Mouser 1000/day)."
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=MANUAL_WARNING)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="use the bundled seed list and the disk cache only - no network call",
    )
    parser.add_argument(
        "--family",
        choices=[family.value for family in Family],
        default=Family.MOSFET.value,
        help="the family whose seed list is built (default: mosfet)",
    )
    parser.add_argument("--limit", type=int, default=25, help="number of parts")
    parser.add_argument(
        "--mpn",
        action="append",
        default=[],
        help="collect exactly this manufacturer part number (repeatable)",
    )
    parser.add_argument(
        "--datasheets",
        action="store_true",
        help="also download the datasheet of every collected part",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="where the normalised parts are written (default: data/collected)",
    )
    return parser.parse_args(argv)


def _write_parts(parts: list[dict[str, Any]], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    path = out_dir / f"{stamp}.json"
    path.write_text(json.dumps(parts, indent=2, default=str), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """Run the manual collection. Returns the process exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)
    settings: Settings = get_settings()
    settings.ensure_dirs()
    family = Family(args.family)

    if args.dry_run:
        return _dry_run(settings, family, args)

    logger.warning(MANUAL_WARNING)
    mpns = list(args.mpn)
    if not mpns:
        bundle = DefaultCollectorBundle(settings)
        collectors = bundle.for_family(family)
        mpns = build_seed_list(family, args.limit, collector=collectors[0] if collectors else None)
    logger.info("collecting %d parts of the family %s", len(mpns), family.value)

    collected: list[dict[str, Any]] = []
    downloader = DatasheetDownloader(settings)
    for mpn in mpns:
        for collector in DefaultCollectorBundle(settings).collectors:
            try:
                record = collector.search_by_mpn(mpn)
            except MissingCredentialsError as exc:
                logger.warning("%s is skipped: %s", collector.name, exc)
                continue
            except CollectorError as exc:
                logger.warning("%s failed for %s: %s", collector.name, mpn, exc)
                continue
            if record is None:
                logger.info("%s has no part %s", collector.name, mpn)
                continue
            collected.append(record.model_dump(mode="json"))
            logger.info("%s collected %s", collector.name, mpn)
            if args.datasheets and record.datasheet_url:
                source = downloader.download(record.datasheet_url, record.part_id)
                if source is None:
                    logger.warning("no datasheet for %s", mpn)
                else:
                    logger.info(
                        "datasheet for %s stored as %s (%s pages)",
                        mpn,
                        source.source_id,
                        source.page_count,
                    )

    out_dir = args.out or (settings.data_dir / "collected")
    path = _write_parts(collected, out_dir)
    logger.info("%d parts written to %s", len(collected), path)
    return 0


def _dry_run(settings: Settings, family: Family, args: argparse.Namespace) -> int:
    """Use the bundled seed list and the disk cache only."""
    logger.info("dry run: no network call is made")
    mpns = load_bundled_seed(family, settings=settings)
    logger.info("%d bundled part numbers of the family %s", len(mpns), family.value)
    for mpn in mpns:
        logger.info("  %s", mpn)
    records = bundled_part_records(family, settings=settings)
    out_dir = args.out or (settings.data_dir / "collected")
    path = _write_parts(
        [record.model_dump(mode="json") for record in records],
        out_dir,
    )
    logger.info("%d bundled parts written to %s", len(records), path)
    from collectors.base import DiskCache

    for namespace in ("digikey", "nexar", "mouser"):
        cache = DiskCache(settings.raw_dir, namespace)
        stats = cache.stats()
        logger.info("cache %s: %s", namespace, json.dumps(stats.as_dict(), default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    sys.exit(main())
