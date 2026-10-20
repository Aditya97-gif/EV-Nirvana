"""
pipeline/ingest/gov_chargers.py
Phase 2 — Attempt to ingest government/open-data charger lists.
Sources tried in order:
  1. data.gov.in search for EV charging datasets
  2. BEE (Bureau of Energy Efficiency) open listings (if available)
Falls back gracefully; logs to OPEN_QUESTIONS if no usable file found.
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path

import requests
import yaml
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(os.environ.get("PROJECT_ROOT", str(Path(__file__).resolve().parents[3])))
CONFIG_PATH = ROOT / "config" / "project.yaml"
RAW_DIR = ROOT / "data" / "raw" / "gov"
RAW_DIR.mkdir(parents=True, exist_ok=True)

with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

STATE = CONFIG["state"]

DB_URL = (
    f"postgresql+psycopg2://{os.environ.get('DB_USER','evuser')}:"
    f"{os.environ.get('DB_PASSWORD','password')}@"
    f"{os.environ.get('DB_HOST','db')}:"
    f"{os.environ.get('DB_PORT','5432')}/"
    f"{os.environ.get('DB_NAME','ev_infra')}"
)

# Known public datasets from data.gov.in (verified manually; may move)
KNOWN_GOV_DATASETS = [
    {
        "name": "data.gov.in EV Charging Stations",
        "url": "https://data.gov.in/resource/electric-vehicle-charging-stations",
        "note": "Check manually; API key may be required.",
    },
]


def attempt_gov_fetch() -> list:
    """Try to download a usable CSV/JSON from known government URLs."""
    import csv, io
    headers = {"User-Agent": "EV_Nirvana/1.0"}
    for ds in KNOWN_GOV_DATASETS:
        try:
            resp = requests.get(ds["url"], headers=headers, timeout=30)
            resp.raise_for_status()
            # Try JSON
            try:
                data = resp.json()
                if isinstance(data, list):
                    cache = RAW_DIR / f"gov_{datetime.utcnow().strftime('%Y%m%d')}.json"
                    cache.write_text(json.dumps(data), encoding="utf-8")
                    logger.info("Saved gov dataset: %s", cache)
                    return data
            except Exception:
                pass
            # Try CSV
            text_data = resp.text
            reader = csv.DictReader(io.StringIO(text_data))
            rows = list(reader)
            if rows:
                cache = RAW_DIR / f"gov_{datetime.utcnow().strftime('%Y%m%d')}.csv"
                cache.write_text(text_data, encoding="utf-8")
                logger.info("Saved gov CSV: %s", cache)
                return rows
        except Exception as e:
            logger.warning("Gov dataset fetch failed (%s): %s", ds["name"], e)

    # Check if user manually dropped files
    manual = list(RAW_DIR.glob("*.csv")) + list(RAW_DIR.glob("*.json"))
    if manual:
        logger.info("Found manually placed gov file: %s", manual[0])
        import csv, io
        if manual[0].suffix == ".json":
            with open(manual[0]) as f:
                return json.load(f)
        else:
            with open(manual[0]) as f:
                return list(csv.DictReader(f))

    return []


def log_open_question():
    oq = ROOT / "docs" / "OPEN_QUESTIONS.md"
    oq.parent.mkdir(parents=True, exist_ok=True)
    with open(oq, "a") as f:
        f.write(
            "\n## Government charger dataset not found\n"
            "- Checked: data.gov.in EV Charging Stations\n"
            "- Action: Download manually from https://data.gov.in and place in data/raw/gov/\n"
            "- Also check: BEE EVSE portal, MoP public reports\n"
            "- Impact: Only OSM (+OCM if key provided) will be the source. "
            "Gov data would increase coverage confidence.\n"
        )


def infer_lat_lon(row: dict) -> tuple[float | None, float | None]:
    """Try common column name patterns for lat/lon."""
    lat_keys = ["lat", "latitude", "Latitude", "LAT", "y"]
    lon_keys = ["lon", "lng", "longitude", "Longitude", "LON", "LNG", "x"]
    lat = next((float(row[k]) for k in lat_keys if k in row and row[k]), None)
    lon = next((float(row[k]) for k in lon_keys if k in row and row[k]), None)
    return lat, lon


def load_into_db(rows: list) -> None:
    if not rows:
        return
    engine = create_engine(DB_URL, pool_pre_ping=True)
    inserted = 0
    fetched_at = datetime.utcnow().isoformat()
    with engine.begin() as conn:
        for row in rows:
            lat, lon = infer_lat_lon(row)
            if lat is None or lon is None:
                continue
            conn.execute(text("""
                INSERT INTO raw.chargers_raw
                    (source, source_id, name, operator, lat, lon,
                     connector_types, power_kw, current_type, status, fetched_at, raw_payload)
                VALUES
                    ('gov', :sid, :name, :operator, :lat, :lon,
                     :connector_types, :power_kw, :current_type, :status, :fetched_at, :raw_payload)
            """), {
                "sid": str(row.get("id") or row.get("ID") or ""),
                "name": row.get("name") or row.get("Name") or row.get("station_name"),
                "operator": row.get("operator") or row.get("Operator"),
                "lat": lat, "lon": lon,
                "connector_types": ["unknown"],
                "power_kw": None,
                "current_type": None,
                "status": row.get("status") or "unknown",
                "fetched_at": fetched_at,
                "raw_payload": json.dumps(row),
            })
            inserted += 1
    logger.info("Inserted %d gov chargers into raw.chargers_raw", inserted)


def main():
    logger.info("=== Gov Charger Ingestion for %s ===", STATE)
    rows = attempt_gov_fetch()
    if not rows:
        logger.warning("No usable gov charger data found. Logging to OPEN_QUESTIONS.")
        log_open_question()
    else:
        load_into_db(rows)


if __name__ == "__main__":
    main()
