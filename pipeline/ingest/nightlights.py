"""
pipeline/ingest/nightlights.py
Phase 5 — Load VIIRS night-lights data for demand proxy (zonal mean per district).
The raster is large (~500 MB) so this script checks for a local copy before downloading.

Source: NOAA/NGDC VIIRS Monthly Composites (public domain)
URL: https://eogdata.mines.edu/products/vnl/
"""
import logging
import os
import sys
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(os.environ.get("PROJECT_ROOT", str(Path(__file__).resolve().parents[3])))
with open(ROOT / "config" / "project.yaml") as f:
    CONFIG = yaml.safe_load(f)

RAW_DIR = ROOT / "data" / "raw" / "nightlights"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def main():
    # Look for any existing raster in the raw dir
    tif_files = list(RAW_DIR.glob("*.tif")) + list(RAW_DIR.glob("*.tiff"))
    if not tif_files:
        logger.warning(
            "No night-lights raster found in %s\n"
            "Action: Download the VIIRS annual composite for India from:\n"
            "  https://eogdata.mines.edu/products/vnl/\n"
            "Place the .tif file in data/raw/nightlights/ and re-run.\n"
            "Logged to OPEN_QUESTIONS.md.",
            RAW_DIR,
        )
        oq = ROOT / "docs" / "OPEN_QUESTIONS.md"
        oq.parent.mkdir(exist_ok=True)
        with open(oq, "a") as f:
            f.write(
                "\n## VIIRS Night Lights Raster\n"
                "- Source: https://eogdata.mines.edu/products/vnl/ (public domain)\n"
                "- Action: Download VNL V2.2 annual composite for latest year, crop to India bbox.\n"
                "- Place .tif in data/raw/nightlights/ and rerun: `docker compose exec api python -m pipeline.ingest.nightlights`\n"
                "- Impact: night_light_mean in demand_features will be NULL until loaded (pipeline proceeds without it).\n"
            )
        return  # Non-fatal; pipeline continues

    # Compute zonal statistics per district
    try:
        import geopandas as gpd
        import rasterstats
        import sqlalchemy
        from sqlalchemy import create_engine, text

        tif_path = tif_files[0]
        logger.info("Using night-lights raster: %s", tif_path)

        DB_URL = (
            f"postgresql+psycopg2://{os.environ.get('DB_USER','evuser')}:"
            f"{os.environ.get('DB_PASSWORD','password')}@"
            f"{os.environ.get('DB_HOST','db')}:"
            f"{os.environ.get('DB_PORT','5432')}/"
            f"{os.environ.get('DB_NAME','ev_infra')}"
        )
        engine = create_engine(DB_URL, pool_pre_ping=True)

        districts = gpd.read_postgis(
            "SELECT id, geom FROM clean.admin_units WHERE level='district'",
            engine, geom_col="geom", crs="EPSG:4326",
        )

        stats = rasterstats.zonal_stats(
            districts.geometry,
            str(tif_path),
            stats=["mean"],
            nodata=-9999,
        )

        updated = 0
        with engine.begin() as conn:
            for (_, row), stat in zip(districts.iterrows(), stats):
                mean_val = stat.get("mean")
                if mean_val is None:
                    continue
                conn.execute(text("""
                    INSERT INTO clean.demand_features (admin_unit_id, night_light_mean, data_status)
                    VALUES (:uid, :nl, 'observed')
                    ON CONFLICT (admin_unit_id)
                    DO UPDATE SET night_light_mean = EXCLUDED.night_light_mean
                """), {"uid": int(row.id), "nl": float(mean_val)})
                updated += 1

        logger.info("Updated night_light_mean for %d districts.", updated)

    except ImportError as e:
        logger.error("Missing dependency: %s — install rasterstats", e)
    except Exception as e:
        logger.error("Night-lights processing failed: %s", e)


if __name__ == "__main__":
    main()
