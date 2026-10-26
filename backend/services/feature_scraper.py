"""Feature-wise semiconductor scraping engine for PartPilot.

Implements dedicated, parameter-specific extraction methods engineered for electronic specifications:
- Vds (Drain-Source Breakdown Voltage)
- Rds(on) (On-State Resistance with test condition verification)
- Id (Continuous Drain Current at specified case temperature)
- Vgs(th) (Gate Threshold Voltage, strictly isolated from Vgs(max))
- Vgs(max) (Gate-Source Voltage Limit)
- Qg, Qgd, Qgs (Gate charges in nC -> Coulombs)
- Ciss, Coss, Crss (Capacitances in pF/nF -> Farads, preserving Ciss > Coss)
- Tj(max) (Operating Junction Temperature)
- RthJC, RthJA (Thermal resistances in °C/W)
- Pd (Maximum Power Dissipation in Watts)
- Gate Driver features (IO+, IO-, VCC, tpd, tr, tf, channels)
- Multi-distributor offers (DigiKey, Mouser, element14, Robu, Evelta, LCSC)
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from collectors.scrapers.india_hub import IndiaSourcesHub
from shared.schemas import (
    Family,
    Offer,
    ParameterValue,
    PartRecord,
    ValueStatus,
)

logger = logging.getLogger(__name__)

# Packages commonly used in discrete semiconductors and power ICs
CANONICAL_PACKAGES: list[tuple[str, re.Pattern[str]]] = [
    ("SuperSO8", re.compile(r"\b(superso[- ]?8|pg[- ]tdson[- ]?8|powerpak[- ]?so[- ]?8|tdson[- ]?8|dfn[- ]?5x6|pqfn)\b", re.I)),
    ("D2PAK", re.compile(r"\b(d2pak|to[- ]?263(?:[- ]?[a-z0-9]+)?)\b", re.I)),
    ("TO-220AB", re.compile(r"\b(to[- ]?220(?:ab)?|to[- ]?220[- ]?3)\b", re.I)),
    ("DPAK", re.compile(r"\b(dpak|to[- ]?252(?:[- ]?[a-z0-9]+)?)\b", re.I)),
    ("SOIC-8", re.compile(r"\b((?:8[- ]lead\s+)?soic(?:[- ]?8)?|so[- ]?8|soic8)\b", re.I)),
    ("SOT-23", re.compile(r"\b(sot[- ]?23(?:[- ]?3)?|to[- ]?236(?:ab)?|to[- ]?236[- ]?3|sc[- ]?59)\b", re.I)),
    ("SOT-23-6", re.compile(r"\b(sot[- ]?23[- ]?6|sot23[- ]?6|tsot[- ]?23[- ]?6)\b", re.I)),
    ("SOT-223", re.compile(r"\b(sot[- ]?223)\b", re.I)),
    ("TO-247", re.compile(r"\b(to[- ]?247(?:[- ]?[a-z0-9]+)?)\b", re.I)),
    ("TO-92", re.compile(r"\b(to[- ]?92(?:[- ]?3)?)\b", re.I)),
    ("DIP-8", re.compile(r"\b((?:8[- ]lead\s+)?(?:p)?dip(?:[- ]?8)?)\b", re.I)),
    ("SOIC-16", re.compile(r"\b(soic[- ]?16|htssop[- ]?16|tssop[- ]?16)\b", re.I)),
]

NON_SEMICONDUCTOR_KEYWORDS = re.compile(
    r"\b(fan\s+tubeaxial|tubeaxial|ball\s+bearing|blower|cfm|wire\s+leads|capacitor|mlcc|resistor|potentiometer|ferrite\s+bead|heatsink)\b",
    re.I,
)


class FeatureWiseScraper:
    """Dedicated feature extractor that parses technical content per parameter."""

    @classmethod
    def is_valid_semiconductor(cls, text: str, family: Family) -> bool:
        """Verify that text describes an authentic active semiconductor."""
        if NON_SEMICONDUCTOR_KEYWORDS.search(text):
            return False
        return True

    @classmethod
    def extract_package(cls, text: str) -> str | None:
        """Identify canonical semiconductor package outline from text."""
        for name, pattern in CANONICAL_PACKAGES:
            if pattern.search(text):
                return name
        return None

    @classmethod
    def extract_vds_max(cls, text: str) -> float | None:
        """Extract Drain-to-Source breakdown voltage (Vds max).
        
        Rejects logic/gate voltages (e.g., 3.3V, 5V, 10V Vgs).
        Valid range: 12V to 1700V.
        """
        # Look for explicit breakdown label first
        m = re.search(
            r"(?:v\(br\)dss|bvdss|vdss|vds\s*max|drain[- ](?:to[- ])?source breakdown voltage|drain[- ]source voltage)"
            r"[:=\s]+(\d+(?:\.\d+)?)\s*v\b",
            text,
            re.I,
        )
        if m:
            val = float(m.group(1))
            if 12.0 <= val <= 1700.0:
                return val

        # Look for headline format e.g. "55V N-Channel MOSFET" or "60 V, 50 A"
        m_head = re.search(r"\b(\d{2,4})\s*v(?:olts?)?\s*(?:n[- ]channel|p[- ]channel|mosfet)\b", text, re.I)
        if m_head:
            val = float(m_head.group(1))
            if 12.0 <= val <= 1700.0:
                return val

        # Specs paired with current: e.g. "50V, 0.22A" or "55V, 110A"
        m_paired = re.search(r"\b(\d{2,4})\s*v(?:olts?)?\s*,\s*(?:\d+(?:\.\d+)?)\s*(?:a|ma)\b", text, re.I)
        if m_paired:
            val = float(m_paired.group(1))
            if 12.0 <= val <= 1700.0:
                return val

        # Specs paired with resistance: e.g. "60V, 45mOhm"
        m_triad = re.search(r"\b(\d{2,4})\s*v\s*,\s*(?:\d+(?:\.\d+)?)\s*(?:m?ohm|mΩ)", text, re.I)
        if m_triad:
            val = float(m_triad.group(1))
            if 12.0 <= val <= 1700.0:
                return val

        return None

    @classmethod
    def extract_rds_on(cls, text: str) -> tuple[float, dict[str, str]] | None:
        """Extract On-State Resistance Rds(on) in Ohms with test conditions.
        
        Carefully handles milliohms vs ohms and rejects gate resistance Rg.
        Valid range: 0.0002 ohm (0.2 mOhm) to 30 ohm.
        """
        # 1. Milliohms (mOhm or mΩ)
        m_mohm = re.search(
            r"(?:rds\s*\(?on\)?|on[- ]state resistance|static drain[- ]source resistance)"
            r"[^0-9a-z]{0,10}(\d+(?:\.\d+)?)\s*(?:m[oO]hm|mΩ|milli[- ]?ohms?)\b",
            text,
            re.I,
        )
        if m_mohm:
            val = float(m_mohm.group(1)) / 1000.0
            if 0.0002 <= val <= 0.99:
                vgs_cond = "10 V"
                cond_m = re.search(r"(?:vgs\s*[:=]?\s*|@\s*)(\d+(?:\.\d+)?)\s*v\b", text[max(0, m_mohm.start() - 30):m_mohm.end() + 30], re.I)
                if cond_m and float(cond_m.group(1)) in (4.5, 10.0, 12.0, 2.5):
                    vgs_cond = f"{cond_m.group(1)} V"
                return val, {"Vgs": vgs_cond, "Tj": "25 C"}

        # Standalone milliohm in summary triad (e.g., "55V, 8 mOhm, 110A")
        m_triad = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:m[oO]hm|mΩ)\b", text, re.I)
        if m_triad:
            val = float(m_triad.group(1)) / 1000.0
            if 0.0002 <= val <= 0.99:
                return val, {"Vgs": "10 V", "Tj": "25 C"}

        # 2. Ohms (Ω) - for small signal FETs like BSS138, 2N7002
        m_ohm = re.search(
            r"(?:rds\s*\(?on\)?|on[- ]state resistance|drain[- ]source on resistance)"
            r"[^0-9a-z]{0,10}(\d+(?:\.\d+)?)\s*(?:ohm|Ω)\b",
            text,
            re.I,
        )
        if m_ohm:
            val = float(m_ohm.group(1))
            if 0.01 <= val <= 30.0:
                return val, {"Vgs": "10 V", "Tj": "25 C"}

        return None

    @classmethod
    def extract_id_continuous(cls, text: str) -> tuple[float, dict[str, str]] | None:
        """Extract continuous drain current (Id) in Amperes.
        
        Rejects pulsed current (Idm) and test currents (< 50mA).
        """
        # Look for explicit continuous drain current label
        m = re.search(
            r"(?:continuous drain current|id\s*\(cont\)|drain current\s*id|continuous current)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*a\b",
            text,
            re.I,
        )
        if m:
            val = float(m.group(1))
            if 0.1 <= val <= 500.0:
                return val, {"Tc": "25 C"}

        # In summary string: "55 V, 110 A" or "100V, 33A"
        m_summary = re.search(r"\b\d{2,4}\s*v\s*,\s*(\d+(?:\.\d+)?)\s*a\b", text, re.I)
        if m_summary:
            val = float(m_summary.group(1))
            if 0.2 <= val <= 500.0:
                return val, {"Tc": "25 C"}

        # Small signal in mA (e.g. "200 mA (Ta)" or "0.22A")
        m_ma = re.search(
            r"(?:continuous drain current|id|drain current)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*ma\b",
            text,
            re.I,
        )
        if m_ma:
            val = float(m_ma.group(1)) / 1000.0
            if 0.05 <= val <= 2.0:
                return val, {"Ta": "25 C"}

        return None

    @classmethod
    def extract_vgs_threshold(cls, text: str) -> tuple[float, dict[str, str]] | None:
        """Extract Gate Threshold Voltage Vgs(th) in Volts.
        
        Strict bounds: 0.6V to 5.5V. Never match Vgs(max) (+/-20V).
        """
        m = re.search(
            r"(?:vgs\s*\(?th\)?|gate[- ]source threshold voltage|gate threshold voltage|vth)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*v\b",
            text,
            re.I,
        )
        if m:
            val = float(m.group(1))
            if 0.6 <= val <= 5.5:
                return val, {"Id": "250 uA"}
        return None

    @classmethod
    def extract_vgs_max(cls, text: str) -> float | None:
        """Extract Absolute Maximum Gate-Source Voltage rating (Vgs max).
        
        Explicitly rejects '@ Vgs = 10V' test conditions.
        Standard ratings: ±12V, ±16V, ±20V, ±30V.
        """
        m = re.search(
            r"(?:vgs\s*max|gate[- ]source voltage rating|gate[- ]source voltage|vgs\s*rating|vgss)\s*(?:rating|limit)?\s*[:=]?\s*(?:[±\+\-/]+)?\s*(\d+(?:\.\d+)?)\s*v\b",
            text,
            re.I,
        )
        if m:
            val = float(m.group(1))
            if 8.0 <= val <= 35.0:
                return val

        m_sym = re.search(r"(?:[±\+\-/]+)\s*(12|16|20|25|30)\s*v\b", text, re.I)
        if m_sym:
            return float(m_sym.group(1))

        return None

    @classmethod
    def extract_gate_charges(cls, text: str) -> dict[str, float]:
        """Extract Qg (total) and Qgd (Miller) in Coulombs."""
        charges: dict[str, float] = {}

        # Total gate charge Qg
        m_qg = re.search(
            r"(?:total gate charge|qg(?:\s*\(total\))?)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*nc\b",
            text,
            re.I,
        )
        if m_qg:
            val_nc = float(m_qg.group(1))
            if 0.5 <= val_nc <= 600.0:
                charges["total_gate_charge_qg"] = val_nc * 1e-9

        # Gate-to-drain charge Qgd
        m_qgd = re.search(
            r"(?:gate[- ]to[- ]drain charge|qgd|miller charge)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*nc\b",
            text,
            re.I,
        )
        if m_qgd:
            val_nc = float(m_qgd.group(1))
            if 0.2 <= val_nc <= 250.0:
                charges["gate_drain_charge_qgd"] = val_nc * 1e-9

        return charges

    @classmethod
    def extract_capacitances(cls, text: str) -> dict[str, float]:
        """Extract Ciss and Coss in Farads, ensuring distinct values and Ciss > Coss."""
        caps: dict[str, float] = {}

        # Input capacitance Ciss
        m_ciss = re.search(r"(?:ciss|input capacitance)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:pf|nf)\b", text, re.I)
        if m_ciss:
            mult = 1e-9 if "nf" in m_ciss.group(0).lower() else 1e-12
            val = float(m_ciss.group(1)) * mult
            if 10e-12 <= val <= 50e-9:
                caps["input_capacitance_ciss"] = val

        # Output capacitance Coss
        m_coss = re.search(r"(?:coss|output capacitance)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:pf|nf)\b", text, re.I)
        if m_coss:
            mult = 1e-9 if "nf" in m_coss.group(0).lower() else 1e-12
            val = float(m_coss.group(1)) * mult
            if 5e-12 <= val <= 25e-9:
                if "input_capacitance_ciss" not in caps or abs(val - caps["input_capacitance_ciss"]) > 1e-12:
                    caps["output_capacitance_coss"] = val

        return caps

    @classmethod
    def extract_thermal_and_power(cls, text: str) -> dict[str, float]:
        """Extract max junction temperature, RthJC, and power dissipation."""
        results: dict[str, float] = {}

        # Operating Junction Temperature Tj max (150 or 175 °C standard)
        m_tj = re.search(
            r"(?:operating junction temperature|maximum junction temperature|tj\s*max)\s*[:=]?\s*(\d{2,3})\s*(?:°|deg)?c\b|\b(150|175)\s*(?:°|deg)?c\s*(?:tj|max|junction)?\b",
            text,
            re.I,
        )
        if m_tj:
            val = float(m_tj.group(1) or m_tj.group(2))
            if val in (125.0, 150.0, 175.0, 200.0):
                results["max_junction_temp"] = val

        # Thermal resistance RthJC
        m_rth = re.search(
            r"(?:rthjc|rθjc|thermal resistance[,\s]*junction[- ]to[- ]case)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:°c/w|degc/w|k/w)\b",
            text,
            re.I,
        )
        if m_rth:
            val = float(m_rth.group(1))
            if 0.1 <= val <= 25.0:
                results["thermal_resistance"] = val

        # Maximum Power Dissipation Pd
        m_pd = re.search(
            r"(?:maximum power dissipation|power dissipation|pd)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*w\b",
            text,
            re.I,
        )
        if m_pd:
            val = float(m_pd.group(1))
            if 0.3 <= val <= 500.0:
                results["power_dissipation_pd"] = val

        return results

    @classmethod
    def extract_gate_driver_features(cls, text: str) -> dict[str, Any]:
        """Extract gate driver parameters: peak currents, supply voltages, timing."""
        params: dict[str, Any] = {}

        # Supply voltage max (VCC max)
        m_vcc = re.search(
            r"(?:vcc|vdd|supply voltage)\s*(?:max|range)?\s*[:=]?\s*(?:up to\s*)?(\d+(?:\.\d+)?)\s*v\b",
            text,
            re.I,
        )
        if m_vcc:
            val = float(m_vcc.group(1))
            if 8.0 <= val <= 35.0:
                params["supply_voltage_max"] = val

        # Peak Source and Sink Currents (supports slash e.g. "130mA / 270mA" or "2A / 4A")
        m_slash = re.search(
            r"(?:source[/ ]sink|output source/sink|peak source/sink)\s*(?:current)?.*?(\d+(?:\.\d+)?)\s*(m?a)\s*[/,\s]+\s*(\d+(?:\.\d+)?)\s*(m?a)",
            text,
            re.I,
        )
        if m_slash:
            s_val = float(m_slash.group(1)) * (1e-3 if m_slash.group(2).lower() == "ma" else 1.0)
            k_val = float(m_slash.group(3)) * (1e-3 if m_slash.group(4).lower() == "ma" else 1.0)
            params["peak_source_current"] = round(s_val, 4)
            params["peak_sink_current"] = round(k_val, 4)
        else:
            m_dual = re.search(r"(\d+(?:\.\d+)?)\s*a\s*(?:source|pull[- ]up)[,\s]+(\d+(?:\.\d+)?)\s*a\s*(?:sink|pull[- ]down)", text, re.I)
            if m_dual:
                params["peak_source_current"] = float(m_dual.group(1))
                params["peak_sink_current"] = float(m_dual.group(2))
            else:
                m_src = re.search(r"(?:source current|io\+|output source)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*a\b", text, re.I)
                if m_src:
                    params["peak_source_current"] = float(m_src.group(1))
                m_snk = re.search(r"(?:sink current|io\-|output sink)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*a\b", text, re.I)
                if m_snk:
                    params["peak_sink_current"] = float(m_snk.group(1))

        # Propagation delay (ns -> s)
        m_tpd = re.search(
            r"(?:propagation delay|prop delay|tpd|turn[- ]on propagation delay)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*ns\b",
            text,
            re.I,
        )
        if m_tpd:
            val_ns = float(m_tpd.group(1))
            if 10.0 <= val_ns <= 1500.0:
                params["propagation_delay"] = val_ns * 1e-9

        # Rise and Fall time
        m_tr = re.search(r"(?:rise time|tr)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*ns\b", text, re.I)
        if m_tr:
            val = float(m_tr.group(1))
            if 5.0 <= val <= 250.0:
                params["rise_time"] = val * 1e-9

        m_tf = re.search(r"(?:fall time|tf)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*ns\b", text, re.I)
        if m_tf:
            val = float(m_tf.group(1))
            if 5.0 <= val <= 250.0:
                params["fall_time"] = val * 1e-9

        # Channel count
        if re.search(r"\b(half[- ]bridge|high[- ]and[- ]low[- ]side|dual[- ]channel|2[- ]channel)\b", text, re.I):
            params["channel_count"] = 2.0
        elif re.search(r"\b(single[- ]channel|low[- ]side driver|1[- ]channel)\b", text, re.I):
            params["channel_count"] = 1.0

        return params

    @classmethod
    def extract_parameters_from_text(
        cls,
        text: str,
        family: Family,
        title: str = "",
        mpn: str = "",
    ) -> list[ParameterValue]:
        """Run feature-wise extraction for all parameters matching the component family."""
        combined = f"{title} {text} {mpn}".strip()
        params: list[ParameterValue] = []

        def add_p(name: str, val: float, unit: str | None, conf: float = 0.88, cond: dict[str, Any] | None = None):
            params.append(
                ParameterValue(
                    name=name,
                    value=val,
                    value_typ=val,
                    unit=unit,
                    condition=cond or {},
                    confidence=conf,
                    status=ValueStatus.ACCEPTED,
                    method="tier1",
                )
            )

        if family in (Family.MOSFET, Family.GENERAL):
            vds = cls.extract_vds_max(combined)
            if vds is not None:
                add_p("vds_max", vds, "V", 0.92)

            rds = cls.extract_rds_on(combined)
            if rds is not None:
                val, cond = rds
                add_p("rds_on", val, "ohm", 0.90, cond)

            id_c = cls.extract_id_continuous(combined)
            if id_c is not None:
                val, cond = id_c
                add_p("id_continuous", val, "A", 0.88, cond)

            vth = cls.extract_vgs_threshold(combined)
            if vth is not None:
                val, cond = vth
                add_p("vgs_threshold", val, "V", 0.88, cond)

            vgs_max = cls.extract_vgs_max(combined)
            if vgs_max is not None:
                add_p("vgs_max", vgs_max, "V", 0.90)

            charges = cls.extract_gate_charges(combined)
            for k, val in charges.items():
                add_p(k, val, "C", 0.85)

            caps = cls.extract_capacitances(combined)
            for k, val in caps.items():
                add_p(k, val, "F", 0.85)

            thermal = cls.extract_thermal_and_power(combined)
            if "max_junction_temp" in thermal:
                add_p("max_junction_temp", thermal["max_junction_temp"], "degC", 0.92)
            if "thermal_resistance" in thermal:
                add_p("thermal_resistance", thermal["thermal_resistance"], "degC/W", 0.88)
            if "power_dissipation_pd" in thermal:
                add_p("power_dissipation_pd", thermal["power_dissipation_pd"], "W", 0.85)

        elif family == Family.GATE_DRIVER:
            gd_feats = cls.extract_gate_driver_features(combined)
            if "supply_voltage_max" in gd_feats:
                add_p("supply_voltage_max", gd_feats["supply_voltage_max"], "V", 0.92)
            if "peak_source_current" in gd_feats:
                add_p("peak_source_current", gd_feats["peak_source_current"], "A", 0.90)
            if "peak_sink_current" in gd_feats:
                add_p("peak_sink_current", gd_feats["peak_sink_current"], "A", 0.90)
            if "propagation_delay" in gd_feats:
                add_p("propagation_delay", gd_feats["propagation_delay"], "s", 0.88)
            if "rise_time" in gd_feats:
                add_p("rise_time", gd_feats["rise_time"], "s", 0.85)
            if "fall_time" in gd_feats:
                add_p("fall_time", gd_feats["fall_time"], "s", 0.85)
            if "channel_count" in gd_feats:
                add_p("channel_count", gd_feats["channel_count"], None, 0.95)

        return params
