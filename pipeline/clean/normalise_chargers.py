"""
pipeline/clean/normalise_chargers.py
Phase 3 — Normalise raw charger records:
  - Operator name canonicalisation (alias dict + rapidfuzz)
  - Connector type standardisation to canonical set
  - Power in kW, AC/DC classification
"""
import logging
import os
from pathlib import Path

import yaml
from rapidfuzz import process, fuzz
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(os.environ.get("PROJECT_ROOT", str(Path(__file__).resolve().parents[3])))
with open(ROOT / "config" / "project.yaml") as f:
    CONFIG = yaml.safe_load(f)

DB_URL = (
    f"postgresql+psycopg2://{os.environ.get('DB_USER','evuser')}:"
    f"{os.environ.get('DB_PASSWORD','password')}@"
    f"{os.environ.get('DB_HOST','db')}:"
    f"{os.environ.get('DB_PORT','5432')}/"
    f"{os.environ.get('DB_NAME','ev_infra')}"
)

# Canonical operator aliases (extend as data is loaded)
OPERATOR_ALIASES: dict[str, str] = {
    "tata power": "Tata Power EV",
    "tata power ev": "Tata Power EV",
    "tata": "Tata Power EV",
    "ather": "Ather Energy",
    "ather energy": "Ather Energy",
    "charge zone": "ChargeZone",
    "chargezone": "ChargeZone",
    "statiq": "Statiq",
    "static": "Statiq",
    "fortum": "Fortum Charge & Drive",
    "fortum charge": "Fortum Charge & Drive",
    "bpcl": "BPCL",
    "bharat petroleum": "BPCL",
    "hpcl": "HPCL",
    "hindustan petroleum": "HPCL",
    "reliance": "Reliance BP Mobility",
    "exicom": "Exicom",
    "okaya": "Okaya Power",
    "delta": "Delta Electronics",
    "jio-bp": "Jio-bp",
    "jiobp": "Jio-bp",
    "bescom": "BESCOM",
    "mahadiscom": "MSEDCL",
    "msedcl": "MSEDCL",
    "eesl": "EESL",
    "energy efficiency services": "EESL",
    "ola electric": "Ola Electric",
    "hero electric": "Hero Electric",
    "kazam": "Kazam",
    "volttic": "Volttic",
    "charzer": "Charzer",
    "magenta": "Magenta Mobility",
}

CANONICAL_OPERATORS = list(set(OPERATOR_ALIASES.values()))

# Connector type canonicalisation
CONNECTOR_MAP: dict[str, str] = {
    "ccs": "CCS2", "ccs2": "CCS2", "ccs 2": "CCS2",
    "chademo": "CHAdeMO", "chademo ": "CHAdeMO",
    "type2": "Type2", "type 2": "Type2", "mennekes": "Type2",
    "gbt": "GB/T", "gb/t": "GB/T",
    "bharat ac": "Bharat AC-001", "bharat ac-001": "Bharat AC-001",
    "bharat dc": "Bharat DC-001", "bharat dc-001": "Bharat DC-001",
    "3pin": "3-pin", "3-pin": "3-pin", "type1": "Type1",
    "unknown": "unknown",
}


def canonicalise_operator(raw: str | None) -> str | None:
    if not raw:
        return None
    lower = raw.lower().strip()
    if lower in OPERATOR_ALIASES:
        return OPERATOR_ALIASES[lower]
    # Fuzzy match
    result = process.extractOne(lower, list(OPERATOR_ALIASES.keys()), scorer=fuzz.token_sort_ratio, score_cutoff=80)
    if result:
        return OPERATOR_ALIASES[result[0]]
    return raw.strip()


def canonicalise_connectors(types: list | None) -> list[str]:
    if not types:
        return ["unknown"]
    canonical = []
    for t in types:
        lower = str(t).lower().strip()
        canonical.append(CONNECTOR_MAP.get(lower, t))
    return list(set(canonical)) or ["unknown"]


def determine_current_type(power_kw: float | None, connector_types: list[str], raw_current: str | None) -> str:
    if raw_current and raw_current.upper() in ("AC", "DC", "AC/DC"):
        return raw_current.upper()
    dc_connectors = {"CCS2", "CHAdeMO", "GB/T", "Bharat DC-001"}
    if any(c in dc_connectors for c in connector_types):
        return "DC"
    if power_kw and power_kw >= 22:
        return "DC"
    return "AC"


def normalise(engine) -> None:
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT id, operator, connector_types, power_kw, current_type FROM raw.chargers_raw"
        )).fetchall()

        for row in rows:
            norm_op = canonicalise_operator(row.operator)
            norm_ct = canonicalise_connectors(row.connector_types)
            norm_cur = determine_current_type(row.power_kw, norm_ct, row.current_type)
            conn.execute(text("""
                UPDATE raw.chargers_raw
                SET operator = :op, connector_types = :ct, current_type = :cur
                WHERE id = :id
            """), {"op": norm_op, "ct": norm_ct, "cur": norm_cur, "id": row.id})

    logger.info("Normalised %d charger records.", len(rows))


def main():
    logger.info("=== Charger Normalisation ===")
    engine = create_engine(DB_URL, pool_pre_ping=True)
    normalise(engine)


if __name__ == "__main__":
    main()
