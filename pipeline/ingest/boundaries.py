"""
pipeline/ingest/boundaries.py
Phase 1 — Download and load state/district boundaries for the configured state.

Sources (in priority order):
  1. Cached local file (data/raw/boundaries/)
  2. geohacker/india GADM district GeoJSON (GitHub, CC BY) — filter by NAME_1
  3. DataMeet India (ODbL) — second fallback

IMPORTANT: geopandas read_file() cannot accept raw bytes — always save to disk first.
"""
import logging
import os
import sys
from pathlib import Path

import geopandas as gpd
import requests
import yaml
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(os.environ.get("PROJECT_ROOT", str(Path(__file__).resolve().parents[3])))
CONFIG_PATH = ROOT / "config" / "project.yaml"
RAW_DIR = ROOT / "data" / "raw" / "boundaries"
RAW_DIR.mkdir(parents=True, exist_ok=True)

with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

STATE = CONFIG["state"]
STATE_CODE = CONFIG["state_code"]

GADM_URL = "https://raw.githubusercontent.com/geohacker/india/master/district/india_district.geojson"
DATAMEET_BASE = "https://raw.githubusercontent.com/datameet/maps/master/Districts"

DB_URL = (
    f"postgresql+psycopg2://{os.environ.get('DB_USER','evuser')}:"
    f"{os.environ.get('DB_PASSWORD','password')}@"
    f"{os.environ.get('DB_HOST','db')}:"
    f"{os.environ.get('DB_PORT','5432')}/"
    f"{os.environ.get('DB_NAME','ev_infra')}"
)

HEADERS = {"User-Agent": "EV_Nirvana/1.0"}


def read_cached(path: Path):
    if path.exists():
        logger.info("Loading from cache: %s", path.name)
        try:
            return gpd.read_file(str(path))
        except Exception as e:
            logger.warning("Cache read failed: %s", e)
    return None


def fetch_gadm(state_name: str):
    """Download all-India GADM GeoJSON, save bytes to disk, filter to state."""
    filtered_cache = RAW_DIR / f"{STATE_CODE}_districts_gadm.geojson"
    raw_cache = RAW_DIR / "india_districts_raw.geojson"

    gdf = read_cached(filtered_cache)
    if gdf is not None:
        return gdf

    logger.info("Downloading all-India GADM from geohacker/india ...")
    try:
        r = requests.get(GADM_URL, timeout=90, headers=HEADERS)
        r.raise_for_status()
        logger.info("Downloaded %.1f MB — writing to disk ...", len(r.content) / 1e6)

        # Must write bytes to file — gpd.read_file does NOT accept raw bytes
        raw_cache.write_bytes(r.content)
        all_gdf = gpd.read_file(str(raw_cache))
        logger.info("Total GADM districts: %d", len(all_gdf))

        state_gdf = all_gdf[all_gdf["NAME_1"] == state_name].copy()
        if state_gdf.empty:
            state_gdf = all_gdf[all_gdf["NAME_1"].str.lower() == state_name.lower()].copy()

        if state_gdf.empty:
            logger.warning("'%s' not found. Available: %s", state_name,
                           sorted(all_gdf["NAME_1"].unique())[:10])
            return None

        state_gdf.to_file(str(filtered_cache), driver="GeoJSON")
        logger.info("Saved %d districts for %s.", len(state_gdf), state_name)
        return state_gdf

    except Exception as e:
        logger.warning("GADM fetch failed: %s", e, exc_info=True)
        return None


def fetch_datameet(state_code: str):
    """Fallback: DataMeet state GeoJSON."""
    url = f"{DATAMEET_BASE}/{state_code}.geojson"
    cache = RAW_DIR / f"{state_code}_datameet.geojson"
    gdf = read_cached(cache)
    if gdf is not None:
        return gdf
    logger.info("Trying DataMeet: %s", url)
    try:
        r = requests.get(url, timeout=30, headers=HEADERS)
        r.raise_for_status()
        cache.write_bytes(r.content)
        return gpd.read_file(str(cache))
    except Exception as e:
        logger.warning("DataMeet failed: %s", e)
        return None


def get_district_name(row) -> str:
    return (row.get("NAME_2") or row.get("DISTRICT") or
            row.get("district") or row.get("dtname") or
            row.get("name") or "Unknown")


def load_into_db(gdf: gpd.GeoDataFrame, state_name: str):
    engine = create_engine(DB_URL, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO clean.admin_units (level, name, data_status)
            VALUES ('state', :s, 'observed') ON CONFLICT DO NOTHING
        """), {"s": state_name})

        state_id = conn.execute(text(
            "SELECT id FROM clean.admin_units WHERE level='state' AND name=:n"
        ), {"n": state_name}).scalar()

        inserted = 0
        for _, row in gdf.iterrows():
            if not row.geometry or row.geometry.is_empty:
                continue
            conn.execute(text("""
                INSERT INTO clean.admin_units
                    (level, name, parent_id, geom, boundary_vintage, data_status)
                VALUES ('district', :name, :pid,
                        ST_Multi(ST_GeomFromText(:geom, 4326)), '2011+', 'observed')
                ON CONFLICT DO NOTHING
            """), {"name": get_district_name(row), "pid": state_id,
                   "geom": row.geometry.wkt})
            inserted += 1

        logger.info("Inserted %d districts for %s.", inserted, state_name)


def main():
    logger.info("=== Phase 1: Boundaries ingestion for %s ===", STATE)

    gdf = fetch_gadm(STATE)
    if gdf is None:
        gdf = fetch_datameet(STATE_CODE)

    if gdf is None:
        oq = ROOT / "docs" / "OPEN_QUESTIONS.md"
        with open(oq, "a") as f:
            f.write(
                f"\n## BLOCKED: boundaries for {STATE}\n"
                f"- Download GADM Level 2 India from https://gadm.org/download_country.html\n"
                f"- Place as data/raw/boundaries/{STATE_CODE}_districts_gadm.geojson\n"
            )
        logger.error("Boundaries blocked — see OPEN_QUESTIONS.md")
        sys.exit(0)

    gdf = gdf.to_crs("EPSG:4326")
    load_into_db(gdf, STATE)
    logger.info("Done — boundaries for %s loaded.", STATE)


if __name__ == "__main__":
    main()
