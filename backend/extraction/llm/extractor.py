"""The LLM backed extractor (tiers 2 and 3) - plan WP4.

``LLMExtractorImpl`` implements :class:`shared.interfaces.LLMExtractor`:

* tier 2 reads the text and the table rows of the pages it is given,
* tier 3 reads the rendered image of a page,
* the name mapper proposes a standard name (a person has to approve it),
* the search filter builder builds a filter (the database executes it),
* the alternative explainer writes one short sentence.

Every call goes through :mod:`extraction.llm.recorder` so the cost of the
extraction can be reported (NFR-05), and every field that the model did not
fill in becomes a failed field - it is never guessed (NFR-03).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from shared.config import Settings, get_settings
from shared.schemas import (
    ExtractionMethod,
    ExtractionResult,
    Family,
    SearchFilter,
)

from . import chains
from .chains import (
    CHAIN_ALTERNATIVE,
    CHAIN_NAME_MAPPER,
    CHAIN_SEARCH_FILTER,
    CHAIN_TIER2,
    CHAIN_TIER3,
    NameMappingProposal,
)
from .chains import model_name as _model_name
from .factory import build_chat_model
from .parameters import parameter_names_for, spec_model_for
from .recorder import NoOpRecorder, Recorder, build_call_record

logger = logging.getLogger(__name__)

#: A name mapping below this confidence is treated as "not sure".
MIN_MAPPING_CONFIDENCE = 0.5


class LLMExtractorImpl:
    """The LLM backed extractor."""

    def __init__(
        self,
        model: Any | None = None,
        recorder: Recorder | None = None,
        settings: Settings | None = None,
        prompts_dir: Path | str | None = None,
        vision_model: Any | None = None,
    ) -> None:
        """Create the extractor.

        Args:
            model: an already built chat model. When it is ``None`` the model
                is built lazily on the first call (never at import time).
            recorder: the recorder every call is written to. A no-op recorder
                is used when none is injected.
            settings: the settings to use.
            prompts_dir: an alternative directory with the prompt files.
            vision_model: the model used for tier 3. Built lazily when missing.
        """
        self.settings = settings or get_settings()
        self._model = model
        # An injected model is used for the vision chain as well, so a test
        # never builds a real provider client.
        self._vision_model = vision_model if vision_model is not None else model
        self._recorder: Recorder = recorder if recorder is not None else NoOpRecorder()
        self._prompts_dir = Path(prompts_dir) if prompts_dir is not None else None
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_enabled: set[str] = (
            set(chains.chain_names()) if self.settings.llm_cache_enabled else set()
        )

    # -- model -----------------------------------------------------------------

    @property
    def model(self) -> Any:
        """Return the text model, building it on first use."""
        if self._model is None:
            self._model = self._build_model(vision=False)
        return self._model

    @property
    def vision_model(self) -> Any:
        """Return the vision model, building it on first use."""
        if self._vision_model is None:
            self._vision_model = self._build_model(vision=True)
        return self._vision_model

    def _build_model(self, vision: bool) -> Any:
        # The SQLite cache is installed by the factory.
        return build_chat_model(settings=self.settings, vision=vision)

    # -- cache -----------------------------------------------------------------

    def disable_cache(self, chain: str) -> None:
        """Turn the result cache of one chain off."""
        self._cache_enabled.discard(chain)

    def enable_cache(self, chain: str) -> None:
        """Turn the result cache of one chain on."""
        self._cache_enabled.add(chain)

    @staticmethod
    def _cache_key(*parts: Any) -> str:
        digest = hashlib.sha256()
        for part in parts:
            digest.update(repr(part).encode("utf-8", errors="replace"))
            digest.update(b"\x00")
        return digest.hexdigest()

    def _cache_get(self, chain: str, key: str) -> Any:
        if chain not in self._cache_enabled:
            return None
        return self._cache.setdefault(chain, {}).get(key)

    def _cache_put(self, chain: str, key: str, value: Any) -> None:
        if chain not in self._cache_enabled:
            return
        self._cache.setdefault(chain, {})[key] = value

    # -- recording -------------------------------------------------------------

    def _record(
        self,
        chain: str,
        model: Any,
        prompt_version: str,
        part_id: str | None = None,
        cached: bool = False,
        duration_ms: int | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        raw: Any = None,
    ) -> None:
        record = build_call_record(
            chain=chain,
            model=_model_name(model),
            response=raw,
            prompt_version=prompt_version,
            part_id=part_id,
            cached=cached,
            duration_ms=duration_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            settings=self.settings,
        )
        self._recorder.record(record)

    # -- tier 2 ----------------------------------------------------------------

    def extract_tier2(
        self,
        pages: Iterable[tuple[int, str]],
        family: Family,
        part_id: str | None = None,
    ) -> ExtractionResult:
        """Extract the values of the given pages with the text model."""
        page_list = [(int(number), text) for number, text in pages]
        names = list(parameter_names_for(family))
        if not page_list:
            return ExtractionResult(
                part_id=part_id,
                family=family,
                method=ExtractionMethod.TIER2,
                values=[],
                pages_used=[],
                failed_fields=names,
                notes="no page was handed over",
            )
        messages = chains.build_tier2_messages(family, page_list, self._prompts_dir)
        key = self._cache_key(CHAIN_TIER2, family.value, page_list)
        cached_result = self._cache_get(CHAIN_TIER2, key)
        if cached_result is not None:
            self._record(
                chain=CHAIN_TIER2,
                model=self.model,
                prompt_version=chains.prompt_version(
                    chains.PROMPT_TIER2, directory=self._prompts_dir
                ),
                part_id=part_id,
                cached=True,
                duration_ms=0,
            )
            return cached_result.model_copy(deep=True)

        outcome = chains.call_structured(
            self.model,
            spec_model_for(family),
            messages,
            chains.PROMPT_TIER2,
            self._prompts_dir,
        )
        self._record(
            chain=CHAIN_TIER2,
            model=self.model,
            prompt_version=outcome.prompt_version,
            part_id=part_id,
            cached=False,
            duration_ms=outcome.duration_ms,
            tokens_in=outcome.tokens_in,
            tokens_out=outcome.tokens_out,
            raw=outcome.raw,
        )
        spec = outcome.value
        if spec is None:
            logger.warning("tier 2 could not be parsed: %s", outcome.error)
            values: list = []
            failed = names
        else:
            values, failed = chains.spec_to_values(spec, ExtractionMethod.TIER2, part_id)
        result = ExtractionResult(
            part_id=part_id,
            family=family,
            method=ExtractionMethod.TIER2,
            values=values,
            pages_used=[number for number, _ in page_list],
            failed_fields=failed,
            notes=outcome.error,
            duration_ms=outcome.duration_ms,
        )
        self._cache_put(CHAIN_TIER2, key, result)
        return result

    # -- tier 3 ----------------------------------------------------------------

    def extract_tier3(
        self,
        page_images: Iterable[tuple[int, bytes]],
        family: Family,
        part_id: str | None = None,
    ) -> ExtractionResult:
        """Extract the values of the given page images with the vision model."""
        image_list = [(int(number), image) for number, image in page_images]
        names = list(parameter_names_for(family))
        if not image_list:
            return ExtractionResult(
                part_id=part_id,
                family=family,
                method=ExtractionMethod.TIER3,
                values=[],
                pages_used=[],
                failed_fields=names,
                notes="no page image was handed over",
            )
        model = self.vision_model
        specs = []
        values: list = []
        failed: list[str] = []
        duration = 0
        for number, image in image_list:
            messages = chains.build_tier3_messages(family, number, image, self._prompts_dir)
            key = self._cache_key(CHAIN_TIER3, family.value, number, image)
            cached_result = self._cache_get(CHAIN_TIER3, key)
            if cached_result is not None:
                self._record(
                    chain=CHAIN_TIER3,
                    model=model,
                    prompt_version=chains.prompt_version(
                        chains.PROMPT_TIER3, directory=self._prompts_dir
                    ),
                    part_id=part_id,
                    cached=True,
                    duration_ms=0,
                )
                specs.append(cached_result)
                continue
            outcome = chains.call_structured(
                model,
                spec_model_for(family),
                messages,
                chains.PROMPT_TIER3,
                self._prompts_dir,
            )
            self._record(
                chain=CHAIN_TIER3,
                model=model,
                prompt_version=outcome.prompt_version,
                part_id=part_id,
                cached=False,
                duration_ms=outcome.duration_ms,
                tokens_in=outcome.tokens_in,
                tokens_out=outcome.tokens_out,
                raw=outcome.raw,
            )
            duration += outcome.duration_ms
            if outcome.value is None:
                logger.warning("tier 3 could not be parsed: %s", outcome.error)
                continue
            specs.append(outcome.value)
            self._cache_put(CHAIN_TIER3, key, outcome.value)

        merged, failed = chains.merge_specs(specs)
        if merged is None:
            failed = names
            values = []
        else:
            values, failed = chains.spec_to_values(merged, ExtractionMethod.TIER3, part_id)
        return ExtractionResult(
            part_id=part_id,
            family=family,
            method=ExtractionMethod.TIER3,
            values=values,
            pages_used=[number for number, _ in image_list],
            failed_fields=failed,
            scanned=True,
            duration_ms=duration,
        )

    # -- name mapper -----------------------------------------------------------

    def map_name(self, raw_name: str, family: Family) -> str | None:
        """Propose a standard name for an unknown raw name.

        The proposal is never an approval: a person has to accept it.
        """
        messages = chains.build_name_mapper_messages(raw_name, family, self._prompts_dir)
        key = self._cache_key(CHAIN_NAME_MAPPER, family.value, raw_name)
        cached_result = self._cache_get(CHAIN_NAME_MAPPER, key)
        if cached_result is not None:
            self._record(
                chain=CHAIN_NAME_MAPPER,
                model=self.model,
                prompt_version=chains.prompt_version(
                    chains.PROMPT_NAME_MAPPER, directory=self._prompts_dir
                ),
                cached=True,
                duration_ms=0,
            )
            return cached_result

        outcome = chains.call_structured(
            self.model,
            NameMappingProposal,
            messages,
            chains.PROMPT_NAME_MAPPER,
            self._prompts_dir,
        )
        self._record(
            chain=CHAIN_NAME_MAPPER,
            model=self.model,
            prompt_version=outcome.prompt_version,
            cached=False,
            duration_ms=outcome.duration_ms,
            tokens_in=outcome.tokens_in,
            tokens_out=outcome.tokens_out,
            raw=outcome.raw,
        )
        proposal = outcome.value
        if proposal is None:
            logger.warning("name mapper could not be parsed: %s", outcome.error)
            return None
        name = proposal.standard_name
        if not name:
            return None
        if name not in parameter_names_for(family):
            logger.warning("name mapper proposed an unknown parameter %r", name)
            return None
        if proposal.confidence < MIN_MAPPING_CONFIDENCE:
            logger.info("name mapper was not sure about %r", name)
            return None
        self._cache_put(CHAIN_NAME_MAPPER, key, name)
        return name

    # -- search filter ---------------------------------------------------------

    def build_search_filter(self, query: str) -> SearchFilter:
        """Turn a natural-language query into a validated filter."""
        messages = chains.build_search_filter_messages(query, self._prompts_dir)
        key = self._cache_key(CHAIN_SEARCH_FILTER, query)
        cached_result = self._cache_get(CHAIN_SEARCH_FILTER, key)
        if cached_result is not None:
            self._record(
                chain=CHAIN_SEARCH_FILTER,
                model=self.model,
                prompt_version=chains.prompt_version(
                    chains.PROMPT_SEARCH_FILTER, directory=self._prompts_dir
                ),
                cached=True,
                duration_ms=0,
            )
            return cached_result.model_copy(deep=True)

        outcome = chains.call_structured(
            self.model,
            SearchFilter,
            messages,
            chains.PROMPT_SEARCH_FILTER,
            self._prompts_dir,
        )
        self._record(
            chain=CHAIN_SEARCH_FILTER,
            model=self.model,
            prompt_version=outcome.prompt_version,
            cached=False,
            duration_ms=outcome.duration_ms,
            tokens_in=outcome.tokens_in,
            tokens_out=outcome.tokens_out,
            raw=outcome.raw,
        )
        filt = outcome.value
        if filt is None:
            logger.warning("search filter could not be parsed: %s", outcome.error)
            return SearchFilter(text=query)
        filt = chains.validate_search_filter(filt)
        self._cache_put(CHAIN_SEARCH_FILTER, key, filt)
        return filt

    # -- alternative explainer --------------------------------------------------

    def explain_alternative(self, differences: dict[str, dict[str, float | None]], mpn: str) -> str:
        """Return one short sentence describing the trade-off."""
        messages = chains.build_alternative_messages(differences, mpn, self._prompts_dir)
        key = self._cache_key(CHAIN_ALTERNATIVE, mpn, differences)
        cached_result = self._cache_get(CHAIN_ALTERNATIVE, key)
        if cached_result is not None:
            self._record(
                chain=CHAIN_ALTERNATIVE,
                model=self.model,
                prompt_version=chains.prompt_version(
                    chains.PROMPT_ALTERNATIVE, directory=self._prompts_dir
                ),
                cached=True,
                duration_ms=0,
            )
            return cached_result

        outcome = chains.call_text(
            self.model, messages, chains.PROMPT_ALTERNATIVE, self._prompts_dir
        )
        self._record(
            chain=CHAIN_ALTERNATIVE,
            model=self.model,
            prompt_version=outcome.prompt_version,
            cached=False,
            duration_ms=outcome.duration_ms,
            tokens_in=outcome.tokens_in,
            tokens_out=outcome.tokens_out,
            raw=outcome.raw,
        )
        sentence = chains.clean_explanation(outcome.value or "", differences, mpn)
        self._cache_put(CHAIN_ALTERNATIVE, key, sentence)
        return sentence


__all__ = ["LLMExtractorImpl", "MIN_MAPPING_CONFIDENCE"]
