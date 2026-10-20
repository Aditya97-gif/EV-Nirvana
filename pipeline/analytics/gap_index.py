"""
pipeline/analytics/gap_index.py
Phase 6 — Compute Charging Gap Index (CGI) per district.

CGI = w1*norm(evs_per_charger)
    + w2*(1 - norm(coverage_pop_pct))
    + w3*norm(demand_score)
    + w4*norm(growth_rate)
    + w5*norm(corridor_gap_score)

All weights loaded from meta.assumptions (adjustable from UI).
Normalisation: min-max per indicator across all districts.
"""
import logging
import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
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

WEIGHTS_VERSION = "1.0"


def load_assumptions(conn) -> dict:
    rows = conn.execute(text(
        "SELECT key, value FROM meta.assumptions WHERE key LIKE 'cgi_%' OR key LIKE 'coverage_%' OR key='dc_fast_min_kw'"
    )).fetchall()
    return {r.key: float(r.value) for r in rows}


def minmax_norm(series: pd.Series) -> pd.Series:
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(0.5, index=series.index)
    return (series - mn) / (mx - mn)


def compute_coverage_pct(conn, unit_id: int, radius_urban_km: float, radius_rural_km: float) -> float:
    """
    Estimate population coverage as share within radius of a charger.
    Uses a simple buffer count against demand_features population.
    Returns fraction 0–1.
    """
    result = conn.execute(text("""
        SELECT
            SUM(CASE WHEN within_radius THEN d.population ELSE 0 END)::FLOAT /
            NULLIF(SUM(d.population), 0) AS coverage
        FROM clean.admin_units a
        JOIN clean.demand_features d ON d.admin_unit_id = a.id
        CROSS JOIN LATERAL (
            SELECT EXISTS (
                SELECT 1 FROM clean.chargers c
                WHERE ST_DWithin(
                    c.geom::geography,
                    a.geom::geography,
                    CASE WHEN d.urban_share > 0.5 THEN :r_urban * 1000
                         ELSE :r_rural * 1000 END
                )
            ) AS within_radius
        ) sub
        WHERE a.id = :uid
    """), {"uid": unit_id, "r_urban": radius_urban_km, "r_rural": radius_rural_km}).scalar()
    return float(result or 0.0)


def compute_growth_rate(conn, unit_id: int) -> float:
    """Compute YoY EV growth rate for latest available year."""
    result = conn.execute(text("""
        WITH yearly AS (
            SELECT year, SUM(count) AS total
            FROM clean.ev_registrations
            WHERE admin_unit_id = :uid
            GROUP BY year ORDER BY year
        )
        SELECT
            CASE WHEN LAG(total) OVER (ORDER BY year) > 0
                 THEN (total - LAG(total) OVER (ORDER BY year))::FLOAT / LAG(total) OVER (ORDER BY year)
                 ELSE 0 END AS growth_rate
        FROM yearly
        ORDER BY year DESC LIMIT 1
    """), {"uid": unit_id}).scalar()
    return float(result or 0.0)


def main():
    logger.info("=== Gap Index Computation ===")
    engine = create_engine(DB_URL, pool_pre_ping=True)
    as_of = date.today()

    with engine.connect() as conn:
        assumptions = load_assumptions(conn)
        w = {
            "evs_per_charger": assumptions.get("cgi_weight_evs_per_charger", 0.30),
            "coverage":        assumptions.get("cgi_weight_coverage", 0.25),
            "demand_score":    assumptions.get("cgi_weight_demand_score", 0.20),
            "growth_rate":     assumptions.get("cgi_weight_growth_rate", 0.10),
            "corridor_gap":    assumptions.get("cgi_weight_corridor_gap", 0.15),
        }
        dc_fast_min = assumptions.get("dc_fast_min_kw", 30)
        r_urban = assumptions.get("coverage_radius_urban_km", 3)
        r_rural = assumptions.get("coverage_radius_highway_km", 25)

        # Load all districts
        districts = conn.execute(text(
            "SELECT id, name FROM clean.admin_units WHERE level='district'"
        )).fetchall()

    records = []
    engine2 = create_engine(DB_URL, pool_pre_ping=True)
    for dist in districts:
        uid = dist.id
        with engine2.connect() as conn:
            evs_total = conn.execute(text(
                "SELECT COALESCE(SUM(count),0) FROM clean.ev_registrations WHERE admin_unit_id=:uid"
            ), {"uid": uid}).scalar() or 0
            evs_2w = conn.execute(text(
                "SELECT COALESCE(SUM(count),0) FROM clean.ev_registrations WHERE admin_unit_id=:uid AND vehicle_class='2W'"
            ), {"uid": uid}).scalar() or 0
            evs_4w = conn.execute(text(
                "SELECT COALESCE(SUM(count),0) FROM clean.ev_registrations WHERE admin_unit_id=:uid AND vehicle_class='4W'"
            ), {"uid": uid}).scalar() or 0
            public_chargers = conn.execute(text(
                "SELECT COUNT(*) FROM clean.chargers WHERE admin_unit_id=:uid"
            ), {"uid": uid}).scalar() or 0
            dc_chargers = conn.execute(text(
                "SELECT COUNT(*) FROM clean.chargers WHERE admin_unit_id=:uid AND max_power_kw>=:dc"
            ), {"uid": uid, "dc": dc_fast_min}).scalar() or 0

            night_light = conn.execute(text(
                "SELECT COALESCE(night_light_mean,0) FROM clean.demand_features WHERE admin_unit_id=:uid"
            ), {"uid": uid}).scalar() or 0.0

            evs_per_charger = evs_total / max(public_chargers, 1)
            coverage = compute_coverage_pct(conn, uid, r_urban, r_rural)
            growth_rate = compute_growth_rate(conn, uid)

        records.append({
            "admin_unit_id": uid,
            "evs_total": int(evs_total),
            "evs_2w": int(evs_2w),
            "evs_4w": int(evs_4w),
            "public_chargers": int(public_chargers),
            "dc_fast_chargers": int(dc_chargers),
            "evs_per_charger": evs_per_charger,
            "coverage_pop_pct": coverage,
            "demand_score": float(night_light),
            "growth_rate": growth_rate,
        })

    df = pd.DataFrame(records)
    if df.empty:
        logger.warning("No district data found — gap index skipped.")
        return

    # Normalise indicators
    df["n_evs_per_charger"] = minmax_norm(df["evs_per_charger"])
    df["n_coverage"]        = minmax_norm(df["coverage_pop_pct"])
    df["n_demand"]          = minmax_norm(df["demand_score"])
    df["n_growth"]          = minmax_norm(df["growth_rate"])
    df["n_corridor"]        = 0.5  # placeholder until corridor_gaps.py runs first

    df["gap_index"] = (
        w["evs_per_charger"] * df["n_evs_per_charger"]
        + w["coverage"]     * (1 - df["n_coverage"])
        + w["demand_score"] * df["n_demand"]
        + w["growth_rate"]  * df["n_growth"]
        + w["corridor_gap"] * df["n_corridor"]
    ).round(4)

    df["rank"] = df["gap_index"].rank(ascending=False, method="min").astype(int)

    # Write to DB
    with engine.begin() as conn:
        conn.execute(text(
            "DELETE FROM analytics.gap_scores WHERE as_of=:d AND weights_version=:wv"
        ), {"d": as_of.isoformat(), "wv": WEIGHTS_VERSION})
        for _, row in df.iterrows():
            conn.execute(text("""
                INSERT INTO analytics.gap_scores
                    (admin_unit_id, as_of, evs_total, evs_2w, evs_4w, public_chargers,
                     dc_fast_chargers, evs_per_charger, coverage_pop_pct,
                     gap_index, rank, weights_version)
                VALUES
                    (:uid, :d, :et, :e2w, :e4w, :pc, :dc, :epc, :cov, :gi, :rk, :wv)
            """), {
                "uid": int(row.admin_unit_id), "d": as_of.isoformat(),
                "et": int(row.evs_total), "e2w": int(row.evs_2w), "e4w": int(row.evs_4w),
                "pc": int(row.public_chargers), "dc": int(row.dc_fast_chargers),
                "epc": round(float(row.evs_per_charger), 2),
                "cov": round(float(row.coverage_pop_pct), 4),
                "gi": float(row.gap_index), "rk": int(row["rank"]), "wv": WEIGHTS_VERSION,
            })

    logger.info("Gap index computed for %d districts. Top gap: rank 1.", len(df))


if __name__ == "__main__":
    main()
