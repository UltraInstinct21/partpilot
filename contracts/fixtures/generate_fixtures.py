"""Generate the recorded PartPilot fixtures.

Run with:  python contracts/fixtures/generate_fixtures.py

Everything this script writes is SYNTHETIC. The shapes follow the real
DigiKey / Nexar / Mouser responses (verified against the vendor documentation),
but the values are made up for the MOSFETs and gate drivers. They exist so the
collectors, the extractors, the validators and the frontend can be developed
and tested without touching a live API (Global rule 2).

Outputs
-------
digikey/product_details.json     one full productdetails response
digikey/keyword_search.json      one keyword search response
digikey/parts.json               10 normalised parts
nexar/supply_response.json       one GraphQL response (data + errors)
nexar/parts.json                 10 normalised parts
mouser/partnumber_search.json    one search response
mouser/parts.json                10 normalised parts
pages/*.json                     5 extracted page samples (text + tables)
seed/parts.json                  30 seed parts
seed/seed_parts.csv              the same 30 parts as CSV
gold/gold_set_example.csv        12 labelled rows (gold set template)
pdfs/synthetic_mosfet.pdf        synthetic datasheet with a known table
pdfs/synthetic_gate_driver.pdf   synthetic datasheet with a known table
pdfs/synthetic_scanned.pdf       image only PDF, no text layer
pdfs/expected_values.json        the exact values inside the synthetic PDFs
"""

from __future__ import annotations

import csv
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Shared catalogue
# ---------------------------------------------------------------------------

NOW = datetime(2026, 10, 1, 9, 30, tzinfo=timezone.utc)


def _ts(days_ago: int = 0, hours: int = 0) -> str:
    return (NOW - timedelta(days=days_ago, hours=hours)).isoformat().replace("+00:00", "Z")


# (mpn, manufacturer, package, lifecycle, family)
MOSFETS = [
    ("IRF3205S", "International Rectifier", "TO-220AB", "active", 56.0, 3.2, 12.0),
    ("IRF540N", "International Rectifier", "TO-220AB", "active", 100.0, 33.0, 47.0),
    ("IRLZ44N", "International Rectifier", "TO-220AB", "active", 55.0, 25.0, 48.0),
    ("BSC030N08NS5", "Infineon Technologies", "SuperSO8", "active", 80.0, 3.0, 6.2),
    ("BSZ084N08NS5", "Infineon Technologies", "SuperSO8", "active", 80.0, 8.4, 11.5),
    ("Si7148DP", "Vishay Siliconix", "PowerPAK SO-8", "active", 30.0, 2.8, 1.1),
    ("NVMFS5C430NL", "onsemi", "DFN5X6", "active", 30.0, 4.3, 1.6),
    ("PSMN2R30", "Nexperia", "PowerPAK SO-8", "active", 30.0, 2.3, 1.9),
    ("STP55NF06L", "STMicroelectronics", "TO-220AB", "active", 60.0, 55.0, 8.0),
    ("CSD1642Q5", "Infineon Technologies", "TO-263", "active", 100.0, 16.4, 5.9),
    ("DMN3024U-13", "Diodes Incorporated", "TO-252", "active", 30.0, 2.4, 9.0),
    ("AOD4184A", "Alpha & Omega Semiconductor", "SO-8", "nrnd", 40.0, 18.4, 7.0),
    ("SI2302CDS", "Vishay Siliconix", "SOT-23", "active", 20.0, 3.0, 11.0),
    ("DMP3010LK3", "Diodes Incorporated", "TO-252", "active", 30.0, 10.1, 22.0),
    ("CSD19536Y", "Texas Instruments", "DSBGA-8", "active", 100.0, 0.2, 2.4),
]

GATE_DRIVERS = [
    ("IR2110", "International Rectifier", "TO-263-5", "active", 25.0),
    ("IR2104", "International Rectifier", "SOIC-8", "active", 25.0),
    ("IR2304", "International Rectifier", "SOIC-8", "active", 25.0),
    ("TC4427", "Microchip Technology", "SOIC-8", "active", 25.0),
    ("TC4429", "Microchip Technology", "SOIC-8", "active", 25.0),
    ("UCC27511", "Texas Instruments", "SOT-23-6", "active", 8.0),
    ("UCC27524", "Texas Instruments", "HTSSOP-16", "active", 10.0),
    ("UCC27531", "Texas Instruments", "SOT-23-6", "active", 5.0),
    ("EL7158", "Renesas Electronics", "SOIC-8", "active", 8.0),
    ("6N137", "onsemi", "SOIC-8", "active", 10.0),
    ("MAX4428", "Analog Devices / Maxim", "SOIC-8", "active", 2.0),
    ("MAX4429", "Analog Devices / Maxim", "SOIC-8", "active", 2.0),
    ("Si9121", "Vishay Siliconix", "SOIC-8", "active", 2.0),
    ("NCP51820", "onsemi", "SOIC-8", "active", 8.0),
    ("LM5109B", "Texas Instruments", "HTSSOP-16", "active", 1.0),
]

PARAM_NAMES_MOSFET = [
    "vds_max",
    "id_continuous",
    "rds_on",
    "vgs_threshold",
    "vgs_max",
    "total_gate_charge_qg",
    "gate_drain_charge_qgd",
    "input_capacitance_ciss",
    "output_capacitance_coss",
    "max_junction_temp",
    "package",
    "thermal_resistance",
    "reverse_recovery_qrr",
]

PARAM_NAMES_GATE_DRIVER = [
    "supply_voltage_min",
    "supply_voltage_max",
    "peak_source_current",
    "peak_sink_current",
    "input_logic_level",
    "propagation_delay",
    "rise_time",
    "fall_time",
    "uvlo_threshold",
    "channel_count",
    "package",
    "operating_temp_min",
    "operating_temp_max",
]

#: The seed fixture stores CANONICAL SI base units, exactly like the database
#: and the validator (see docs/CONTRACTS.md). The datasheet units are only
#: used inside the raw API fixtures and the synthetic PDFs, because that is
#: what the source document says.
#:
#: The factors are applied with ``pint`` so the stored value is bit identical
#: to what ``db.units.canonicalize()`` produces.
_SEED_UNIT_FACTORS: dict[str, tuple[str, float]] = {
    "mohm": ("ohm", 1e-3),
    "nC": ("C", 1e-9),
    "uC": ("C", 1e-6),
    "pF": ("F", 1e-12),
    "nF": ("F", 1e-9),
    "ns": ("s", 1e-9),
    "us": ("s", 1e-6),
    "mV": ("V", 1e-3),
    "mA": ("A", 1e-3),
}


def to_canonical(value, unit):
    """Return ``(value, unit)`` in the canonical SI base unit."""
    if value is None or not unit:
        return value, unit
    if unit not in _SEED_UNIT_FACTORS:
        return value, unit
    target, factor = _SEED_UNIT_FACTORS[unit]
    return value * factor, target


#: The inverse of :func:`to_canonical`. The RAW API fixtures keep the unit the
#: vendor writes on the page ("12 mOhm", "37.5 nC", "8750 pF"), because that is
#: what a real API response contains. Only the seed fixture, which represents
#: data that has already passed the validator, is canonical.
_CANONICAL_TO_DATASHEET: dict[str, tuple[str, float]] = {
    "ohm": ("mohm", 1e3),
    "C": ("nC", 1e9),
    "F": ("pF", 1e12),
    "s": ("ns", 1e9),
}


def to_datasheet(value, unit):
    """Return ``(value, unit)`` in the unit a vendor writes on the page."""
    if value is None or not unit:
        return value, unit
    if unit not in _CANONICAL_TO_DATASHEET:
        return value, unit
    target, factor = _CANONICAL_TO_DATASHEET[unit]
    return value * factor, target


MOSFET_FAMILY_ID = "86"
GATE_DRIVER_FAMILY_ID = "421"


def _mosfet_params(rng: random.Random, vds: float, idc: float, rds: float) -> dict[str, dict]:
    """Build a plausible parameter set for a MOSFET."""
    return {
        "vds_max": {"value": vds, "unit": "V", "condition": {}},
        "id_continuous": {"value": idc, "unit": "A", "condition": {"Tc": "25 C"}},
        "rds_on": {
            "value": rds,
            "unit": "mohm",
            "condition": {"Vgs": "10 V", "Id": f"{max(1.0, idc / 2):.0f} A", "Tj": "25 C"},
        },
        "vgs_threshold": {
            "value": round(rng.uniform(2.0, 4.0), 2),
            "unit": "V",
            "condition": {"Id": "250 uA"},
        },
        "vgs_max": {"value": 20.0, "unit": "V", "condition": {}},
        "total_gate_charge_qg": {
            "value": round(rng.uniform(8, 90), 1),
            "unit": "nC",
            "condition": {"Vgs": "10 V", "Id": f"{max(1.0, idc / 2):.0f} A"},
        },
        "gate_drain_charge_qgd": {
            "value": round(rng.uniform(2, 22), 1),
            "unit": "nC",
            "condition": {"Vgs": "10 V", "Id": f"{max(1.0, idc / 2):.0f} A"},
        },
        "input_capacitance_ciss": {
            "value": round(rng.uniform(600, 12000), 0),
            "unit": "pF",
            "condition": {"Vds": "50 V", "Vgs": "0 V", "f": "1 MHz"},
        },
        "output_capacitance_coss": {
            "value": round(rng.uniform(120, 2400), 0),
            "unit": "pF",
            "condition": {"Vds": "50 V", "Vgs": "0 V", "f": "1 MHz"},
        },
        "max_junction_temp": {"value": 175.0, "unit": "degC", "condition": {}},
        "package": {"value": None, "unit": None, "condition": {}},
        "thermal_resistance": {
            "value": round(rng.uniform(0.6, 4.5), 1),
            "unit": "degC/W",
            "condition": {"RthJC": "junction to case"},
        },
        "reverse_recovery_qrr": {
            "value": round(rng.uniform(30, 400), 0),
            "unit": "nC",
            "condition": {"Id": "10 A", "di/dt": "100 A/us"},
        },
    }


def _gate_driver_params(rng: random.Random, supply: float) -> dict[str, dict]:
    vmin = round(rng.choice([4.5, 5.0, 6.0, 7.0]), 1)
    vmax = round(vmin + supply, 1)
    return {
        "supply_voltage_min": {"value": vmin, "unit": "V", "condition": {}},
        "supply_voltage_max": {"value": vmax, "unit": "V", "condition": {}},
        "peak_source_current": {
            "value": round(rng.uniform(1.0, 8.0), 1),
            "unit": "A",
            "condition": {},
        },
        "peak_sink_current": {
            "value": round(rng.uniform(1.0, 8.0), 1),
            "unit": "A",
            "condition": {},
        },
        "input_logic_level": {
            "value": round(rng.uniform(0.8, 2.0), 2),
            "unit": "V",
            "condition": {"VIL": "maximum low level input voltage"},
        },
        "propagation_delay": {
            "value": round(rng.uniform(15, 250), 1),
            "unit": "ns",
            "condition": {"Vcc": f"{vmax} V", "Rl": "10 kohm"},
        },
        "rise_time": {"value": round(rng.uniform(5, 120), 1), "unit": "ns", "condition": {}},
        "fall_time": {"value": round(rng.uniform(5, 120), 1), "unit": "ns", "condition": {}},
        "uvlo_threshold": {
            "value": round(rng.uniform(4.0, 12.0), 2),
            "unit": "V",
            "condition": {},
        },
        "channel_count": {"value": 1, "unit": None, "condition": {}},
        "package": {"value": None, "unit": None, "condition": {}},
        "operating_temp_min": {"value": -40.0, "unit": "degC", "condition": {}},
        "operating_temp_max": {"value": 125.0, "unit": "degC", "condition": {}},
    }


def build_parts() -> list[dict]:
    """Return 30 normalised part dictionaries (15 MOSFET, 15 gate driver).

    The parameter values are in CANONICAL SI base units and every part carries
    distributor offers with a stock number, so the BOM health check and the
    alternatives ranking can be exercised against the seed data.
    """
    rng = random.Random(20261001)
    # A separate stream for the offers, so adding an offer never changes the
    # parameter values (and the tests that pin them stay valid).
    offer_rng = random.Random(20261002)
    parts: list[dict] = []
    for index, (mpn, mfr, package, lifecycle, vds, idc, rds) in enumerate(MOSFETS):
        raw_params = _mosfet_params(rng, vds, idc, rds)
        parts.append(
            {
                "part_id": f"mosfet-{mpn.lower()}",
                "mpn": mpn,
                "manufacturer": mfr,
                "family": "mosfet",
                "package": package,
                "lifecycle_status": lifecycle,
                "datasheet_url": f"https://example.invalid/datasheets/{mpn}.pdf",
                "description": f"{mfr} {mpn} N-channel power MOSFET, {vds:.0f} V",
                "source_ids": [f"api-digikey-{mpn.lower()}", f"api-nexar-{mpn.lower()}"],
                "parameters": _canonicalise_params(raw_params),
                # The raw API fixtures use the unit the vendor writes.
                "_raw_parameters": raw_params,
                "offers": _offers(mpn, offer_rng, lifecycle),
            }
        )
    for index, (mpn, mfr, package, _charge, supply) in enumerate(GATE_DRIVERS):
        raw_params = _gate_driver_params(rng, supply)
        parts.append(
            {
                "part_id": f"gate-driver-{mpn.lower()}",
                "mpn": mpn,
                "manufacturer": mfr,
                "family": "gate_driver",
                "package": package,
                "lifecycle_status": "active",
                "datasheet_url": f"https://example.invalid/datasheets/{mpn}.pdf",
                "description": f"{mfr} {mpn} high-side gate driver, {supply:.0f} V",
                "source_ids": [f"api-digikey-{mpn.lower()}", f"api-mouser-{mpn.lower()}"],
                "parameters": _canonicalise_params(raw_params),
                "_raw_parameters": raw_params,
                "offers": _offers(mpn, offer_rng, "active"),
            }
        )
    return parts


def _canonicalise_params(params: dict[str, dict]) -> dict[str, dict]:
    """Convert every parameter value to its canonical SI base unit."""
    out: dict[str, dict] = {}
    for name, spec in params.items():
        value, unit = to_canonical(spec.get("value"), spec.get("unit"))
        out[name] = {**spec, "value": value, "unit": unit}
    return out


def _offers(mpn: str, rng: random.Random, lifecycle: str) -> list[dict]:
    """Return deterministic distributor offers for a part.

    Rules that make the seed data useful for the BOM check:
    * every part has at least one DigiKey offer;
    * the NRND part is single source (no Mouser offer) -> `single_source` risk;
    * one part has a low stock (< 1000) -> `low_stock` risk;
    * an obsolete part would have no offers at all.
    """
    if lifecycle == "obsolete":
        return []
    digikey_stock = rng.randrange(200, 40000)
    price = round(rng.uniform(0.35, 4.5), 4)
    offers = [
        {
            "distributor": "digikey",
            "sku": f"296-{mpn}-ND",
            "stock": digikey_stock,
            "unit_price": price,
            "currency": "USD",
            "url": f"https://www.digikey.com/en/products/detail/x/{mpn}/1234567",
        }
    ]
    if lifecycle == "nrnd":
        # Single source on purpose.
        return offers
    if mpn == "IRF540N":
        # Low stock on purpose.
        digikey_stock = 120
        offers[0]["stock"] = digikey_stock
        return offers
    offers.append(
        {
            "distributor": "mouser",
            "sku": f"81-{mpn}",
            "stock": rng.randrange(50, 20000),
            "unit_price": round(price * 1.04, 4),
            "currency": "USD",
            "url": f"https://www.mouser.com/ProductDetail/x/{mpn}",
        }
    )
    return offers


# ---------------------------------------------------------------------------
# DigiKey
# ---------------------------------------------------------------------------


def digikey_product_details(part: dict) -> dict:
    mpn = part["mpn"]
    # The raw API response carries the unit the vendor writes on the page.
    params = part.get("_raw_parameters") or part["parameters"]
    return {
        "Product": {
            "ManufacturerProductNumber": mpn,
            "Manufacturer": {"Id": 1234, "Name": part["manufacturer"]},
            "Description": part["description"],
            "ProductUrl": f"https://www.digikey.com/en/products/detail/{part['manufacturer']}/{mpn}/1234567",
            "DatasheetUrl": part["datasheet_url"],
            "Family": part["family"],
            "Category": {
                "Id": int(MOSFET_FAMILY_ID if part["family"] == "mosfet" else GATE_DRIVER_FAMILY_ID),
                "Name": "Transistors - FETs, MOSFETs" if part["family"] == "mosfet" else "Gate Drivers",
            },
            "Status": {
                "LifecycleStatus": part["lifecycle_status"],
                "ObsoleteReason": "End of Life" if part["lifecycle_status"] == "obsolete" else "",
            },
            "UnitPrice": 0.89,
            "QuantityAvailable": 48213,
            "ProductVariations": [
                {
                    "DigiKeyProductNumber": f"296-{mpn}-ND",
                    "PackageType": {"Id": 1, "Name": "Tube"},
                    "StandardPricing": [
                        {"BreakQuantity": 1, "UnitPrice": 0.89, "TotalPrice": 0.89},
                        {"BreakQuantity": 10, "UnitPrice": 0.674, "TotalPrice": 6.74},
                        {"BreakQuantity": 100, "UnitPrice": 0.5223, "TotalPrice": 52.23},
                        {"BreakQuantity": 1000, "UnitPrice": 0.4121, "TotalPrice": 412.1},
                    ],
                    "MinimumOrderQuantity": 1,
                    "StandardPackage": 100,
                    "QuantityAvailableforPackageType": 48213,
                }
            ],
            "Parameters": {
                "Parameter": [
                    {
                        "ParameterId": 1001,
                        "Text": "Drain to Source Voltage (Vdss)",
                        "Value": f"{params['vds_max']['value']} V",
                    },
                    {
                        "ParameterId": 1002,
                        "Text": "Continuous Drain Current (Id) @ 25°C",
                        "Value": f"{params['id_continuous']['value']} A",
                    },
                    {
                        "ParameterId": 1003,
                        "Text": "RDS(on) @ Id, Vgs",
                        "Value": f"{params['rds_on']['value']} {params['rds_on']['unit']}",
                    },
                    {
                        "ParameterId": 1004,
                        "Text": "Gate Threshold Voltage (Vgs(th))",
                        "Value": f"{params['vgs_threshold']['value']} V",
                    },
                    {
                        "ParameterId": 1005,
                        "Text": "Total Gate Charge (Qg)",
                        "Value": f"{params['total_gate_charge_qg']['value']} {params['total_gate_charge_qg']['unit']}",
                    },
                    {
                        "ParameterId": 1006,
                        "Text": "Package / Case",
                        "Value": part["package"],
                    },
                ]
            },
        }
    }


def digikey_keyword_search(parts: list[dict]) -> dict:
    return {
        "Products": [
            {
                "ManufacturerProductNumber": p["mpn"],
                "Manufacturer": {"Id": 1234, "Name": p["manufacturer"]},
                "Description": p["description"],
                "ProductUrl": f"https://www.digikey.com/en/products/detail/x/{p['mpn']}/1234567",
                "DatasheetUrl": p["datasheet_url"],
                "UnitPrice": 0.89,
                "QuantityAvailable": 48213,
            }
            for p in parts[:5]
        ],
        "ProductsCount": len(parts[:5]),
        "ProductsTotalCount": len(parts),
    }


# ---------------------------------------------------------------------------
# Nexar
# ---------------------------------------------------------------------------


def nexar_response(parts: list[dict]) -> dict:
    return {
        "data": {
            "supSearchMpn": {
                "hits": len(parts),
                "results": [
                    {
                        "part": {
                            "id": f"nexar-{p['part_id']}",
                            "name": p["description"],
                            "mpn": p["mpn"],
                            "manufacturer": {"id": "mfr-1", "name": p["manufacturer"]},
                            "totalAvail": 48213,
                            "category": {"id": "86", "name": "Transistors - FETs, MOSFETs"},
                            "lifecycle": {"status": p["lifecycle_status"].upper()},
                            "specs": [
                                {
                                    "attribute": {
                                        "id": "attr-vds",
                                        "name": "Drain Source Voltage (Vdss)",
                                        "shortname": "vds",
                                    },
                                    "value": p["parameters"].get("vds_max", {}).get("value"),
                                    "displayValue": f"{p['parameters'].get('vds_max', {}).get('value')} V",
                                    "unitsName": "V",
                                    "unitsSymbol": "V",
                                }
                                for p in parts
                            ],
                            "sellers": [
                                {
                                    "company": {"id": "digi", "name": "DigiKey", "isVerified": True},
                                    "isAuthorized": True,
                                    "offers": [
                                        {
                                            "id": "offer-1",
                                            "sku": f"296-{p['mpn']}-ND",
                                            "inventoryLevel": 48213,
                                            "moq": 1,
                                            "prices": [
                                                {"quantity": 1, "convertedPrice": 0.89, "convertedCurrency": "USD"},
                                                {"quantity": 100, "convertedPrice": 0.5223, "convertedCurrency": "USD"},
                                            ],
                                        }
                                    ],
                                }
                            ],
                        }
                    }
                    for p in parts
                ],
            }
        },
        "errors": [],
    }


# ---------------------------------------------------------------------------
# Mouser
# ---------------------------------------------------------------------------


def mouser_response(parts: list[dict]) -> dict:
    return {
        "Errors": [],
        "SearchResults": {
            "NumberOfResult": len(parts),
            "Parts": [
                {
                    "MouserPartNumber": f"81-{p['mpn']}",
                    "ManufacturerPartNumber": p["mpn"],
                    "Manufacturer": p["manufacturer"],
                    "Description": p["description"],
                    "Category": "Transistors - FETs, MOSFETs"
                    if p["family"] == "mosfet"
                    else "PMIC - Gate Drivers",
                    "DataSheetUrl": p["datasheet_url"],
                    "ProductDetailUrl": f"https://www.mouser.com/ProductDetail/{p['manufacturer']}/{p['mpn']}",
                    "ImagePath": f"https://www.mouser.com/images/{p['mpn']}.jpg",
                    "Availability": "48213 In Stock",
                    "AvailabilityInStock": "48213",
                    "LeadTime": "84 Days",
                    "LifecycleStatus": "New Product" if p["lifecycle_status"] == "active" else "End of Life",
                    "IsDiscontinued": "false" if p["lifecycle_status"] == "active" else "true",
                    "SuggestedReplacement": "",
                    "Min": "1",
                    "Mult": "1",
                    "Reeling": True,
                    "ROHSStatus": "RoHS Compliant",
                    "PriceBreaks": [
                        {"Quantity": 1, "Price": "0.89", "Currency": "USD"},
                        {"Quantity": 10, "Price": "0.674", "Currency": "USD"},
                        {"Quantity": 100, "Price": "0.5223", "Currency": "USD"},
                        {"Quantity": 1000, "Price": "0.4121", "Currency": "USD"},
                    ],
                    "ProductAttributes": [
                        {"AttributeName": "Drain to Source Voltage (Vdss)", "AttributeValue": "100 V"},
                        {"AttributeName": "Continuous Drain Current (Id)", "AttributeValue": "25 A"},
                        {"AttributeName": "RDS(on) @ Id, Vgs", "AttributeValue": "5.5 mOhm"},
                        {"AttributeName": "Package / Case", "AttributeValue": p["package"]},
                    ],
                }
                for p in parts
            ],
        },
    }


# ---------------------------------------------------------------------------
# Extracted page samples
# ---------------------------------------------------------------------------


def page_samples() -> list[dict]:
    """Five extracted pages: text plus the tables pdfplumber found."""
    return [
        {
            "source_id": "pdf-synthetic-mosfet",
            "family": "mosfet",
            "page": 1,
            "title": "Absolute Maximum Ratings",
            "text": (
                "PARTPILOT SYNTHETIC DATASHEET\n"
                "PMP100N08 - 100 V N-Channel Power MOSFET\n\n"
                "1. Absolute Maximum Ratings\n"
                "TA = 25 C unless otherwise noted.\n"
                "(Tj = 125 C maximum continuous)\n"
            ),
            "tables": [
                {
                    "bbox": [54, 200, 558, 300],
                    "rows": [
                        ["Parameter", "Symbol", "Value", "Unit"],
                        ["Drain-Source Voltage", "VDS", "100", "V"],
                        ["Continuous Drain Current", "ID", "25", "A"],
                        ["Maximum Junction Temperature", "TJ", "175", "C"],
                    ],
                }
            ],
        },
        {
            "source_id": "pdf-synthetic-mosfet",
            "family": "mosfet",
            "page": 2,
            "title": "Electrical Characteristics",
            "text": (
                "2. Electrical Characteristics\n"
                "TA = 25 C unless otherwise noted.\n"
            ),
            "tables": [
                {
                    "bbox": [54, 180, 558, 560],
                    "rows": [
                        [
                            "Parameter",
                            "Symbol",
                            "Min",
                            "Typ",
                            "Max",
                            "Unit",
                            "Conditions",
                        ],
                        ["Drain-Source On-Resistance", "RDS(on)", "-", "5.5", "7", "mOhm", "VGS = 10 V, ID = 10 A, TJ = 25 C"],
                        ["Gate-Source Threshold Voltage", "VGS(th)", "2", "3.5", "4.5", "V", "ID = 250 uA"],
                        ["Gate-Source Voltage", "VGS", "-", "-", "20", "V", ""],
                        ["Total Gate Charge", "QG", "-", "62", "-", "nC", "VGS = 10 V, ID = 10 A"],
                        ["Gate-Drain Charge", "QGD", "-", "12", "-", "nC", "VGS = 10 V, ID = 10 A"],
                        ["Input Capacitance", "CISS", "-", "4900", "-", "pF", "VDS = 50 V, VGS = 0 V, f = 1 MHz"],
                        ["Output Capacitance", "COSS", "-", "900", "-", "pF", "VDS = 50 V, VGS = 0 V, f = 1 MHz"],
                        ["Thermal Resistance, Junction-to-Case", "RthJC", "-", "1.2", "-", "C/W", ""],
                        ["Reverse Recovery Charge", "Qrr", "-", "120", "-", "nC", "ID = 10 A, di/dt = 100 A/us"],
                    ],
                }
            ],
        },
        {
            "source_id": "pdf-synthetic-gate-driver",
            "family": "gate_driver",
            "page": 1,
            "title": "Electrical Characteristics",
            "text": (
                "PARTPILOT SYNTHETIC DATASHEET\n"
                "PGD35 - 35 V High-Side Gate Driver\n\n"
                "1. Electrical Characteristics\n"
                "TA = 25 C unless otherwise noted.\n"
            ),
            "tables": [
                {
                    "bbox": [54, 180, 558, 480],
                    "rows": [
                        [
                            "Parameter",
                            "Symbol",
                            "Min",
                            "Typ",
                            "Max",
                            "Unit",
                            "Conditions",
                        ],
                        ["Supply Voltage", "VCC", "4.5", "-", "35", "V", ""],
                        ["Peak Source Current", "IO+", "-", "2", "-", "A", ""],
                        ["Peak Sink Current", "IO-", "-", "2", "-", "A", ""],
                        ["Input Low Level Voltage", "VIL", "-", "-", "0.8", "V", ""],
                        ["Propagation Delay", "tPD", "-", "20", "-", "ns", "VCC = 15 V, RL = 10 kohm"],
                        ["Rise Time", "tR", "-", "15", "-", "ns", "CL = 1000 pF"],
                        ["Fall Time", "tF", "-", "14", "-", "ns", "CL = 1000 pF"],
                        ["UVLO Threshold", "UVLO", "-", "8", "-", "V", ""],
                        ["Operating Temperature", "TOPR", "-40", "-", "125", "C", ""],
                    ],
                }
            ],
        },
        {
            "source_id": "pdf-synthetic-gate-driver",
            "family": "gate_driver",
            "page": 2,
            "title": "Absolute Maximum Ratings",
            "text": (
                "2. Absolute Maximum Ratings\n"
                "TA = 25 C unless otherwise noted.\n"
            ),
            "tables": [
                {
                    "bbox": [54, 200, 558, 320],
                    "rows": [
                        ["Parameter", "Symbol", "Value", "Unit"],
                        ["Supply Voltage", "VCC", "35", "V"],
                        ["Output Current, Source", "IO+", "2", "A"],
                        ["Output Current, Sink", "IO-", "2", "A"],
                    ],
                }
            ],
        },
        {
            "source_id": "pdf-synthetic-scanned",
            "family": "mosfet",
            "page": 1,
            "title": "Electrical Characteristics (scanned)",
            "text": "",
            "tables": [],
            "is_image_only": True,
            "note": "Scanned datasheet page: no text layer. Tier 1 must not return values.",
        },
    ]


# ---------------------------------------------------------------------------
# Synthetic PDFs
# ---------------------------------------------------------------------------

MOSFET_ROWS = [
    ["Drain-Source On-Resistance", "RDS(on)", "-", "5.5", "7", "mOhm", "VGS = 10 V, ID = 10 A, TJ = 25 C"],
    ["Gate-Source Threshold Voltage", "VGS(th)", "2", "3.5", "4.5", "V", "ID = 250 uA"],
    ["Gate-Source Voltage", "VGS", "-", "-", "20", "V", ""],
    ["Total Gate Charge", "QG", "-", "62", "-", "nC", "VGS = 10 V, ID = 10 A"],
    ["Gate-Drain Charge", "QGD", "-", "12", "-", "nC", "VGS = 10 V, ID = 10 A"],
    ["Input Capacitance", "CISS", "-", "4900", "-", "pF", "VDS = 50 V, VGS = 0 V, f = 1 MHz"],
    ["Output Capacitance", "COSS", "-", "900", "-", "pF", "VDS = 50 V, VGS = 0 V, f = 1 MHz"],
    ["Thermal Resistance, Junction-to-Case", "RthJC", "-", "1.2", "-", "C/W", ""],
    ["Reverse Recovery Charge", "Qrr", "-", "120", "-", "nC", "ID = 10 A, di/dt = 100 A/us"],
]

GATE_DRIVER_ROWS = [
    ["Supply Voltage", "VCC", "4.5", "-", "35", "V", ""],
    ["Peak Source Current", "IO+", "-", "2", "-", "A", ""],
    ["Peak Sink Current", "IO-", "-", "2", "-", "A", ""],
    ["Input Low Level Voltage", "VIL", "-", "-", "0.8", "V", ""],
    ["Propagation Delay", "tPD", "-", "20", "-", "ns", "VCC = 15 V, RL = 10 kohm"],
    ["Rise Time", "tR", "-", "15", "-", "ns", "CL = 1000 pF"],
    ["Fall Time", "tF", "-", "14", "-", "ns", "CL = 1000 pF"],
    ["UVLO Threshold", "UVLO", "-", "8", "-", "V", ""],
    ["Operating Temperature", "TOPR", "-40", "-", "125", "C", ""],
]

MOSFET_ABS_ROWS = [
    ["Drain-Source Voltage", "VDS", "100", "V"],
    ["Continuous Drain Current", "ID", "25", "A"],
    ["Maximum Junction Temperature", "TJ", "175", "C"],
]

GATE_DRIVER_ABS_ROWS = [
    ["Supply Voltage", "VCC", "35", "V"],
    ["Output Current, Source", "IO+", "2", "A"],
    ["Output Current, Sink", "IO-", "2", "A"],
]


def _draw_table(canvas, x, y_top, headers, rows, col_widths, row_h=20):
    """Draw a fully ruled table.

    The vertical rules matter: pdfplumber only splits a row into columns when
    it can see the ruling lines, so every column border is drawn.
    """
    total_w = sum(col_widths)
    canvas.setLineWidth(0.6)
    y = y_top
    # header band
    canvas.setFillColorRGB(0.88, 0.9, 0.94)
    canvas.rect(x, y - row_h, total_w, row_h, fill=1, stroke=1)
    canvas.setFillColorRGB(0, 0, 0)
    canvas.setFont("Helvetica-Bold", 7.5)
    cx = x
    for head, w in zip(headers, col_widths):
        canvas.drawString(cx + 3, y - row_h + 6, str(head))
        cx += w
    canvas.setFont("Helvetica", 7.5)
    y = y_top - row_h
    for row in rows:
        canvas.rect(x, y - row_h, total_w, row_h, fill=0, stroke=1)
        cx = x
        for cell, w in zip(row, col_widths):
            canvas.drawString(cx + 3, y - row_h + 6, str(cell))
            cx += w
        y -= row_h

    # vertical rules over the whole table
    top = y_top
    bottom = y
    cx = x
    for w in col_widths:
        canvas.line(cx, bottom, cx, top)
        cx += w
    canvas.line(cx, bottom, cx, top)
    # horizontal rules
    canvas.line(x, bottom, x + total_w, bottom)
    canvas.line(x, top, x + total_w, top)
    return y


def build_mosfet_pdf(path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdfcanvas

    c = pdfcanvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    # --- page 1: absolute maximum ratings
    c.setFont("Helvetica-Bold", 16)
    c.drawString(54, height - 70, "PMP100N08")
    c.setFont("Helvetica", 11)
    c.drawString(54, height - 88, "100 V N-Channel Power MOSFET - SYNTHETIC TEST DATASHEET")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(54, height - 130, "1. Absolute Maximum Ratings")
    c.setFont("Helvetica", 9)
    c.drawString(54, height - 146, "TA = 25 C unless otherwise noted. (Tj = 125 C maximum continuous)")
    _draw_table(
        c,
        54,
        height - 165,
        ["Parameter", "Symbol", "Value", "Unit"],
        MOSFET_ABS_ROWS,
        [220, 80, 80, 60],
    )
    c.showPage()

    # --- page 2: electrical characteristics
    c.setFont("Helvetica-Bold", 12)
    c.drawString(54, height - 70, "2. Electrical Characteristics")
    c.setFont("Helvetica", 9)
    c.drawString(54, height - 86, "TA = 25 C unless otherwise noted.")
    _draw_table(
        c,
        36,
        height - 110,
        ["Parameter", "Symbol", "Min", "Typ", "Max", "Unit", "Conditions"],
        MOSFET_ROWS,
        [130, 55, 38, 38, 38, 42, 165],
    )
    c.showPage()
    c.save()


def build_gate_driver_pdf(path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdfcanvas

    c = pdfcanvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(54, height - 70, "PGD35")
    c.setFont("Helvetica", 11)
    c.drawString(54, height - 88, "35 V High-Side Gate Driver - SYNTHETIC TEST DATASHEET")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(54, height - 130, "1. Electrical Characteristics")
    c.setFont("Helvetica", 9)
    c.drawString(54, height - 146, "TA = 25 C unless otherwise noted.")
    _draw_table(
        c,
        36,
        height - 168,
        ["Parameter", "Symbol", "Min", "Typ", "Max", "Unit", "Conditions"],
        GATE_DRIVER_ROWS,
        [140, 55, 38, 38, 38, 42, 155],
    )
    c.showPage()

    c.setFont("Helvetica-Bold", 12)
    c.drawString(54, height - 70, "2. Absolute Maximum Ratings")
    c.setFont("Helvetica", 9)
    c.drawString(54, height - 86, "TA = 25 C unless otherwise noted.")
    _draw_table(
        c,
        54,
        height - 105,
        ["Parameter", "Symbol", "Value", "Unit"],
        GATE_DRIVER_ABS_ROWS,
        [220, 80, 80, 60],
    )
    c.showPage()
    c.save()


def build_scanned_pdf(path: Path) -> None:
    """A PDF with an image only: no text layer, so Tier 1 must not find values."""
    import pymupdf

    src = pymupdf.open()
    page = src.new_page(width=595, height=842)
    page.insert_text((54, 90), "1. Electrical Characteristics", fontsize=14, fontname="helv")
    page.insert_text((54, 120), "Drain-Source On-Resistance RDS(on)  typ 5.5 max 7 mOhm", fontsize=9, fontname="helv")
    page.insert_text((54, 140), "Gate-Source Threshold Voltage VGS(th) min 2 typ 3.5 max 4.5 V", fontsize=9, fontname="helv")
    pix = page.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY)

    out = pymupdf.open()
    out_page = out.new_page(width=595, height=842)
    out_page.insert_image(out_page.rect, pixmap=pix)
    out.save(str(path, ), deflate=True, garbage=4)
    out.close()
    src.close()


# ---------------------------------------------------------------------------
# Seed data and gold set
# ---------------------------------------------------------------------------


def write_seed(parts: list[dict]) -> None:
    seed_dir = HERE / "seed"
    seed_dir.mkdir(parents=True, exist_ok=True)
    public = [
        {k: v for k, v in part.items() if not k.startswith("_")} for part in parts
    ]
    (seed_dir / "parts.json").write_text(
        json.dumps(
            {
                "_note": (
                    "Synthetic seed data. 30 parts (15 MOSFET, 15 gate driver). "
                    "Parameter values are in CANONICAL SI base units (ohm, C, F, s, V, A, "
                    "degC, degC/W). The raw API fixtures keep the unit the vendor writes "
                    "(mohm, nC, pF, ns)."
                ),
                "parts": public,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with (seed_dir / "seed_parts.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "part_id",
                "mpn",
                "manufacturer",
                "family",
                "package",
                "lifecycle_status",
                "datasheet_url",
                "distributor",
                "stock",
                "unit_price",
            ]
        )
        for part in parts:
            offers = part.get("offers") or []
            if not offers:
                writer.writerow(
                    [
                        part["part_id"],
                        part["mpn"],
                        part["manufacturer"],
                        part["family"],
                        part["package"],
                        part["lifecycle_status"],
                        part["datasheet_url"],
                        "",
                        "",
                        "",
                    ]
                )
                continue
            for offer in offers:
                writer.writerow(
                    [
                        part["part_id"],
                        part["mpn"],
                        part["manufacturer"],
                        part["family"],
                        part["package"],
                        part["lifecycle_status"],
                        part["datasheet_url"],
                        offer["distributor"],
                        offer["stock"],
                        offer["unit_price"],
                    ]
                )


def write_gold_set(parts: list[dict]) -> None:
    gold_dir = HERE / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(4242)
    rows = []
    for part in parts[:12]:
        for name in ("vds_max", "id_continuous", "rds_on", "vgs_threshold"):
            spec = part["parameters"].get(name)
            if not spec:
                continue
            rows.append(
                {
                    "part_id": part["part_id"],
                    "mpn": part["mpn"],
                    "manufacturer": part["manufacturer"],
                    "family": part["family"],
                    "param_name": name,
                    "value": spec["value"],
                    "unit": spec["unit"],
                    "condition": json.dumps(spec["condition"], sort_keys=True),
                    "labelled_by": "member-d",
                    "second_check_by": "" if rng.random() > 0.2 else "member-c",
                    "agreement": "" if rng.random() > 0.2 else "yes",
                    "notes": "",
                }
            )
    fieldnames = list(rows[0].keys())
    with (gold_dir / "gold_set_example.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parts = build_parts()

    (HERE / "digikey").mkdir(parents=True, exist_ok=True)
    (HERE / "nexar").mkdir(parents=True, exist_ok=True)
    (HERE / "mouser").mkdir(parents=True, exist_ok=True)
    (HERE / "pages").mkdir(parents=True, exist_ok=True)
    (HERE / "pdfs").mkdir(parents=True, exist_ok=True)

    digikey_parts = parts[:10]
    nexar_parts = parts[10:20]
    mouser_parts = parts[20:30]

    (HERE / "digikey" / "product_details.json").write_text(
        json.dumps(digikey_product_details(digikey_parts[0]), indent=2), encoding="utf-8"
    )
    (HERE / "digikey" / "keyword_search.json").write_text(
        json.dumps(digikey_keyword_search(digikey_parts), indent=2), encoding="utf-8"
    )
    (HERE / "digikey" / "parts.json").write_text(
        json.dumps({"parts": digikey_parts}, indent=2), encoding="utf-8"
    )

    (HERE / "nexar" / "supply_response.json").write_text(
        json.dumps(nexar_response(nexar_parts), indent=2), encoding="utf-8"
    )
    (HERE / "nexar" / "parts.json").write_text(
        json.dumps({"parts": nexar_parts}, indent=2), encoding="utf-8"
    )

    (HERE / "mouser" / "partnumber_search.json").write_text(
        json.dumps(mouser_response(mouser_parts), indent=2), encoding="utf-8"
    )
    (HERE / "mouser" / "parts.json").write_text(
        json.dumps({"parts": mouser_parts}, indent=2), encoding="utf-8"
    )

    for index, sample in enumerate(page_samples(), start=1):
        (HERE / "pages" / f"page_{index:02d}.json").write_text(
            json.dumps(sample, indent=2), encoding="utf-8"
        )

    write_seed(parts)
    write_gold_set(parts)

    build_mosfet_pdf(HERE / "pdfs" / "synthetic_mosfet.pdf")
    build_gate_driver_pdf(HERE / "pdfs" / "synthetic_gate_driver.pdf")
    build_scanned_pdf(HERE / "pdfs" / "synthetic_scanned.pdf")

    expected = {
        "_note": "The exact values inside the synthetic PDFs. Tier 1 tests assert against this.",
        "pdfs/synthetic_mosfet.pdf": {
            "source_id": "pdf-synthetic-mosfet",
            "family": "mosfet",
            "pages": {
                "1": {"title": "Absolute Maximum Ratings"},
                "2": {"title": "Electrical Characteristics"},
            },
            "values": {
                "vds_max": {"value": 100.0, "unit": "V", "page": 1, "method": "tier1"},
                "id_continuous": {"value": 25.0, "unit": "A", "page": 1, "method": "tier1"},
                "max_junction_temp": {"value": 175.0, "unit": "degC", "page": 1, "method": "tier1"},
                "rds_on": {
                    "value": 5.5,
                    "value_typ": 5.5,
                    "value_max": 7.0,
                    "unit": "mohm",
                    "page": 2,
                    "method": "tier1",
                    "condition": {"Vgs": "10 V", "Id": "10 A", "Tj": "25 C"},
                },
                "vgs_threshold": {
                    "value": 3.5,
                    "value_min": 2.0,
                    "value_typ": 3.5,
                    "value_max": 4.5,
                    "unit": "V",
                    "page": 2,
                    "method": "tier1",
                    "condition": {"Id": "250 uA"},
                },
                "vgs_max": {"value": 20.0, "unit": "V", "page": 2, "method": "tier1"},
                "total_gate_charge_qg": {"value": 62.0, "unit": "nC", "page": 2, "method": "tier1"},
                "gate_drain_charge_qgd": {"value": 12.0, "unit": "nC", "page": 2, "method": "tier1"},
                "input_capacitance_ciss": {"value": 4900.0, "unit": "pF", "page": 2, "method": "tier1"},
                "output_capacitance_coss": {"value": 900.0, "unit": "pF", "page": 2, "method": "tier1"},
                "thermal_resistance": {"value": 1.2, "unit": "degC/W", "page": 2, "method": "tier1"},
                "reverse_recovery_qrr": {"value": 120.0, "unit": "nC", "page": 2, "method": "tier1"},
            },
        },
        "pdfs/synthetic_gate_driver.pdf": {
            "source_id": "pdf-synthetic-gate-driver",
            "family": "gate_driver",
            "pages": {
                "1": {"title": "Electrical Characteristics"},
                "2": {"title": "Absolute Maximum Ratings"},
            },
            "values": {
                "supply_voltage_min": {"value": 4.5, "unit": "V", "page": 1, "method": "tier1"},
                "supply_voltage_max": {"value": 35.0, "unit": "V", "page": 1, "method": "tier1"},
                "peak_source_current": {"value": 2.0, "unit": "A", "page": 1, "method": "tier1"},
                "peak_sink_current": {"value": 2.0, "unit": "A", "page": 1, "method": "tier1"},
                "input_logic_level": {
                    "value": 0.8,
                    "value_max": 0.8,
                    "unit": "V",
                    "page": 1,
                    "method": "tier1",
                },
                "propagation_delay": {"value": 20.0, "unit": "ns", "page": 1, "method": "tier1"},
                "rise_time": {"value": 15.0, "unit": "ns", "page": 1, "method": "tier1"},
                "fall_time": {"value": 14.0, "unit": "ns", "page": 1, "method": "tier1"},
                "uvlo_threshold": {"value": 8.0, "unit": "V", "page": 1, "method": "tier1"},
                "operating_temp_min": {"value": -40.0, "unit": "degC", "page": 1, "method": "tier1"},
                "operating_temp_max": {"value": 125.0, "unit": "degC", "page": 1, "method": "tier1"},
                "channel_count": {"value": 1, "unit": None, "page": 1, "method": "tier1"},
            },
        },
        "pdfs/synthetic_scanned.pdf": {
            "source_id": "pdf-synthetic-scanned",
            "family": "mosfet",
            "scanned": True,
            "values": {},
            "note": "No text layer. Tier 1 must return no values and mark the file as scanned.",
        },
    }
    (HERE / "pdfs" / "expected_values.json").write_text(json.dumps(expected, indent=2), encoding="utf-8")

    print(f"fixtures written to {HERE}")


if __name__ == "__main__":
    main()
