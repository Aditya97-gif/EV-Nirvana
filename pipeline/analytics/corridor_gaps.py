"""
pipeline/analytics/corridor_gaps.py
Phase 6 — Identify gaps between DC fast chargers along National Highways.
For each NH segment, finds the maximum distance between consecutive DC chargers.
Flags segments where max_gap_km > threshold (from meta.assumptions).
"""
import logging
import os
from pathlib import Path

import geopandas as gpd
import pandas as pd
import yaml
from shapely.geometry import LineString, Point
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

PROJ_CRS = CONFIG.get("project_crs", "EPSG:32643")


def main():
    logger.info("=== Corridor Gap Analysis ===")
    engine = create_engine(DB_URL, pool_pre_ping=True)

    with engine.connect() as conn:
        threshold_km = conn.execute(text(
            "SELECT value FROM meta.assumptions WHERE key='corridor_gap_threshold_km'"
        )).scalar() or 50.0
        dc_min_kw = conn.execute(text(
            "SELECT value FROM meta.assumptions WHERE key='dc_fast_min_kw'"
        )).scalar() or 30.0

    # Load NH roads and DC chargers
    roads_gdf = gpd.read_postgis(
        "SELECT id, ref, name, geom FROM clean.roads_nh",
        engine, geom_col="geom", crs="EPSG:4326",
    )
    chargers_gdf = gpd.read_postgis(
        f"SELECT id, geom FROM clean.chargers WHERE max_power_kw >= {dc_min_kw}",
        engine, geom_col="geom", crs="EPSG:4326",
    )

    if roads_gdf.empty:
        logger.warning("No NH road data. Run roads ingestion first.")
        return

    roads_proj = roads_gdf.to_crs(PROJ_CRS)
    chargers_proj = chargers_gdf.to_crs(PROJ_CRS) if not chargers_gdf.empty else chargers_gdf

    # For each road, find chargers within 1 km snap distance, order by road position
    SNAP_DIST_M = 1000  # chargers within 1 km of road counted as "on" the road
    gap_records = []

    for _, road in roads_proj.iterrows():
        road_line = road["geom"]   # geom_col='geom' in read_postgis
        if road_line is None or road_line.is_empty:
            continue

        if chargers_proj.empty:
            nearby = gpd.GeoDataFrame(geometry=[], crs=PROJ_CRS)
        else:
            nearby = chargers_proj[chargers_proj["geom"].distance(road_line) < SNAP_DIST_M].copy()

        if nearby.empty:
            # No chargers on this road — entire road is a gap
            gap_records.append({
                "road_id": int(road["id"]),
                "segment_id": 0,
                "geom": road_line,
                "max_gap_km": road_line.length / 1000,
                "n_dc_chargers": 0,
                "gap_flag": (road_line.length / 1000) > float(threshold_km),
            })
            continue

        # Project charger positions onto the line
        nearby["position_m"] = nearby["geom"].apply(lambda g: road_line.project(g))
        charger_positions = sorted(nearby["position_m"].tolist())

        # Add road start (0) and end
        positions = [0.0] + charger_positions + [road_line.length]
        max_gap_m = max(positions[i+1] - positions[i] for i in range(len(positions)-1))

        gap_records.append({
            "road_id": int(road["id"]),
            "segment_id": 0,
            "geom": road_line,
            "max_gap_km": round(max_gap_m / 1000, 2),
            "n_dc_chargers": len(charger_positions),
            "gap_flag": (max_gap_m / 1000) > float(threshold_km),
        })

    if not gap_records:
        logger.warning("No corridor gap records computed.")
        return

    gap_gdf = gpd.GeoDataFrame(gap_records, geometry="geom", crs=PROJ_CRS).to_crs("EPSG:4326")

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM analytics.corridor_gaps"))
        for _, row in gap_gdf.iterrows():
            conn.execute(text("""
                INSERT INTO analytics.corridor_gaps
                    (road_id, segment_id, geom, max_gap_km, n_dc_chargers, gap_flag)
                VALUES
                    (:road_id, :seg_id, ST_GeomFromText(:geom, 4326), :gap_km, :n_dc, :flag)
            """), {
                "road_id": int(row["road_id"]), "seg_id": int(row["segment_id"]),
                "geom": row["geom"].wkt,
                "gap_km": float(row["max_gap_km"]),
                "n_dc": int(row["n_dc_chargers"]),
                "flag": bool(row["gap_flag"]),
            })

    flagged = sum(1 for r in gap_records if r["gap_flag"])
    logger.info(
        "Corridor analysis complete: %d road segments, %d flagged (gap > %.0f km).",
        len(gap_records), flagged, threshold_km,
    )


if __name__ == "__main__":
    main()
