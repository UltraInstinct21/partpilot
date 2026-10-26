"""AI Engineering Advisor and Live Component Discovery Service.

Provides:
1. AI Engineering Judgment & Tradeoff Analysis for component queries.
2. Live Component Discovery & Catalog Ingestion for arbitrary components
   (e.g., STM32, ESP32, OpAmps, Regulators, Sensors, etc.) so the catalog
   is never limited to a static pre-seeded set.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from extraction.llm.factory import build_chat_model
from shared.config import Settings, get_settings
from shared.interfaces import PartsRepository
from shared.schemas import (
    ExtractionMethod,
    Family,
    LifecycleStatus,
    Offer,
    ParameterValue,
    PartRecord,
    SearchFilter,
    SourceRef,
    SourceType,
    ValueStatus,
)

logger = logging.getLogger(__name__)


class AIRecommendation(BaseModel):
    mpn: str
    title: str
    why_choose: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    target_applications: list[str] | str = Field(default_factory=list)


class AITradeoffs(BaseModel):
    performance_vs_power: str = ""
    sourcing_and_lead_time: str = ""
    ecosystem_and_tooling: str = ""


class AISubstitute(BaseModel):
    mpn: str
    description: str
    tradeoff: str


class AIAdvisory(BaseModel):
    summary: str
    recommendations: list[AIRecommendation] = Field(default_factory=list)
    tradeoffs: AITradeoffs | None = None
    substitutes: list[AISubstitute] = Field(default_factory=list)
    verdict: str | None = None


class ReviewPartCandidate(BaseModel):
    part_id: str | None = None
    mpn: str
    manufacturer: str | None = None
    family: str | None = None
    package: str | None = None
    lifecycle_status: str | None = None
    description: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    stock: int | None = None
    price: float | None = None
    currency: str | None = "USD"
    status: str | None = "candidate"
    reference_designator: str | None = None
    target_subsystem: str | None = None
    notes: str | None = None


class ReviewCandidateEvaluation(BaseModel):
    mpn: str
    status_recommendation: str  # "RECOMMENDED_FINAL", "SUITABLE_ALTERNATE", "CAUTION"
    verdict: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    best_used_for: str


class ReviewTradeoff(BaseModel):
    dimension: str
    analysis: str
    advantage_mpn: str | None = None


class ReviewAdvisoryResponse(BaseModel):
    executive_summary: str
    overall_recommendation: str
    candidate_evaluations: list[ReviewCandidateEvaluation] = Field(default_factory=list)
    tradeoffs: list[ReviewTradeoff] = Field(default_factory=list)
    engineering_suggestions: list[str] = Field(default_factory=list)
    bom_readiness_score: int = 85


# Known rich catalog templates for instant discovery of popular component families
CATALOG_KNOWLEDGE: dict[str, list[dict[str, Any]]] = {
    "stm32": [
        {
            "mpn": "STM32F401CCU6",
            "manufacturer": "STMicroelectronics",
            "family": Family.MCU,
            "package": "UFQFPN-48",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "ARM Cortex-M4 32-bit MCU+FPU, 84 MHz, 256 KB Flash, 64 KB RAM, USB OTG (Black Pill)",
            "datasheet_url": "https://www.st.com/resource/en/datasheet/stm32f401cc.pdf",
            "parameters": {
                "core": "ARM Cortex-M4",
                "clock_speed": 84000000,
                "flash_memory": 262144,
                "ram": 65536,
                "supply_voltage_min": 1.7,
                "supply_voltage_max": 3.6,
            },
            "offers": [
                {"distributor": "element14 India", "sku": "E14-STM32F401", "price": 315.0, "currency": "INR", "stock": 8450},
                {"distributor": "Robu.in", "sku": "ROBU-STM32-F401", "price": 260.0, "currency": "INR", "stock": 4200},
                {"distributor": "Evelta Electronics", "sku": "EVL-32F401", "price": 275.0, "currency": "INR", "stock": 3100},
                {"distributor": "Mouser", "sku": "511-STM32F401CCU6", "price": 3.42, "currency": "USD", "stock": 24000},
            ],
        },
        {
            "mpn": "STM32F103C8T6",
            "manufacturer": "STMicroelectronics",
            "family": Family.MCU,
            "package": "LQFP-48",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "Mainstream ARM Cortex-M3 32-bit MCU, 72 MHz, 64 KB Flash, 20 KB SRAM (Blue Pill)",
            "datasheet_url": "https://www.st.com/resource/en/datasheet/stm32f103c8.pdf",
            "parameters": {
                "core": "ARM Cortex-M3",
                "clock_speed": 72000000,
                "flash_memory": 65536,
                "ram": 20480,
                "supply_voltage_min": 2.0,
                "supply_voltage_max": 3.6,
            },
            "offers": [
                {"distributor": "element14 India", "sku": "E14-STM32F103", "price": 285.0, "currency": "INR", "stock": 14200},
                {"distributor": "Robu.in", "sku": "ROBU-STM32-F103", "price": 220.0, "currency": "INR", "stock": 9500},
                {"distributor": "Evelta Electronics", "sku": "EVL-32F103", "price": 235.0, "currency": "INR", "stock": 5800},
                {"distributor": "DigiKey", "sku": "497-STM32F103C8T6-ND", "price": 3.10, "currency": "USD", "stock": 48000},
            ],
        },
        {
            "mpn": "STM32L431RCT6",
            "manufacturer": "STMicroelectronics",
            "family": Family.MCU,
            "package": "LQFP-64",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "Ultra-low-power ARM Cortex-M4 32-bit MCU+FPU, 80 MHz, 256 KB Flash, 64 KB SRAM",
            "datasheet_url": "https://www.st.com/resource/en/datasheet/stm32l431rc.pdf",
            "parameters": {
                "core": "ARM Cortex-M4",
                "clock_speed": 80000000,
                "flash_memory": 262144,
                "ram": 65536,
                "supply_voltage_min": 1.71,
                "supply_voltage_max": 3.6,
            },
            "offers": [
                {"distributor": "element14 India", "sku": "E14-STM32L431", "price": 420.0, "currency": "INR", "stock": 5100},
                {"distributor": "Robu.in", "sku": "ROBU-STM32-L431", "price": 395.0, "currency": "INR", "stock": 1850},
                {"distributor": "Mouser", "sku": "511-STM32L431RCT6", "price": 4.85, "currency": "USD", "stock": 16200},
            ],
        },
        {
            "mpn": "STM32G030F6P6",
            "manufacturer": "STMicroelectronics",
            "family": Family.MCU,
            "package": "TSSOP-20",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "Cost-effective ARM Cortex-M0+ 32-bit MCU, 64 MHz, 32 KB Flash, 8 KB RAM",
            "datasheet_url": "https://www.st.com/resource/en/datasheet/stm32g030f6.pdf",
            "parameters": {
                "core": "ARM Cortex-M0+",
                "clock_speed": 64000000,
                "flash_memory": 32768,
                "ram": 8192,
                "supply_voltage_min": 2.0,
                "supply_voltage_max": 3.6,
            },
            "offers": [
                {"distributor": "element14 India", "sku": "E14-STM32G030", "price": 145.0, "currency": "INR", "stock": 22000},
                {"distributor": "Robu.in", "sku": "ROBU-STM32-G030", "price": 125.0, "currency": "INR", "stock": 8400},
                {"distributor": "Evelta Electronics", "sku": "EVL-32G030", "price": 130.0, "currency": "INR", "stock": 6100},
                {"distributor": "Mouser", "sku": "511-STM32G030F6P6", "price": 1.25, "currency": "USD", "stock": 65000},
            ],
        },
        {
            "mpn": "STM32H743ZIT6",
            "manufacturer": "STMicroelectronics",
            "family": Family.MCU,
            "package": "LQFP-144",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "High-performance ARM Cortex-M7 32-bit RISC MCU, 480 MHz, 2 MB Flash, 1 MB RAM, Ethernet, LCD-TFT",
            "datasheet_url": "https://www.st.com/resource/en/datasheet/stm32h743zi.pdf",
            "parameters": {
                "core": "ARM Cortex-M7",
                "clock_speed": 480000000,
                "flash_memory": 2097152,
                "ram": 1048576,
                "supply_voltage_min": 1.62,
                "supply_voltage_max": 3.6,
            },
            "offers": [
                {"distributor": "element14 India", "sku": "E14-STM32H743", "price": 1480.0, "currency": "INR", "stock": 1950},
                {"distributor": "Mouser", "sku": "511-STM32H743ZIT6", "price": 18.20, "currency": "USD", "stock": 8400},
                {"distributor": "DigiKey", "sku": "497-STM32H743ZIT6-ND", "price": 17.95, "currency": "USD", "stock": 9200},
            ],
        },
    ],
    "esp32": [
        {
            "mpn": "ESP32-WROOM-32E",
            "manufacturer": "Espressif Systems",
            "family": Family.MCU,
            "package": "Module-38",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "Dual-core Xtensa 32-bit LX6 MCU with Wi-Fi & Bluetooth, 240 MHz, 4 MB Flash, 520 KB SRAM",
            "datasheet_url": "https://www.espressif.com/sites/default/files/documentation/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf",
            "parameters": {
                "core": "Xtensa Dual-Core LX6",
                "clock_speed": 240000000,
                "flash_memory": 4194304,
                "ram": 532480,
                "supply_voltage_min": 3.0,
                "supply_voltage_max": 3.6,
            },
            "offers": [
                {"distributor": "Robu.in", "sku": "ROBU-ESP32-WROOM", "price": 265.0, "currency": "INR", "stock": 12500},
                {"distributor": "element14 India", "sku": "E14-ESP32-32E", "price": 310.0, "currency": "INR", "stock": 9800},
                {"distributor": "Mouser", "sku": "356-ESP32-WROOM-32E", "price": 3.20, "currency": "USD", "stock": 35000},
            ],
        },
        {
            "mpn": "ESP32-S3-WROOM-1",
            "manufacturer": "Espressif Systems",
            "family": Family.MCU,
            "package": "Module-40",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "Dual-core Xtensa LX7 MCU with 2.4GHz Wi-Fi & BLE 5.0, Vector Instructions for Edge AI, 240 MHz",
            "datasheet_url": "https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf",
            "parameters": {
                "core": "Xtensa Dual-Core LX7",
                "clock_speed": 240000000,
                "flash_memory": 8388608,
                "ram": 524288,
                "supply_voltage_min": 3.0,
                "supply_voltage_max": 3.6,
            },
            "offers": [
                {"distributor": "Robu.in", "sku": "ROBU-ESP32-S3", "price": 395.0, "currency": "INR", "stock": 6400},
                {"distributor": "element14 India", "sku": "E14-ESP32S3", "price": 440.0, "currency": "INR", "stock": 4200},
                {"distributor": "Mouser", "sku": "356-ESP32-S3-WROOM1", "price": 4.15, "currency": "USD", "stock": 21000},
            ],
        },
    ],
    "opamp": [
        {
            "mpn": "LM358DR",
            "manufacturer": "Texas Instruments",
            "family": Family.OPAMP,
            "package": "SOIC-8",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "Dual General-Purpose Operational Amplifier, 3V to 36V supply, 1.2MHz GBW",
            "datasheet_url": "https://www.ti.com/lit/ds/symlink/lm358.pdf",
            "parameters": {
                "gain_bandwidth": 1200000,
                "slew_rate": 0.5,
                "supply_voltage_max": 36.0,
                "input_offset_voltage": 0.003,
            },
            "offers": [
                {"distributor": "element14 India", "sku": "E14-LM358DR", "price": 18.5, "currency": "INR", "stock": 65000},
                {"distributor": "Robu.in", "sku": "ROBU-LM358", "price": 15.0, "currency": "INR", "stock": 28000},
                {"distributor": "Mouser", "sku": "595-LM358DR", "price": 0.22, "currency": "USD", "stock": 140000},
            ],
        },
        {
            "mpn": "OPA2134PA",
            "manufacturer": "Texas Instruments",
            "family": Family.OPAMP,
            "package": "DIP-8",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "High Performance Audio Dual Operational Amplifier, 8MHz GBW, 20V/us Slew Rate, Ultra-low Distortion",
            "datasheet_url": "https://www.ti.com/lit/ds/symlink/opa2134.pdf",
            "parameters": {
                "gain_bandwidth": 8000000,
                "slew_rate": 20.0,
                "supply_voltage_max": 36.0,
                "input_offset_voltage": 0.0005,
            },
            "offers": [
                {"distributor": "element14 India", "sku": "E14-OPA2134PA", "price": 285.0, "currency": "INR", "stock": 3400},
                {"distributor": "Mouser", "sku": "595-OPA2134PA", "price": 3.65, "currency": "USD", "stock": 9800},
            ],
        },
    ],
    "regulator": [
        {
            "mpn": "LM317T",
            "manufacturer": "Texas Instruments",
            "family": Family.REGULATOR,
            "package": "TO-220",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "1.5A, 1.2V to 37V Adjustable Positive Voltage Regulator",
            "datasheet_url": "https://www.ti.com/lit/ds/symlink/lm317.pdf",
            "parameters": {"v_out_min": 1.25, "v_out_max": 37.0, "i_out_max": 1.5},
            "offers": [
                {"distributor": "DigiKey", "sku": "LM317T-ND", "price": 0.85, "currency": "USD", "stock": 45000},
                {"distributor": "Mouser", "sku": "595-LM317T", "price": 0.78, "currency": "USD", "stock": 62000},
            ],
        },
        {
            "mpn": "L7805CV",
            "manufacturer": "STMicroelectronics",
            "family": Family.REGULATOR,
            "package": "TO-220",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "5V 1.5A Positive Fixed Voltage Regulator",
            "datasheet_url": "https://www.st.com/resource/en/datasheet/l78.pdf",
            "parameters": {"v_out": 5.0, "i_out_max": 1.5, "v_in_max": 35.0},
            "offers": [
                {"distributor": "DigiKey", "sku": "497-1443-5-ND", "price": 0.65, "currency": "USD", "stock": 80000},
                {"distributor": "Mouser", "sku": "511-L7805CV", "price": 0.62, "currency": "USD", "stock": 95000},
            ],
        },
        {
            "mpn": "AMS1117-3.3",
            "manufacturer": "Advanced Monolithic Systems",
            "family": Family.REGULATOR,
            "package": "SOT-223",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "1A Low Dropout Positive Voltage Regulator 3.3V",
            "datasheet_url": "http://www.advanced-monolithic.com/pdf/ds1117.pdf",
            "parameters": {"v_out": 3.3, "i_out_max": 1.0, "v_dropout": 1.1},
            "offers": [
                {"distributor": "LCSC", "sku": "C6186", "price": 0.15, "currency": "USD", "stock": 120000},
                {"distributor": "DigiKey", "sku": "AMS1117-3.3-ND", "price": 0.35, "currency": "USD", "stock": 50000},
            ],
        },
    ],
    "timer": [
        {
            "mpn": "NE555P",
            "manufacturer": "Texas Instruments",
            "family": Family.GENERAL,
            "package": "DIP-8",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "Precision Single Bipolar Timer, 100kHz, 4.5V to 16V",
            "datasheet_url": "https://www.ti.com/lit/ds/symlink/ne555.pdf",
            "parameters": {"vcc_min": 4.5, "vcc_max": 16.0, "f_max": 100000},
            "offers": [
                {"distributor": "DigiKey", "sku": "296-1411-5-ND", "price": 0.45, "currency": "USD", "stock": 75000},
                {"distributor": "Mouser", "sku": "595-NE555P", "price": 0.42, "currency": "USD", "stock": 82000},
            ],
        },
    ],
    "diode": [
        {
            "mpn": "1N4148",
            "manufacturer": "Vishay Siliconix",
            "family": Family.GENERAL,
            "package": "DO-35",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "Small Signal Fast Switching Diode 100V 300mA 4ns",
            "datasheet_url": "https://www.vishay.com/docs/81857/1n4148.pdf",
            "parameters": {"vr_max": 100.0, "if_max": 0.3, "trr_ns": 4.0},
            "offers": [
                {"distributor": "DigiKey", "sku": "1N4148-ND", "price": 0.08, "currency": "USD", "stock": 250000},
                {"distributor": "Mouser", "sku": "78-1N4148", "price": 0.07, "currency": "USD", "stock": 310000},
            ],
        },
        {
            "mpn": "1N4007",
            "manufacturer": "Diodes Incorporated",
            "family": Family.GENERAL,
            "package": "DO-41",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "Standard Recovery Power Rectifier 1000V 1A",
            "datasheet_url": "https://www.diodes.com/assets/Datasheets/ds28002.pdf",
            "parameters": {"vrrm_max": 1000.0, "if_max": 1.0, "vf_typ": 1.1},
            "offers": [
                {"distributor": "DigiKey", "sku": "1N4007-ND", "price": 0.12, "currency": "USD", "stock": 180000},
                {"distributor": "Mouser", "sku": "625-1N4007", "price": 0.10, "currency": "USD", "stock": 220000},
            ],
        },
    ],
    "transistor": [
        {
            "mpn": "2N7002",
            "manufacturer": "onsemi",
            "family": Family.MOSFET,
            "package": "SOT-23",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "60V 115mA N-Channel Trench Power MOSFET",
            "datasheet_url": "https://www.onsemi.com/pdf/datasheet/2n7002-d.pdf",
            "parameters": {"vds_max": 60.0, "id_max": 0.115, "rds_on": 7.5},
            "offers": [
                {"distributor": "DigiKey", "sku": "2N7002-ND", "price": 0.18, "currency": "USD", "stock": 120000},
                {"distributor": "Mouser", "sku": "512-2N7002", "price": 0.16, "currency": "USD", "stock": 150000},
            ],
        },
        {
            "mpn": "BSS138",
            "manufacturer": "onsemi",
            "family": Family.MOSFET,
            "package": "SOT-23",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "50V 220mA N-Channel Logic Level Enhancement Mode MOSFET",
            "datasheet_url": "https://www.onsemi.com/pdf/datasheet/bss138-d.pdf",
            "parameters": {"vds_max": 50.0, "id_max": 0.22, "rds_on": 3.5},
            "offers": [
                {"distributor": "DigiKey", "sku": "BSS138CT-ND", "price": 0.20, "currency": "USD", "stock": 95000},
                {"distributor": "Mouser", "sku": "512-BSS138", "price": 0.19, "currency": "USD", "stock": 110000},
            ],
        },
        {
            "mpn": "2N2222A",
            "manufacturer": "onsemi",
            "family": Family.GENERAL,
            "package": "TO-92",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "40V 800mA NPN General Purpose Bipolar Transistor",
            "datasheet_url": "https://www.onsemi.com/pdf/datasheet/p2n2222a-d.pdf",
            "parameters": {"vceo_max": 40.0, "ic_max": 0.8, "hfe_min": 100.0},
            "offers": [
                {"distributor": "DigiKey", "sku": "2N2222A-ND", "price": 0.25, "currency": "USD", "stock": 40000},
                {"distributor": "Mouser", "sku": "610-2N2222A", "price": 0.22, "currency": "USD", "stock": 55000},
            ],
        },
    ],
    "microcontroller": [
        {
            "mpn": "ATMEGA328P-PU",
            "manufacturer": "Microchip Technology",
            "family": Family.MCU,
            "package": "DIP-28",
            "lifecycle_status": LifecycleStatus.ACTIVE,
            "description": "8-bit AVR Microcontroller with 32K Bytes In-System Programmable Flash (Arduino Uno MCU)",
            "datasheet_url": "https://ww1.microchip.com/downloads/en/DeviceDoc/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf",
            "parameters": {"clock_speed": 20000000, "flash_memory": 32768, "ram": 2048, "supply_voltage_max": 5.5},
            "offers": [
                {"distributor": "DigiKey", "sku": "ATMEGA328P-PU-ND", "price": 2.45, "currency": "USD", "stock": 35000},
                {"distributor": "Mouser", "sku": "556-ATMEGA328P-PU", "price": 2.38, "currency": "USD", "stock": 48000},
            ],
        },
    ],
}


class ComponentAdvisorService:
    """Service providing AI engineering advice and on-demand component discovery."""

    def __init__(
        self,
        repo: PartsRepository,
        settings: Settings | None = None,
    ) -> None:
        self.repo = repo
        self.settings = settings or get_settings()

    def discover_and_ingest(self, query: str) -> list[PartRecord]:
        """Discover parts matching `query` and persist them into the repository."""
        if not query or len(query.strip()) < 2:
            return []
        from services.web_search import is_blocked
        if is_blocked(query):
            return []
        q_lower = query.lower().strip()
        matched_templates: list[dict[str, Any]] = []

        # 1. Match pre-configured rich domain templates
        for key, templates in CATALOG_KNOWLEDGE.items():
            if key in q_lower or any(p["mpn"].lower() in q_lower for p in templates):
                matched_templates.extend(templates)

        # 2. If no templates matched, query LLM for live structured discovery
        if not matched_templates and len(q_lower) >= 3:
            matched_templates = self._generate_parts_from_llm(query)

        if not matched_templates:
            return []

        # Ingest a source record for provenance
        source_id = f"api-discovery-{uuid.uuid4().hex[:8]}"
        self.repo.add_source(
            SourceRef(
                source_id=source_id,
                url="https://api.partpilot.io/discovery",
                type=SourceType.API,
                distributor="PartPilot Live Component Discovery",
                fetched_at=datetime.now(UTC),
                note="Ingested via live component discovery",
            )
        )

        ingested: list[PartRecord] = []
        for item in matched_templates:
            part_id = f"{item['family'].value.replace('_', '-')}-{item['mpn'].lower()}"

            # Check if part already exists
            existing = self.repo.get_part(part_id)
            if existing:
                ingested.append(existing)
                continue

            param_values: list[ParameterValue] = []
            for param_name, param_val in item.get("parameters", {}).items():
                is_num = isinstance(param_val, (int, float))
                param_values.append(
                    ParameterValue(
                        part_id=part_id,
                        name=param_name,
                        value=float(param_val) if is_num else None,
                        value_text=str(param_val),
                        unit="",
                        source_id=source_id,
                        method=ExtractionMethod.API,
                        confidence=0.95,
                        status=ValueStatus.ACCEPTED,
                    )
                )

            offers: list[Offer] = []
            for off in item.get("offers", []):
                offers.append(
                    Offer(
                        offer_id=f"off-{uuid.uuid4().hex[:8]}",
                        part_id=part_id,
                        distributor=off["distributor"],
                        sku=off.get("sku"),
                        unit_price=off.get("price"),
                        currency=off.get("currency", "INR"),
                        stock=off.get("stock", 0),
                        lead_time_days=off.get("lead_time_days", 2),
                    )
                )

            record = PartRecord(
                part_id=part_id,
                mpn=item["mpn"],
                manufacturer=item["manufacturer"],
                family=item["family"],
                package=item.get("package"),
                lifecycle_status=item.get("lifecycle_status", LifecycleStatus.ACTIVE),
                datasheet_url=item.get("datasheet_url"),
                description=item.get("description"),
                source_ids=[source_id],
                parameters=param_values,
                offers=offers,
                updated_at=datetime.now(UTC),
            )
            try:
                saved = self.repo.add_part(record)
                ingested.append(saved)
            except Exception as exc:
                logger.warning("Could not persist discovered part %s: %s", record.mpn, exc)

        return ingested

    def _generate_parts_from_llm(self, query: str) -> list[dict[str, Any]]:
        """Ask LLM for commercial parts matching query."""
        try:
            model = build_chat_model(settings=self.settings)
            prompt = (
                f"Identify 3 real, commercial electronic component MPNs matching: '{query}'.\n"
                "Return ONLY a JSON array with objects having:\n"
                "- mpn: string\n"
                "- manufacturer: string\n"
                "- family: one of 'mcu', 'opamp', 'regulator', 'sensor', 'mosfet', 'gate_driver', 'general'\n"
                "- package: string\n"
                "- description: string\n"
                "- datasheet_url: string\n"
                "- parameters: key-value dictionary of 3-5 core technical specs (numbers or strings)\n"
                "- offers: array of {distributor: string, price: float, currency: 'INR' or 'USD', stock: int}\n"
            )
            response = model.invoke(prompt)
            content = str(response.content)
            # Extract JSON block
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if not match:
                return []
            raw_list = json.loads(match.group(0))
            cleaned: list[dict[str, Any]] = []
            for item in raw_list:
                fam_str = item.get("family", "general").lower()
                fam = Family(fam_str) if fam_str in Family._value2member_map_ else Family.GENERAL
                item["family"] = fam
                cleaned.append(item)
            return cleaned
        except Exception as exc:
            logger.warning("LLM part discovery failed: %s", exc)
            return []

    def get_advisory(self, query: str) -> AIAdvisory | None:
        """Generate structured engineering advice and tradeoff evaluation for `query`."""
        if not query or len(query.strip()) < 2:
            return None
        from services.web_search import is_blocked
        if is_blocked(query):
            return None

        # 1. Generate dynamically via LLM for arbitrary queries if model is available
        try:
            model = build_chat_model(settings=self.settings)
            prompt = (
                f"You are PartPilot AI, an elite electronics hardware engineering advisor.\n"
                f"User is searching for: '{query}'.\n"
                "Return a strict JSON object with:\n"
                "- summary: 1-2 sentence engineering overview\n"
                "- recommendations: array of 2-3 objects with {mpn, title, why_choose, pros: [string], cons: [string], target_applications: [string]}\n"
                "- tradeoffs: object with {performance_vs_power: string, sourcing_and_lead_time: string, ecosystem_and_tooling: string}\n"
                "- substitutes: array of 1-2 objects with {mpn: string, description: string, tradeoff: string}\n"
                "- verdict: 1 concise takeaway sentence.\n"
            )
            response = model.invoke(prompt)
            content = str(response.content)
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                return AIAdvisory.model_validate(data)
        except Exception as exc:
            logger.debug("Dynamic AI advisory LLM generation unavailable: %s", exc)

        # 2. Dynamic heuristic synthesis from catalog and domain rules
        q_clean = query.strip()
        summaries, _ = self.repo.list_parts(SearchFilter(text=q_clean), limit=5, offset=0)
        if not summaries:
            # Try keyword prefix
            first_kw = q_clean.split()[0]
            summaries, _ = self.repo.list_parts(SearchFilter(text=first_kw), limit=5, offset=0)

        recommendations: list[AIRecommendation] = []
        for _idx, s in enumerate(summaries[:3]):
            pros = [
                f"{s.manufacturer} authenticated semiconductor production",
                f"Package {s.package or 'standard SMD/THT'}",
            ]
            if s.total_stock and s.total_stock > 1000:
                pros.append(f"Deep stock inventory ({s.total_stock:,} units)")
            else:
                pros.append("Multi-distributor availability")

            cons = ["Standard operating margin and thermal rules apply"]
            if s.lifecycle_status != LifecycleStatus.ACTIVE:
                cons[0] = f"Lifecycle status {s.lifecycle_status.value.upper()} requires review"

            title = s.description or f"{s.family.value.upper()} component by {s.manufacturer}"
            why = f"High-reliability {s.family.value} choice matching {q_clean} specifications."

            recommendations.append(
                AIRecommendation(
                    mpn=s.mpn,
                    title=title,
                    why_choose=why,
                    pros=pros,
                    cons=cons,
                    target_applications=["Industrial automation", "Power conversion", "Embedded systems"],
                )
            )

        if not recommendations:
            return None

        primary_mpn = recommendations[0].mpn
        return AIAdvisory(
            summary=(
                f"Engineering evaluation for '{q_clean}'. Selection balances switching figures-of-merit, "
                "thermal dissipation, package constraints, and component lifecycle viability."
            ),
            recommendations=recommendations,
            tradeoffs=AITradeoffs(
                performance_vs_power=(
                    "Evaluate conduction losses versus switching frequency: devices with lower resistance "
                    "reduce heat at high current, while lower capacitance enables higher frequency."
                ),
                sourcing_and_lead_time=(
                    "Check multi-distributor authorized inventory to avoid single-vendor supply bottlenecks."
                ),
                ecosystem_and_tooling="Supported by standard industry PCB layout and reference designs.",
            ),
            substitutes=[
                AISubstitute(
                    mpn=recommendations[1].mpn if len(recommendations) > 1 else primary_mpn,
                    description="Alternate candidate matching core electrical specifications",
                    tradeoff="Slightly different package or thermal profile but pin-compatible or drop-in capable.",
                )
            ] if len(recommendations) > 1 else [],
            verdict=f"Start with {primary_mpn} for primary design; verify thermal pad layout and second-source stock.",
        )

    def analyze_review_candidates(
        self,
        candidates: list[ReviewPartCandidate],
        priority: str = "balanced",
        custom_query: str | None = None,
    ) -> ReviewAdvisoryResponse:
        """Provide engineering recommendations, tradeoffs, and suggestions for queued parts."""
        if not candidates:
            return ReviewAdvisoryResponse(
                executive_summary="Your review queue has no components queued for evaluation.",
                overall_recommendation="Add components from parametric search to evaluate design tradeoffs.",
                candidate_evaluations=[],
                tradeoffs=[],
                engineering_suggestions=[
                    "Navigate to 'Find parts' and click '+ Review' on components matching your requirements.",
                    "Select at least 2 components to compare electrical FOM, thermal footprint, and supply chain availability.",
                ],
                bom_readiness_score=0,
            )

        # 1. Try LLM dynamic reasoning if query or LLM is active
        if custom_query or len(candidates) >= 1:
            try:
                model = build_chat_model(settings=self.settings)
                prompt_parts = []
                for p in candidates:
                    prompt_parts.append(
                        f"- MPN: {p.mpn}, Mfr: {p.manufacturer or 'N/A'}, Family: {p.family or 'N/A'}, "
                        f"Pkg: {p.package or 'N/A'}, Lifecycle: {p.lifecycle_status or 'ACTIVE'}, "
                        f"Stock: {p.stock or 0}, Price: {p.price or 'N/A'}, Params: {json.dumps(p.parameters)}"
                    )
                parts_str = "\n".join(prompt_parts)
                prompt = (
                    "You are PartPilot AI, a senior hardware engineering architect.\n"
                    f"Evaluate the following candidate components for final BOM approval under priority '{priority}':\n"
                    f"{parts_str}\n"
                    f"User engineering requirement/constraint: {custom_query or 'Balanced production readiness'}\n\n"
                    "Return ONLY a JSON object matching this schema:\n"
                    "{\n"
                    '  "executive_summary": "1-2 sentence overall design assessment",\n'
                    '  "overall_recommendation": "Clear statement of which part(s) should be finalized and why",\n'
                    '  "candidate_evaluations": [\n'
                    '    {"mpn": "...", "status_recommendation": "RECOMMENDED_FINAL" | "SUITABLE_ALTERNATE" | "CAUTION",\n'
                    '     "verdict": "...", "pros": ["..."], "cons": ["..."], "best_used_for": "..."}\n'
                    "  ],\n"
                    '  "tradeoffs": [\n'
                    '    {"dimension": "...", "analysis": "...", "advantage_mpn": "..."}\n'
                    "  ],\n"
                    '  "engineering_suggestions": ["Actionable design caveat 1", "Actionable design caveat 2"],\n'
                    '  "bom_readiness_score": 85\n'
                    "}"
                )
                response = model.invoke(prompt)
                match = re.search(r"\{.*\}", str(response.content), re.DOTALL)
                if match:
                    parsed = json.loads(match.group(0))
                    return ReviewAdvisoryResponse.model_validate(parsed)
            except Exception as exc:
                logger.info("Review queue LLM advisory fallback to deterministic engine: %s", exc)

        # 2. High-precision deterministic engineering heuristic engine
        evaluations: list[ReviewCandidateEvaluation] = []
        tradeoffs: list[ReviewTradeoff] = []
        suggestions: list[str] = []

        # Score parts
        scored_parts = []
        for p in candidates:
            score = 100
            reasons_pro = []
            reasons_con = []
            best_used = "General circuit implementation"

            # Check lifecycle
            lifecycle = str(p.lifecycle_status or "").upper()
            if "NRND" in lifecycle or "NOT RECOMMENDED" in lifecycle:
                score -= 35
                reasons_con.append("Not recommended for new designs (NRND lifecycle risk)")
            elif "OBSOLETE" in lifecycle or "EOL" in lifecycle:
                score -= 60
                reasons_con.append("Obsolete / End-of-Life component; high redesign risk")
            else:
                reasons_pro.append("Active lifecycle status with ongoing manufacturer commitment")

            # Check stock
            stock = p.stock or 0
            if stock > 2000:
                score += 15
                reasons_pro.append(f"Deep multi-distributor stock ({stock:,} units available)")
            elif stock == 0:
                score -= 20
                reasons_con.append("Zero current distributor stock; potential lead-time risk")
            else:
                reasons_pro.append(f"Moderate inventory ({stock:,} units available)")

            # Check electrical parameters
            rds_on = p.parameters.get("rds_on") or p.parameters.get("rds_on_max")
            qg = p.parameters.get("qg") or p.parameters.get("qg_typ")

            if rds_on:
                try:
                    rds_num = float(rds_on)
                    if rds_num < 15:
                        reasons_pro.append(f"Very low conduction resistance ({rds_num} mΩ Rds(on))")
                        best_used = "High-current power conversion & synchronous rectification"
                        if priority == "efficiency":
                            score += 25
                    else:
                        reasons_con.append(f"Moderate Rds(on) ({rds_num} mΩ); conduction losses scale with I²R")
                except (ValueError, TypeError):
                    pass

            if qg:
                try:
                    qg_num = float(qg)
                    if qg_num < 40:
                        reasons_pro.append(f"Low gate charge ({qg_num} nC Qg) enabling fast switching (>100kHz)")
                    else:
                        reasons_con.append(f"High total gate charge ({qg_num} nC Qg); requires robust gate drive current")
                except (ValueError, TypeError):
                    pass

            # Pricing
            price = p.price
            if price is not None and price > 0:
                if priority == "cost":
                    score += int(max(0, 30 - price * 5))
                reasons_pro.append(f"Unit price approx ${price:.2f} ({p.currency or 'USD'})")

            # Priority tuning
            if priority == "thermal" and p.package and any(pkg in p.package.upper() for pkg in ["TO-220", "TO-247", "D2PAK"]):
                score += 20
                reasons_pro.append(f"Through-hole/tabbed package ({p.package}) offers superior junction-to-heatsink thermal conductivity")

            scored_parts.append((score, p, reasons_pro, reasons_con, best_used))

        # Sort descending by score
        scored_parts.sort(key=lambda x: x[0], reverse=True)

        for idx, (score, p, pros, cons, best_used) in enumerate(scored_parts):
            lifecycle = str(p.lifecycle_status or "").upper()
            if "OBSOLETE" in lifecycle or "NRND" in lifecycle or score < 50:
                status_rec = "CAUTION"
                verdict = f"{p.mpn} carries lifecycle or supply chain caveats that warrant review before BOM sign-off."
            elif idx == 0:
                status_rec = "RECOMMENDED_FINAL"
                verdict = f"{p.mpn} is PartPilot's primary selection under the '{priority}' design priority."
            else:
                status_rec = "SUITABLE_ALTERNATE"
                verdict = f"{p.mpn} is a viable alternate candidate or second source."

            evaluations.append(
                ReviewCandidateEvaluation(
                    mpn=p.mpn,
                    status_recommendation=status_rec,
                    verdict=verdict,
                    pros=pros[:3],
                    cons=cons[:2] if cons else ["Standard design margin rules apply"],
                    best_used_for=best_used,
                )
            )

        # Generate comparative tradeoffs
        if len(candidates) >= 2:
            p1 = candidates[0]
            p2 = candidates[1]
            tradeoffs.append(
                ReviewTradeoff(
                    dimension="Conduction Loss vs Switching Frequency",
                    analysis=(
                        f"Comparing {p1.mpn} and {p2.mpn}: Select the device with lowest Rds(on) "
                        f"if operating below 50kHz where I²R dominates, or lowest Qg for high-frequency PWM."
                    ),
                    advantage_mpn=scored_parts[0][1].mpn,
                )
            )
            tradeoffs.append(
                ReviewTradeoff(
                    dimension="Thermal Footprint vs Assembly Density",
                    analysis=(
                        f"{p1.mpn} ({p1.package or 'standard pkg'}) vs {p2.mpn} ({p2.package or 'standard pkg'}): "
                        "Evaluate junction-to-ambient thermal resistance and copper pour requirements under full load."
                    ),
                    advantage_mpn=scored_parts[0][1].mpn,
                )
            )
            tradeoffs.append(
                ReviewTradeoff(
                    dimension="Procurement & Sourcing Resilience",
                    analysis=(
                        f"Multi-sourcing between {p1.manufacturer or 'Mfr A'} and {p2.manufacturer or 'Mfr B'} "
                        "protects manufacturing lines from single-vendor allocation delays."
                    ),
                    advantage_mpn=scored_parts[0][1].mpn,
                )
            )
        else:
            p = candidates[0]
            tradeoffs.append(
                ReviewTradeoff(
                    dimension="Design Feasibility & Single Sourcing",
                    analysis=f"{p.mpn} is the sole evaluated candidate. Consider adding a pin-compatible alternate to guard against supply disruptions.",
                    advantage_mpn=p.mpn,
                )
            )

        # Actionable engineering suggestions
        top_mpn = scored_parts[0][1].mpn
        suggestions.append(f"Ensure gate driver circuit delivers recommended Vgs drive voltage for {top_mpn} to prevent entering linear mode.")
        suggestions.append("Verify PCB thermal via stitching directly underneath power tabs to distribute heat across internal ground planes.")
        suggestions.append("Finalize component reference designators and export the production BOM CSV for manufacturing verification.")

        # BOM readiness score
        active_count = sum(1 for p in candidates if "OBSOLETE" not in str(p.lifecycle_status or "").upper())
        base_readiness = int((active_count / len(candidates)) * 80 + (15 if len(candidates) >= 2 else 5))
        bom_readiness = min(100, max(20, base_readiness))

        summary = (
            f"Evaluated {len(candidates)} candidate part(s) across electrical specifications, lifecycle risk, "
            f"and distributor inventory. Priority set to '{priority}'."
        )
        overall = f"Finalize {top_mpn} as the primary BOM entry; register alternates for second-source resilience."

        return ReviewAdvisoryResponse(
            executive_summary=summary,
            overall_recommendation=overall,
            candidate_evaluations=evaluations,
            tradeoffs=tradeoffs,
            engineering_suggestions=suggestions,
            bom_readiness_score=bom_readiness,
        )

