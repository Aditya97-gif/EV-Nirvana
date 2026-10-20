"""
pipeline/ingest/osm_chargers.py
Phase 2 — Fetch EV charging stations from OpenStreetMap via Overpass API.
Rate-limited, cached, polite user-agent.
Licence: ODbL — attribution required in map footer.
"""
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(os.environ.get("PROJECT_ROOT", str(Path(__file__).resolve().parents[3])))
CONFIG_PATH = ROOT / "config" / "project.yaml"
RAW_DIR = ROOT / "data" / "raw" / "osm"
RAW_DIR.mkdir(parents=True, exist_ok=True)

with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

OVERPASS_URL = os.environ.get("OVERPASS_URL", CONFIG.get("overpass_url", "https://overpass-api.de/api/interpreter"))
RATE_LIMIT_S = CONFIG.get("overpass_rate_limit_s", 2)
STATE = CONFIG["state"]

DB_URL = (
    f"postgresql+psycopg2://{os.environ.get('DB_USER','evuser')}:"
    f"{os.environ.get('DB_PASSWORD','password')}@"
    f"{os.environ.get('DB_HOST','db')}:"
    f"{os.environ.get('DB_PORT','5432')}/"
    f"{os.environ.get('DB_NAME','ev_infra')}"
)

HEADERS = {"User-Agent": "EV_Nirvana/1.0"}


def build_overpass_query(state: str) -> str:
    """Build Overpass QL query for EV charging stations in the given state."""
    return f"""
[out:json][timeout:120];
area["name"="{state}"]["admin_level"="4"]->.searchArea;
(
  node["amenity"="charging_station"](area.searchArea);
  way["amenity"="charging_station"](area.searchArea);
  relation["amenity"="charging_station"](area.searchArea);
);
out center tags;
"""


def fetch_osm_chargers(state: str) -> dict:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    cache_path = RAW_DIR / f"osm_chargers_{state.replace(' ','_')}_{timestamp}.json"

    # Check for any recent cache (within same day)
    existing = sorted(RAW_DIR.glob(f"osm_chargers_{state.replace(' ','_')}_*.json"))
    if existing:
        today_str = datetime.utcnow().strftime("%Y%m%d")
        recent = [p for p in existing if today_str in p.name]
        if recent:
            logger.info("Using today's cached OSM data: %s", recent[-1])
            with open(recent[-1]) as f:
                return json.load(f)

    logger.info("Querying Overpass API for %s (rate limit: %ds)...", state, RATE_LIMIT_S)
    time.sleep(RATE_LIMIT_S)

    query = build_overpass_query(state)
    try:
        resp = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers=HEADERS,
            timeout=150,
        )
        resp.raise_for_status()
        data = resp.json()
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        logger.info("Saved %d OSM elements to %s", len(data.get("elements", [])), cache_path)
        return data
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            logger.error("Rate limited by Overpass — stopping as instructed.")
        else:
            logger.error("Overpass HTTP error: %s", e)
        raise


def parse_connector_types(tags: dict) -> list[str]:
    connectors = []
    for key in tags:
        if key.startswith("socket:") and tags[key] not in ("0", "no"):
            connectors.append(key.replace("socket:", ""))
    return connectors or ["unknown"]


def parse_power_kw(tags: dict) -> float | None:
    raw = tags.get("charging_station:output") or tags.get("maxpower") or tags.get("capacity:electric")
    if not raw:
        return None
    try:
        val = float(raw.lower().replace("kw", "").replace("kva", "").strip())
        return val
    except (ValueError, AttributeError):
        return None


def load_into_db(elements: list, fetched_at: str) -> None:
    engine = create_engine(DB_URL, pool_pre_ping=True)
    inserted = 0
    with engine.begin() as conn:
        for el in elements:
            tags = el.get("tags", {})
            lat = el.get("lat") or (el.get("center", {}) or {}).get("lat")
            lon = el.get("lon") or (el.get("center", {}) or {}).get("lon")
            if lat is None or lon is None:
                continue

            conn.execute(text("""
                INSERT INTO raw.chargers_raw
                    (source, source_id, name, operator, lat, lon,
                     connector_types, power_kw, current_type, status, fetched_at, raw_payload)
                VALUES
                    ('osm', :source_id, :name, :operator, :lat, :lon,
                     :connector_types, :power_kw, :current_type, :status, :fetched_at, :raw_payload)
            """), {
                "source_id": str(el.get("id")),
                "name": tags.get("name"),
                "operator": tags.get("operator") or tags.get("brand"),
                "lat": lat,
                "lon": lon,
                "connector_types": parse_connector_types(tags),
                "power_kw": parse_power_kw(tags),
                "current_type": "DC" if "dc" in str(tags).lower() else "AC",
                "status": tags.get("opening_hours:signed") or "unknown",
                "fetched_at": fetched_at,
                "raw_payload": json.dumps(el),
            })
            inserted += 1
    logger.info("Inserted %d OSM chargers into raw.chargers_raw", inserted)


def main():
    logger.info("=== OSM Charger Ingestion for %s ===", STATE)
    data = fetch_osm_chargers(STATE)
    elements = data.get("elements", [])
    logger.info("Retrieved %d elements from OSM", len(elements))
    fetched_at = datetime.utcnow().isoformat()
    load_into_db(elements, fetched_at)


if __name__ == "__main__":
    main()
