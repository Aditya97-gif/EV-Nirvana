"""
pipeline/ingest/population.py
Phase 5 — Load district population data.
Sources:
  1. Census 2011 district totals (embedded as constants — publicly available)
  2. WorldPop raster (zonal stats per district) — optional, requires raster download
"""
import logging
import os
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(os.environ.get("PROJECT_ROOT", str(Path(__file__).resolve().parents[3])))
CONFIG_PATH = ROOT / "config" / "project.yaml"

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

# Maharashtra district population from Census 2011 (public data, observed)
# Source: Office of the Registrar General, Census of India 2011
MAHARASHTRA_CENSUS_2011 = {
    "Mumbai": {"population": 3085411, "urban_share": 1.00},
    "Mumbai Suburban": {"population": 9356962, "urban_share": 1.00},
    "Thane": {"population": 11060148, "urban_share": 0.80},
    "Pune": {"population": 9429408, "urban_share": 0.69},
    "Nashik": {"population": 6107187, "urban_share": 0.44},
    "Aurangabad": {"population": 3701282, "urban_share": 0.50},
    "Nagpur": {"population": 4653570, "urban_share": 0.71},
    "Solapur": {"population": 4317756, "urban_share": 0.49},
    "Amravati": {"population": 2887826, "urban_share": 0.42},
    "Kolhapur": {"population": 3876001, "urban_share": 0.44},
    "Satara": {"population": 3003922, "urban_share": 0.29},
    "Sangli": {"population": 2822143, "urban_share": 0.41},
    "Ahmednagar": {"population": 4543159, "urban_share": 0.30},
    "Jalgaon": {"population": 4229917, "urban_share": 0.42},
    "Nanded": {"population": 3356566, "urban_share": 0.35},
    "Osmanabad": {"population": 1657576, "urban_share": 0.24},
    "Latur": {"population": 2454196, "urban_share": 0.39},
    "Beed": {"population": 2585962, "urban_share": 0.25},
    "Parbhani": {"population": 1836086, "urban_share": 0.37},
    "Hingoli": {"population": 1177345, "urban_share": 0.23},
    "Buldhana": {"population": 2586258, "urban_share": 0.28},
    "Washim": {"population": 1197160, "urban_share": 0.27},
    "Akola": {"population": 1818617, "urban_share": 0.53},
    "Yavatmal": {"population": 2772348, "urban_share": 0.28},
    "Wardha": {"population": 1300774, "urban_share": 0.40},
    "Chandrapur": {"population": 2194262, "urban_share": 0.37},
    "Gadchiroli": {"population": 1071795, "urban_share": 0.14},
    "Gondia": {"population": 1322507, "urban_share": 0.29},
    "Bhandara": {"population": 1198810, "urban_share": 0.27},
    "Dhule": {"population": 2050862, "urban_share": 0.39},
    "Nandurbar": {"population": 1648295, "urban_share": 0.22},
    "Raigad": {"population": 2634200, "urban_share": 0.37},
    "Ratnagiri": {"population": 1615069, "urban_share": 0.22},
    "Sindhudurg": {"population": 849651, "urban_share": 0.17},
}


def load_into_db() -> None:
    engine = create_engine(DB_URL, pool_pre_ping=True)
    updated = 0
    with engine.begin() as conn:
        for district, stats in MAHARASHTRA_CENSUS_2011.items():
            unit_id = conn.execute(text(
                "SELECT id FROM clean.admin_units WHERE level='district' AND name ILIKE :name LIMIT 1"
            ), {"name": district}).scalar()

            if unit_id is None:
                logger.warning("District not found in admin_units: %s", district)
                continue

            conn.execute(text("""
                INSERT INTO clean.demand_features (admin_unit_id, population, urban_share, data_status)
                VALUES (:uid, :pop, :urban, 'observed')
                ON CONFLICT (admin_unit_id)
                DO UPDATE SET population = EXCLUDED.population,
                              urban_share = EXCLUDED.urban_share,
                              data_status = EXCLUDED.data_status
            """), {
                "uid": unit_id,
                "pop": stats["population"],
                "urban": stats["urban_share"],
            })
            updated += 1

    logger.info("Updated population for %d districts.", updated)


def main():
    logger.info("=== Population Ingestion for %s ===", STATE)
    if STATE == "Maharashtra":
        load_into_db()
    else:
        logger.warning(
            "Census data only pre-loaded for Maharashtra. "
            "For other states, drop a CSV with columns [district, population, urban_share] "
            "in data/raw/population/ and update this script."
        )
        oq = ROOT / "docs" / "OPEN_QUESTIONS.md"
        oq.parent.mkdir(exist_ok=True)
        with open(oq, "a") as f:
            f.write(
                f"\n## Population data for {STATE}\n"
                "- Census 2011 data is pre-loaded only for Maharashtra.\n"
                "- Action: Add district population CSV for the configured state.\n"
            )
    logger.info("Population ingestion done.")


if __name__ == "__main__":
    main()
