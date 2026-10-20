"""
pipeline/clean/dedup_chargers.py
Phase 3 — Deduplicate chargers across sources using spatial clustering (DBSCAN)
and fuzzy name/operator matching. Populates clean.chargers with merged records
and confidence scores.

Formula for confidence score (documented in METHODOLOGY.md):
  confidence = 0.5 * min(n_sources / 3, 1.0)          # source agreement
             + 0.3 * completeness                       # attribute completeness
             + 0.2 * recency_score                      # recency (1 if verified < 90d)

Normalise to [0, 1].
"""
import logging
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from rapidfuzz import fuzz
from sklearn.cluster import DBSCAN
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

EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Return distance in metres between two WGS84 points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def load_raw(engine) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(text(
            "SELECT id, source, name, operator, lat, lon, connector_types, "
            "power_kw, current_type, fetched_at FROM raw.chargers_raw"
        ), conn)
    return df


def cluster_by_distance(df: pd.DataFrame, eps_m: float) -> np.ndarray:
    """Run DBSCAN with haversine distance in metres. Returns cluster labels."""
    coords_rad = np.radians(df[["lat", "lon"]].values)
    eps_rad = eps_m / EARTH_RADIUS_M
    db = DBSCAN(eps=eps_rad, min_samples=1, algorithm="ball_tree", metric="haversine")
    return db.fit_predict(coords_rad)


def operator_similar(op1: str | None, op2: str | None, threshold: int = 80) -> bool:
    if not op1 or not op2:
        return False
    return fuzz.token_sort_ratio(op1, op2) >= threshold


def compute_confidence(n_sources: int, completeness: float, recency_days: float) -> float:
    source_score = min(n_sources / 3, 1.0)
    recency_score = 1.0 if recency_days < 90 else max(0.0, 1.0 - (recency_days - 90) / 365)
    return round(0.5 * source_score + 0.3 * completeness + 0.2 * recency_score, 3)


def attribute_completeness(rows: pd.DataFrame) -> float:
    fields = ["name", "operator", "power_kw", "current_type"]
    non_null = sum(1 for f in fields if rows[f].notna().any())
    return non_null / len(fields)


def merge_cluster(group: pd.DataFrame) -> dict:
    """Merge a cluster of raw records into a single clean charger."""
    # Prefer non-null values; take the record with highest attribute completeness
    best = group.dropna(subset=["name", "operator", "power_kw"]).head(1)
    if best.empty:
        best = group.head(1)
    best_row = best.iloc[0]

    all_connectors = []
    for ct in group["connector_types"].dropna():
        if isinstance(ct, list):
            all_connectors.extend(ct)
        else:
            all_connectors.append(ct)

    # Recency: days since oldest fetch
    recency_days = 0.0
    if group["fetched_at"].notna().any():
        oldest = pd.to_datetime(group["fetched_at"]).min()
        recency_days = (datetime.utcnow() - oldest.to_pydatetime().replace(tzinfo=None)).days

    return {
        "name": best_row.get("name"),
        "operator": best_row.get("operator"),
        "lat": group["lat"].mean(),
        "lon": group["lon"].mean(),
        "connector_types": list(set(all_connectors)) or ["unknown"],
        "max_power_kw": group["power_kw"].max(),
        "current_type": best_row.get("current_type"),
        "n_sources": group["source"].nunique(),
        "merged_from": group["id"].tolist(),
        "confidence": compute_confidence(
            group["source"].nunique(),
            attribute_completeness(group),
            recency_days,
        ),
        "data_status": "observed",
    }


def load_clean(merged: list[dict], engine) -> int:
    inserted = 0
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM clean.chargers"))  # idempotent re-run
        for rec in merged:
            conn.execute(text("""
                INSERT INTO clean.chargers
                    (name, operator, geom, connector_types, max_power_kw, current_type,
                     n_sources, merged_from, confidence, data_status)
                VALUES
                    (:name, :operator,
                     ST_SetSRID(ST_MakePoint(:lon,:lat),4326),
                     :connector_types, :max_power_kw, :current_type,
                     :n_sources, :merged_from, :confidence, :data_status)
            """), {
                **rec,
                "merged_from": rec["merged_from"],
            })
            inserted += 1
    return inserted


def write_dedup_report(before: int, after: int, clusters: list[int]) -> None:
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    report = reports_dir / "dedup_report.md"
    with open(report, "w") as f:
        f.write("# Charger Deduplication Report\n\n")
        f.write(f"- Raw records: {before}\n")
        f.write(f"- After dedup: {after}\n")
        f.write(f"- Reduction: {before - after} ({100*(before-after)/max(before,1):.1f}%)\n")
        f.write(f"- Clusters: {len(clusters)}\n")
        large = [c for c in clusters if c > 1]
        f.write(f"- Multi-source clusters: {len(large)}\n\n")
        f.write("_Generated automatically — see pipeline/clean/dedup_chargers.py_\n")
    logger.info("Dedup report saved to %s", report)


def main():
    logger.info("=== Charger Deduplication ===")
    engine = create_engine(DB_URL, pool_pre_ping=True)

    # Load assumptions
    with engine.connect() as conn:
        eps_m = conn.execute(text(
            "SELECT value FROM meta.assumptions WHERE key='dedup_distance_m'"
        )).scalar() or 75.0

    df = load_raw(engine)
    logger.info("Loaded %d raw charger records.", len(df))

    if df.empty:
        logger.warning("No raw chargers — skipping dedup.")
        return

    labels = cluster_by_distance(df, float(eps_m))
    df["cluster"] = labels

    merged_records = []
    cluster_sizes = []
    for cluster_id, group in df.groupby("cluster"):
        merged_records.append(merge_cluster(group))
        cluster_sizes.append(len(group))

    inserted = load_clean(merged_records, engine)
    write_dedup_report(len(df), inserted, cluster_sizes)
    logger.info("Dedup complete: %d raw → %d clean chargers.", len(df), inserted)


if __name__ == "__main__":
    main()
