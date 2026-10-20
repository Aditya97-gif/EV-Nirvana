"""
pipeline/ingest/substations.py  +  candidate_sites.py combined
Phase 5 — Fetch OSM substations and candidate charger sites (fuel stations, malls, parking).
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
RAW_DIR = ROOT / "data" / "raw" / "osm_extras"
RAW_DIR.mkdir(parents=True, exist_ok=True)

with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

STATE = CONFIG["state"]
OVERPASS_URL = os.environ.get("OVERPASS_URL", CONFIG.get("overpass_url", "https://overpass-api.de/api/interpreter"))
RATE_LIMIT_S = CONFIG.get("overpass_rate_limit_s", 2)

DB_URL = (
    f"postgresql+psycopg2://{os.environ.get('DB_USER','evuser')}:"
    f"{os.environ.get('DB_PASSWORD','password')}@"
    f"{os.environ.get('DB_HOST','db')}:"
    f"{os.environ.get('DB_PORT','5432')}/"
    f"{os.environ.get('DB_NAME','ev_infra')}"
)

HEADERS = {"User-Agent": "EV_Nirvana/1.0"}


def overpass_query(state: str, filter_str: str, tag: str) -> list:
    cache_path = RAW_DIR / f"{tag}_{state.replace(' ','_')}_{datetime.utcnow().strftime('%Y%m%d')}.json"
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)

    query = f"""
[out:json][timeout:120];
area["name"="{state}"]["admin_level"="4"]->.s;
({filter_str}(area.s););
out center tags;
"""
    time.sleep(RATE_LIMIT_S)
    try:
        resp = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=150)
        resp.raise_for_status()
        els = resp.json().get("elements", [])
        cache_path.write_text(json.dumps(els), encoding="utf-8")
        logger.info("Fetched %d elements for %s", len(els), tag)
        return els
    except Exception as e:
        logger.error("Overpass failed for %s: %s", tag, e)
        return []


def load_substations(elements: list) -> None:
    engine = create_engine(DB_URL, pool_pre_ping=True)
    inserted = 0
    with engine.begin() as conn:
        for el in elements:
            tags = el.get("tags", {})
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None or lon is None:
                continue
            voltage_raw = tags.get("voltage", "")
            try:
                voltage_kv = float(voltage_raw.split(";")[0]) / 1000
            except Exception:
                voltage_kv = None
            conn.execute(text("""
                INSERT INTO clean.substations (osm_id, name, voltage_kv, geom, data_status)
                VALUES (:osm_id, :name, :voltage_kv, ST_SetSRID(ST_MakePoint(:lon,:lat),4326), 'observed')
            """), {
                "osm_id": el.get("id"), "name": tags.get("name"),
                "voltage_kv": voltage_kv, "lat": lat, "lon": lon,
            })
            inserted += 1
    logger.info("Inserted %d substations", inserted)


def load_candidate_sites(elements: list, site_type: str) -> None:
    engine = create_engine(DB_URL, pool_pre_ping=True)
    inserted = 0
    with engine.begin() as conn:
        for el in elements:
            tags = el.get("tags", {})
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None or lon is None:
                continue
            conn.execute(text("""
                INSERT INTO clean.candidate_sites (type, name, geom, source)
                VALUES (:type, :name, ST_SetSRID(ST_MakePoint(:lon,:lat),4326), 'osm')
            """), {
                "type": site_type,
                "name": tags.get("name"),
                "lat": lat, "lon": lon,
            })
            inserted += 1
    logger.info("Inserted %d candidate sites of type '%s'", inserted, site_type)


def main():
    logger.info("=== Substations + Candidate Sites Ingestion for %s ===", STATE)

    # Substations
    sub_els = overpass_query(STATE, 'node["power"="substation"]\n  way["power"="substation"]', "substations")
    load_substations(sub_els)

    # Fuel stations
    fuel_els = overpass_query(STATE, 'node["amenity"="fuel"]\n  way["amenity"="fuel"]', "fuel")
    load_candidate_sites(fuel_els, "fuel")

    # Malls
    mall_els = overpass_query(STATE, 'node["shop"="mall"]\n  way["shop"="mall"]', "mall")
    load_candidate_sites(mall_els, "mall")

    # Parking
    park_els = overpass_query(STATE, 'node["amenity"="parking"]\n  way["amenity"="parking"]', "parking")
    load_candidate_sites(park_els, "parking")

    # Highway service areas
    hw_els = overpass_query(STATE, 'node["highway"="services"]\n  way["highway"="services"]', "highway_service")
    load_candidate_sites(hw_els, "highway_service")

    logger.info("Substations + candidate sites ingestion complete.")


if __name__ == "__main__":
    main()
