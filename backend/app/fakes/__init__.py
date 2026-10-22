"""Fake implementations used until the real modules land.

Everything in this package is a *development* implementation:

* it never touches the network and never calls an LLM;
* it is backed by the recorded fixtures in ``contracts/fixtures``;
* it implements the protocols of ``shared.interfaces`` so it can be swapped
  for the real implementation without changing a single route.

The real wiring replaces these classes in :mod:`app.wiring` (one file change).
"""

from __future__ import annotations

from app.fakes.llm import StubLLMExtractor
from app.fakes.repository import InMemoryPartsRepository
from app.fakes.services import (
    FakeAlternativesService,
    FakeBomService,
    FakeJobRunner,
    FakeReviewService,
    FakeSearchService,
    FakeStatsService,
)
from app.fakes.tier1 import StubTier1Extractor
from app.fakes.validator import StubValidator

__all__ = [
    "FakeAlternativesService",
    "FakeBomService",
    "FakeJobRunner",
    "FakeReviewService",
    "FakeSearchService",
    "FakeStatsService",
    "InMemoryPartsRepository",
    "StubLLMExtractor",
    "StubTier1Extractor",
    "StubValidator",
]
