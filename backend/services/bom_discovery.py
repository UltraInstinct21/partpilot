"""AI-assisted query planning for BOM enrichment.

The planner may suggest search wording, but it never decides whether a BOM
line is risky. Risk calculation remains deterministic in :mod:`services.bom`.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

from extraction.llm.factory import build_chat_model
from shared.config import Settings, get_settings

logger = logging.getLogger(__name__)


class BomQueryPlanner:
    """Create safe, MPN-anchored queries for live BOM enrichment."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._model: Any | None = None
        self._model_unavailable = False

    def plan(self, mpn: str, manufacturer: str | None = None) -> list[str]:
        mpn = mpn.strip()
        if not mpn:
            return []
        prefix = f"{manufacturer.strip()} " if manufacturer and manufacturer.strip() else ""
        fallback = [
            f"{prefix}{mpn} datasheet filetype:pdf",
            f"{prefix}{mpn} lifecycle status EOL NRND PCN",
            f"{prefix}{mpn} authorized distributor stock availability",
        ]
        model = self._get_model()
        if model is None:
            return fallback
        prompt = (
            "Create up to three web search queries for this electronic component BOM line. "
            "Return JSON only as an array of strings. Every query must contain the exact "
            f"MPN '{mpn}'. Cover: authoritative datasheet PDF, lifecycle/EOL/NRND/PCN, "
            f"and authorized distributor stock. Manufacturer: {manufacturer or 'unknown'}."
        )
        try:
            pool = ThreadPoolExecutor(max_workers=1)
            future = pool.submit(model.invoke, prompt)
            try:
                response = future.result(timeout=4)
            finally:
                # Do not wait for an unreachable local model after the
                # request deadline. The deterministic query plan remains
                # valid and the abandoned worker is allowed to finish in the
                # background without holding up BOM risk scoring.
                pool.shutdown(wait=False, cancel_futures=True)
            content = getattr(response, "content", response)
            if isinstance(content, list):
                content = " ".join(str(item) for item in content)
            values = json.loads(str(content).strip().strip("`"))
            if isinstance(values, list):
                planned = [
                    str(value).strip()
                    for value in values
                    if str(value).strip() and mpn.lower() in str(value).lower()
                ]
                if planned:
                    return list(dict.fromkeys(planned))[:3]
        except FuturesTimeoutError as exc:
            self._model_unavailable = True
            logger.info("BOM query planner timed out for %s: %s", mpn, exc)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.info("BOM query planner fallback for %s: %s", mpn, exc)
        except Exception as exc:
            self._model_unavailable = True
            logger.warning("BOM query planner failed for %s: %s", mpn, exc)
        return fallback

    def _get_model(self) -> Any | None:
        if self._model_unavailable:
            return None
        if self._model is not None:
            return self._model
        try:
            self._model = build_chat_model(settings=self.settings)
        except Exception as exc:
            logger.info("AI BOM query planning unavailable: %s", exc)
        return self._model


__all__ = ["BomQueryPlanner"]
