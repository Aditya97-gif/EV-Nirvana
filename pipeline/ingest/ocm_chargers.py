"""
pipeline/ingest/ocm_chargers.py
Phase 2 — Fetch EV charging stations from Open Charge Map (OCM) public API.
API key required (set OCM_API_KEY in .env). If missing, logs to OPEN_QUESTIONS and exits.
Licence: Creative Commons CC-BY-SA — attribution required.
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
RAW_DIR = ROOT / "data" / "raw" / "ocm"
RAW_DIR.mkdir(parents=True, exist_ok=True)

with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

STATE = CONFIG["state"]
OCM_API_KEY = os.environ.get("OCM_API_KEY", "")
OCM_BASE = "https://api.openchargemap.io/v3/poi/"
RATE_LIMIT_S = 2

DB_URL = (
    f"postgresql+psycopg2://{os.environ.get('DB_USER','evuser')}:"
    f"{os.environ.get('DB_PASSWORD','password')}@"
    f"{os.environ.get('DB_HOST','db')}:"
    f"{os.environ.get('DB_PORT','5432')}/"
    f"{os.environ.get('DB_NAME','ev_infra')}"
)

# Bounding boxes for Indian states — Maharashtra
STATE_BBOX = {
    "Maharashtra": {"minlat": 15.6, "maxlat": 22.1, "minlong": 72.6, "maxlong": 80.9},
}


def fetch_ocm(state: str) -> list:
    if not OCM_API_KEY or OCM_API_KEY == "YOUR_OCM_API_KEY_HERE":
        logger.warning("OCM_API_KEY not set. Skipping OCM ingestion.")
        oq = ROOT / "docs" / "OPEN_QUESTIONS.md"
        oq.parent.mkdir(parents=True, exist_ok=True)
        with open(oq, "a") as f:
            f.write(
                "\n## Open Charge Map API key missing\n"
                "- Action: Register at https://openchargemap.org/site/develop and set OCM_API_KEY in .env\n"
                "- Impact: OCM charger data not ingested. OSM remains the primary source.\n"
            )
        return []

    bbox = STATE_BBOX.get(state, STATE_BBOX["Maharashtra"])
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    cache_path = RAW_DIR / f"ocm_{state.replace(' ','_')}_{timestamp}.json"

    existing = sorted(RAW_DIR.glob(f"ocm_{state.replace(' ','_')}_*.json"))
    if existing:
        today_str = datetime.utcnow().strftime("%Y%m%d")
        recent = [p for p in existing if today_str in p.name]
        if recent:
            logger.info("Using cached OCM data: %s", recent[-1])
            with open(recent[-1]) as f:
                return json.load(f)

    logger.info("Fetching OCM data for %s...", state)
    time.sleep(RATE_LIMIT_S)

    params = {
        "key": OCM_API_KEY,
        "output": "json",
        "countrycode": "IN",
        "maxresults": 10000,
        "compact": True,
        "verbose": False,
        **bbox,
    }

    try:
        resp = requests.get(
            OCM_BASE, params=params, timeout=60,
            headers={"User-Agent": "EV_Nirvana/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()
        cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        logger.info("Saved %d OCM POIs to %s", len(data), cache_path)
        return data
    except Exception as e:
        logger.error("OCM fetch failed: %s", e)
        return []


def load_into_db(pois: list) -> None:
    if not pois:
        return
    engine = create_engine(DB_URL, pool_pre_ping=True)
    inserted = 0
    fetched_at = datetime.utcnow().isoformat()
    with engine.begin() as conn:
        for poi in pois:
            addr = poi.get("AddressInfo", {}) or {}
            connections = poi.get("Connections") or []
            connector_types = list({
                (c.get("ConnectionType") or {}).get("Title", "unknown")
                for c in connections
            })
            max_kw = max(
                (c.get("PowerKW") or 0 for c in connections), default=None
            ) or None
            current_type = None
            for c in connections:
                ct = ((c.get("CurrentType") or {}).get("Description") or "").upper()
                if "DC" in ct:
                    current_type = "DC"
                    break
                elif "AC" in ct:
                    current_type = "AC"

            lat = addr.get("Latitude")
            lon = addr.get("Longitude")
            if lat is None or lon is None:
                continue

            conn.execute(text("""
                INSERT INTO raw.chargers_raw
                    (source, source_id, name, operator, lat, lon,
                     connector_types, power_kw, current_type, status, fetched_at, raw_payload)
                VALUES
                    ('ocm', :sid, :name, :operator, :lat, :lon,
                     :connector_types, :power_kw, :current_type, :status, :fetched_at, :raw_payload)
            """), {
                "sid": str(poi.get("ID")),
                "name": addr.get("Title"),
                "operator": (poi.get("OperatorInfo") or {}).get("Title"),
                "lat": lat, "lon": lon,
                "connector_types": connector_types,
                "power_kw": max_kw,
                "current_type": current_type,
                "status": (poi.get("StatusType") or {}).get("Title"),
                "fetched_at": fetched_at,
                "raw_payload": json.dumps(poi),
            })
            inserted += 1
    logger.info("Inserted %d OCM chargers into raw.chargers_raw", inserted)


def main():
    logger.info("=== OCM Charger Ingestion for %s ===", STATE)
    pois = fetch_ocm(STATE)
    load_into_db(pois)


if __name__ == "__main__":
    main()
