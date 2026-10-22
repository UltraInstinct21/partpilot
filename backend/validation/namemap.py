"""Fuzzy mapping of a raw datasheet name onto a standard parameter name.

The name map is the part of the system that learns: every correction a person
makes in the review queue is meant to end up in the ``name_map`` table
(plan WP5 step 7).  Until that table exists the matcher works with a
provisional alias table and with a lookup that the integration can inject.

Matching rules
--------------
* An exact hit on a known alias scores ``1.0``.
* Otherwise the raw name is compared with every alias using
  :func:`rapidfuzz.fuzz.token_sort_ratio` and :func:`rapidfuzz.fuzz.WRatio`.
  A score below ``threshold`` (default 88) means "no match".
* When two different standard names are within ``margin`` points of the best
  score the result is ambiguous and ``None`` is returned - a wrong parameter
  name is worse than an unmapped one.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Final

from rapidfuzz import fuzz

__all__ = [
    "DEFAULT_ALIASES",
    "DEFAULT_MARGIN",
    "DEFAULT_THRESHOLD",
    "NameMatcher",
    "normalize_name",
]

#: Default score a fuzzy match has to reach.
DEFAULT_THRESHOLD: Final[int] = 88

#: Two candidates within this margin of the best score are "ambiguous".
DEFAULT_MARGIN: Final[int] = 5

#: Provisional alias table (normalised spelling -> standard name).  The
#: integration replaces this with the ``name_map`` table.
DEFAULT_ALIASES: Final[dict[str, str]] = {
    # ------------------------------------------------------------ MOSFET
    "vds max": "vds_max",
    "vds": "vds_max",
    "vds rating": "vds_max",
    "drain source voltage": "vds_max",
    "drain to source voltage": "vds_max",
    "maximum drain source voltage": "vds_max",
    "id": "id_continuous",
    "id continuous": "id_continuous",
    "drain current": "id_continuous",
    "continuous drain current": "id_continuous",
    "rds on": "rds_on",
    "rds on max": "rds_on",
    "on resistance": "rds_on",
    "on state resistance": "rds_on",
    "drain source on resistance": "rds_on",
    "vgs th": "vgs_threshold",
    "vgs th min": "vgs_threshold",
    "vgs th max": "vgs_threshold",
    "vgs threshold": "vgs_threshold",
    "gate threshold voltage": "vgs_threshold",
    "threshold voltage": "vgs_threshold",
    "vgs max": "vgs_max",
    "vgs rating": "vgs_max",
    "maximum gate source voltage": "vgs_max",
    "gate source voltage maximum": "vgs_max",
    "qg": "total_gate_charge_qg",
    "qg total": "total_gate_charge_qg",
    "total gate charge": "total_gate_charge_qg",
    "gate charge": "total_gate_charge_qg",
    "qgd": "gate_drain_charge_qgd",
    "gate drain charge": "gate_drain_charge_qgd",
    "gd charge": "gate_drain_charge_qgd",
    "miller charge": "gate_drain_charge_qgd",
    "ciss": "input_capacitance_ciss",
    "input capacitance": "input_capacitance_ciss",
    "input capacitance ciss": "input_capacitance_ciss",
    "coss": "output_capacitance_coss",
    "output capacitance": "output_capacitance_coss",
    "output capacitance coss": "output_capacitance_coss",
    "tj": "max_junction_temp",
    "tj max": "max_junction_temp",
    "max junction temp": "max_junction_temp",
    "maximum junction temperature": "max_junction_temp",
    "junction temperature": "max_junction_temp",
    "rthjc": "thermal_resistance",
    "rth jc": "thermal_resistance",
    "theta jc": "thermal_resistance",
    "thermal resistance": "thermal_resistance",
    "thermal resistance junction to case": "thermal_resistance",
    "qrr": "reverse_recovery_qrr",
    "reverse recovery charge": "reverse_recovery_qrr",
    # -------------------------------------------------------- GATE DRIVER
    "vcc min": "supply_voltage_min",
    "vdd min": "supply_voltage_min",
    "vcc minimum": "supply_voltage_min",
    "supply voltage min": "supply_voltage_min",
    "operating supply voltage min": "supply_voltage_min",
    "vcc max": "supply_voltage_max",
    "vdd max": "supply_voltage_max",
    "vcc maximum": "supply_voltage_max",
    "supply voltage max": "supply_voltage_max",
    "operating supply voltage max": "supply_voltage_max",
    "peak source current": "peak_source_current",
    "source peak current": "peak_source_current",
    "i pk": "peak_source_current",
    "peak sink current": "peak_sink_current",
    "sink peak current": "peak_sink_current",
    "i pk sink": "peak_sink_current",
    "input logic level": "input_logic_level",
    "logic input threshold": "input_logic_level",
    "vih": "input_logic_level",
    "logic high input voltage": "input_logic_level",
    "prop delay": "propagation_delay",
    "propagation delay": "propagation_delay",
    "tpd": "propagation_delay",
    "prop delay tpd": "propagation_delay",
    "rise time": "rise_time",
    "tr": "rise_time",
    "rise time tr": "rise_time",
    "fall time": "fall_time",
    "tf": "fall_time",
    "fall time tf": "fall_time",
    "uvlo": "uvlo_threshold",
    "uvlo threshold": "uvlo_threshold",
    "undervoltage lockout": "uvlo_threshold",
    "channel count": "channel_count",
    "number of channels": "channel_count",
    "channels": "channel_count",
    "n channels": "channel_count",
    "driver channels": "channel_count",
    "operating temp min": "operating_temp_min",
    "operating temperature min": "operating_temp_min",
    "ta min": "operating_temp_min",
    "t ambient min": "operating_temp_min",
    "ambient temperature min": "operating_temp_min",
    "operating temp max": "operating_temp_max",
    "operating temperature max": "operating_temp_max",
    "ta max": "operating_temp_max",
    "t ambient max": "operating_temp_max",
    "ambient temperature max": "operating_temp_max",
    # ------------------------------------------------------------- COMMON
    "package": "package",
    "package type": "package",
    "package name": "package",
    "case": "package",
    "body": "package",
}

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


def normalize_name(text: str | None) -> str:
    """Return a comparable form of a parameter name.

    Lower case, the micro sign folded to ``u`` and every run of non
    alphanumeric characters replaced by a single space.  ``"Rds(on)"`` and
    ``"RDS (ON)"`` both become ``"rds on"``.
    """
    if not text:
        return ""
    lowered = str(text).lower().replace("µ", "u").replace("μ", "u")
    cleaned = _NON_ALPHANUMERIC.sub(" ", lowered)
    return " ".join(cleaned.split())


class NameMatcher:
    """Map a raw datasheet name onto a standard parameter name.

    Parameters
    ----------
    lookup:
        The injected name map.  Either a mapping of alias -> standard name or
        a callable ``lookup(raw_name) -> str | None`` (for example a
        repository method that reads the ``name_map`` table).  ``None`` uses
        :data:`DEFAULT_ALIASES`.  A mapping is *merged* into the provisional
        alias table, it never removes an alias the matcher already knows.
    aliases:
        Extra aliases, added on top of ``lookup``.  Use
        :meth:`add_alias` to learn from a human correction.
    threshold:
        Minimum score of a fuzzy match.
    margin:
        Two candidates within this margin of the best score are ambiguous.
    use_defaults:
        ``False`` drops the provisional alias table (only the injected lookup
        is used).

    Notes
    -----
    The score of an **exact** match is ``1.0``; the score of a **fuzzy** match
    is the rapidfuzz score on the ``0 .. 100`` scale.
    """

    def __init__(
        self,
        lookup: Mapping[str, str] | Callable[[str], str | None] | None = None,
        *,
        aliases: Mapping[str, str] | None = None,
        threshold: int = DEFAULT_THRESHOLD,
        margin: int = DEFAULT_MARGIN,
        use_defaults: bool = True,
    ) -> None:
        self.threshold = int(threshold)
        self.margin = int(margin)
        self._lookup: Callable[[str], str | None] | None = None
        self._aliases: dict[str, str] = {}

        base: Mapping[str, str] = {}
        if use_defaults:
            base = DEFAULT_ALIASES
        if lookup is None:
            pass
        elif isinstance(lookup, Mapping):
            # The injected name map is *added* to the provisional table, it
            # never removes an alias the matcher already knows.
            base = {**base, **lookup}
        elif callable(lookup):
            self._lookup = lookup
        else:  # pragma: no cover - defensive
            raise TypeError("lookup must be a mapping, a callable or None")

        for alias, standard in base.items():
            self.add_alias(alias, standard)
        for alias, standard in (aliases or {}).items():
            self.add_alias(alias, standard)

    # ------------------------------------------------------------------ API
    def add_alias(self, alias: str, standard: str) -> None:
        """Teach the matcher one more alias (plan WP5 step 7)."""
        key = normalize_name(alias)
        if key:
            self._aliases[key] = standard

    def standard_names(self) -> list[str]:
        """Return the sorted list of standard names the matcher can produce."""
        return sorted(set(self._aliases.values()))

    def match(self, raw_name: str | None) -> str | None:
        """Return the standard name for ``raw_name`` or ``None``."""
        name, _ = self.match_with_score(raw_name)
        return name

    def match_with_score(self, raw_name: str | None) -> tuple[str | None, float]:
        """Return ``(standard_name, score)``.

        ``(None, best_score)`` is returned when nothing matched or when the
        best match is ambiguous.
        """
        normalized = normalize_name(raw_name)
        if not normalized:
            return (None, 0.0)

        # 1. an injected lookup wins over everything
        if self._lookup is not None:
            for probe in (normalized, str(raw_name or "")):
                try:
                    result = self._lookup(probe)
                except Exception:
                    result = None
                if result:
                    return (str(result), 1.0)

        # 2. an exact alias
        exact = self._aliases.get(normalized)
        if exact is not None:
            return (exact, 1.0)

        # 3. a fuzzy match
        best_per_standard: dict[str, float] = {}
        for alias, standard in self._aliases.items():
            score = max(
                float(fuzz.token_sort_ratio(normalized, alias)),
                float(fuzz.WRatio(normalized, alias)),
            )
            if score > best_per_standard.get(standard, 0.0):
                best_per_standard[standard] = score

        if not best_per_standard:
            return (None, 0.0)

        best = max(best_per_standard.values())
        if best < self.threshold:
            return (None, best)

        winners = [
            standard for standard, score in best_per_standard.items() if score >= best - self.margin
        ]
        if len(winners) != 1:
            return (None, best)
        return (winners[0], best)

    def candidates(self, raw_name: str | None, limit: int = 5) -> list[tuple[str, float]]:
        """Return the best ``limit`` candidates, best score first."""
        normalized = normalize_name(raw_name)
        if not normalized:
            return []
        scores: dict[str, float] = {}
        for alias, standard in self._aliases.items():
            score = max(
                float(fuzz.token_sort_ratio(normalized, alias)),
                float(fuzz.WRatio(normalized, alias)),
            )
            if score > scores.get(standard, 0.0):
                scores[standard] = score
        ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return ordered[:limit]
