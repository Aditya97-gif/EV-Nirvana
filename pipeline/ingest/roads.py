"""
pipeline/ingest/roads.py
Phase 5 — Fetch National Highway geometries from OSM via Overpass bbox query.
Segments each highway into ~10 km chunks for corridor gap analysis.

FIX: replaced osmnx.features_from_place (explodes to 168 sub-queries for MH)
     with a single direct Overpass API bbox query — completes in ~30 seconds.
"""
import logging
import os
import requests
from pathlib import Path

import geopandas as gpd
import numpy as np
import yaml
from shapely.geometry import LineString, MultiLineString
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(os.environ.get("PROJECT_ROOT", str(Path(__file__).resolve().parents[3])))
CONFIG_PATH = ROOT / "config" / "project.yaml"
RAW_DIR = ROOT / "data" / "raw" / "roads"
RAW_DIR.mkdir(parents=True, exist_ok=True)

with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)

STATE = CONFIG["state"]
PROJ_CRS = CONFIG.get("project_crs", "EPSG:32643")
BBOX = CONFIG.get("bbox", [72.6, 15.6, 80.9, 22.1])   # [west, south, east, north]

DB_URL = (
    f"postgresql+psycopg2://{os.environ.get('DB_USER','evuser')}:"
    f"{os.environ.get('DB_PASSWORD','password')}@"
    f"{os.environ.get('DB_HOST','db')}:"
    f"{os.environ.get('DB_PORT','5432')}/"
    f"{os.environ.get('DB_NAME','ev_infra')}"
)

OVERPASS_URL = os.environ.get(
    "OVERPASS_URL",
    CONFIG.get("overpass_url", "https://overpass-api.de/api/interpreter")
)
SEGMENT_LENGTH_M = 10_000   # 10 km


def fetch_nh_roads() -> gpd.GeoDataFrame:
    cache = RAW_DIR / f"nh_{STATE.replace(' ', '_')}.gpkg"
    if cache.exists():
        logger.info("Loading roads from cache: %s", cache)
        return gpd.read_file(str(cache))

    south, west, north, east = BBOX[1], BBOX[0], BBOX[3], BBOX[2]
    query = f"""
    [out:json][timeout:120];
    (
      way["highway"~"motorway|trunk|primary"]["ref"~"^NH"]
         ({south},{west},{north},{east});
    );
    out geom;
    """

    logger.info("Fetching NH roads via Overpass bbox for %s ...", STATE)
    resp = requests.post(
        OVERPASS_URL, data={"data": query}, timeout=150,
        headers={"User-Agent": "EV_Nirvana/1.0"}
    )
    resp.raise_for_status()
    elements = resp.json().get("elements", [])
    logger.info("Overpass returned %d NH way elements.", len(elements))

    rows = []
    for el in elements:
        if el.get("type") != "way" or "geometry" not in el:
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in el["geometry"]]
        if len(coords) < 2:
            continue
        rows.append({
            "osm_id":   el["id"],
            "ref":      el.get("tags", {}).get("ref", ""),
            "name":     el.get("tags", {}).get("name", ""),
            "geometry": LineString(coords),
        })

    if not rows:
        logger.warning("No NH roads found in bbox — corridor gap analysis skipped.")
        return gpd.GeoDataFrame(
            columns=["osm_id", "ref", "name", "geometry"],
            geometry="geometry", crs="EPSG:4326"
        )

    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_file(str(cache), driver="GPKG")
    logger.info("Saved %d NH road features to cache.", len(gdf))
    return gdf


def segment_line(line: LineString, seg_len_m: float) -> list:
    """Segment a LineString into chunks of approximately seg_len_m metres."""
    gdf_tmp = gpd.GeoDataFrame(geometry=[line], crs="EPSG:4326").to_crs(PROJ_CRS)
    line_m = gdf_tmp.geometry.iloc[0]
    total_len = line_m.length

    if total_len <= seg_len_m:
        return [line]

    segments = []
    current_pos = 0.0
    while current_pos < total_len:
        end_pos = min(current_pos + seg_len_m, total_len)
        pts = [line_m.interpolate(d) for d in
               np.linspace(current_pos, end_pos, max(2, int((end_pos - current_pos) / 100)))]
        seg = LineString(pts)
        seg_4326 = gpd.GeoDataFrame(geometry=[seg], crs=PROJ_CRS).to_crs("EPSG:4326").geometry.iloc[0]
        segments.append(seg_4326)
        current_pos += seg_len_m

    return segments


def load_into_db(gdf: gpd.GeoDataFrame) -> None:
    if gdf.empty:
        logger.warning("Empty roads GeoDataFrame — nothing to insert.")
        return

    engine = create_engine(DB_URL, pool_pre_ping=True)
    inserted = 0
    with engine.begin() as conn:
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None:
                continue
            lines = list(geom.geoms) if isinstance(geom, MultiLineString) else [geom]
            ref  = row.get("ref", "")
            name = row.get("name", "")
            for line in lines:
                for seg in segment_line(line, SEGMENT_LENGTH_M):
                    seg_proj = gpd.GeoDataFrame(geometry=[seg], crs="EPSG:4326").to_crs(PROJ_CRS)
                    length_km = seg_proj.geometry.iloc[0].length / 1000
                    conn.execute(text("""
                        INSERT INTO clean.roads_nh (ref, name, geom, length_km)
                        VALUES (:ref, :name, ST_GeomFromText(:geom, 4326), :len)
                    """), {"ref": ref, "name": name,
                           "geom": seg.wkt, "len": round(length_km, 3)})
                    inserted += 1
    logger.info("Inserted %d NH road segments into clean.roads_nh.", inserted)


def main():
    logger.info("=== Roads Ingestion for %s ===", STATE)
    try:
        gdf = fetch_nh_roads()
        load_into_db(gdf)
    except Exception as e:
        logger.error("Roads ingestion failed: %s", e, exc_info=True)
        oq = ROOT / "docs" / "OPEN_QUESTIONS.md"
        with open(oq, "a") as f:
            f.write(f"\n## NH roads fetch failed\n- Error: {e}\n"
                    "- Action: try Geofabrik extract for India at https://download.geofabrik.de/asia/india.html\n")


if __name__ == "__main__":
    main()
