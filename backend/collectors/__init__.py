"""PartPilot collection layer (owned by agent A, plan WP1 + WP2).

The package contains

* :mod:`collectors.base` - rate limiter, disk cache, httpx factory, retry.
* :mod:`collectors.digikey` - DigiKey Product Information v4 client.
* :mod:`collectors.nexar` - Nexar (Octopart) supply GraphQL client.
* :mod:`collectors.mouser` - Mouser Search API client.
* :mod:`collectors.seeds` - seed list builder (bundled + category search).
* :mod:`collectors.datasheets` - robots aware datasheet downloader.
* :mod:`collectors.bundle` - the set of collectors per family.

Every client implements the frozen
:class:`shared.interfaces.Collector` protocol, the downloader implements
:class:`shared.interfaces.DatasheetDownloader`.
"""

from collectors.base import (
    CacheStats,
    CollectorError,
    DiskCache,
    HttpStatusError,
    InvalidPdfError,
    MissingCredentialsError,
    RateLimiter,
    RateLimitExceededError,
    RetryableStatusError,
    RetryPolicy,
    RobotsDisallowedError,
    TokenCache,
    make_async_client,
    make_client,
    run_sync,
    user_agent,
)
from collectors.bundle import DefaultCollectorBundle
from collectors.datasheets import DatasheetDownloader, DatasheetResolver
from collectors.digikey import DigiKeyCollector
from collectors.mouser import MouserCollector
from collectors.nexar import NexarCollector
from collectors.params import (
    resolve_parameter_name,
    slugify,
)
from collectors.seeds import (
    build_seed_list,
    bundled_part_records,
    load_bundled_seed,
)

__all__ = [
    "CacheStats",
    "CollectorError",
    "DatasheetDownloader",
    "DatasheetResolver",
    "DefaultCollectorBundle",
    "DigiKeyCollector",
    "DiskCache",
    "HttpStatusError",
    "InvalidPdfError",
    "MissingCredentialsError",
    "MouserCollector",
    "NexarCollector",
    "RateLimitExceededError",
    "RateLimiter",
    "RetryableStatusError",
    "RetryPolicy",
    "RobotsDisallowedError",
    "TokenCache",
    "build_seed_list",
    "bundled_part_records",
    "load_bundled_seed",
    "make_async_client",
    "make_client",
    "resolve_parameter_name",
    "run_sync",
    "slugify",
    "user_agent",
]
