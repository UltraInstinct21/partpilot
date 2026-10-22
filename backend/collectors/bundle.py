"""The set of collectors the application uses (FR-01).

The bundle implements the frozen
:class:`shared.interfaces.CollectorBundle` protocol. The families follow the
seed data: the MOSFETs are covered by DigiKey and Nexar, the gate drivers by
DigiKey, Mouser and Nexar.
"""

from __future__ import annotations

import logging
from typing import Any

from collectors.digikey import DigiKeyCollector
from collectors.mouser import MouserCollector
from collectors.nexar import NexarCollector
from shared.config import Settings, get_settings
from shared.schemas import Family

logger = logging.getLogger(__name__)

__all__ = ["DefaultCollectorBundle", "FAMILY_COLLECTORS"]

#: Which distributor serves which family.
FAMILY_COLLECTORS: dict[Family, tuple[str, ...]] = {
    Family.MOSFET: ("digikey", "nexar"),
    Family.GATE_DRIVER: ("digikey", "mouser", "nexar"),
}


class DefaultCollectorBundle:
    """Collect every part of a family with the distributors that serve it."""

    def __init__(
        self,
        settings: Settings | None = None,
        collectors: list[Any] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.collectors: list[Any] = (
            collectors
            if collectors is not None
            else [
                DigiKeyCollector(self.settings),
                NexarCollector(self.settings),
                MouserCollector(self.settings),
            ]
        )

    def for_family(self, family: Family) -> list[Any]:
        """Return the collectors that can serve ``family``."""
        wanted = FAMILY_COLLECTORS.get(family, ())
        selected = [c for c in self.collectors if getattr(c, "name", "") in wanted]
        if not selected:
            logger.warning("no collector serves the family %s", family)
        return selected
