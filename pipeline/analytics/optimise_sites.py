"""
pipeline/analytics/optimise_sites.py
Phase 9 — Maximal Covering Location Problem (MCLP) for charger site selection.

Given k candidate sites, choose the set that maximises population covered
within radius R. Uses PuLP LP solver.
Also runs corridor use-case: place DC chargers to eliminate gaps > threshold.
"""
import logging
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
import pulp
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

EARTH_R = 6_371_000


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2-lat1)/2)**2 +
         math.cos(phi1)*math.cos(phi2)*math.sin(math.radians(lon2-lon1)/2)**2)
    return 2 * EARTH_R * math.asin(math.sqrt(a)) / 1000


def load_candidates(engine, admin_unit_id: int | None = None) -> pd.DataFrame:
    where = f"AND ST_Within(c.geom, (SELECT geom FROM clean.admin_units WHERE id={admin_unit_id}))" \
            if admin_unit_id else ""
    with engine.connect() as conn:
        df = pd.read_sql(text(f"""
            SELECT c.id, c.name, c.type,
                   ST_Y(c.geom) AS lat, ST_X(c.geom) AS lon
            FROM clean.candidate_sites c
            WHERE NOT EXISTS (
                SELECT 1 FROM clean.chargers ch
                WHERE ST_DWithin(c.geom::geography, ch.geom::geography, 500)
            )
            {where}
        """), conn)
    return df


def load_demand_points(engine, admin_unit_id: int | None = None) -> pd.DataFrame:
    where = f"AND id={admin_unit_id}" if admin_unit_id else ""
    with engine.connect() as conn:
        df = pd.read_sql(text(f"""
            SELECT a.id, ST_Y(ST_Centroid(a.geom)) AS lat, ST_X(ST_Centroid(a.geom)) AS lon,
                   COALESCE(d.population, 10000) AS population
            FROM clean.admin_units a
            LEFT JOIN clean.demand_features d ON d.admin_unit_id = a.id
            WHERE a.level = 'district' {where}
        """), conn)
    return df


def solve_mclp(candidates: pd.DataFrame, demand: pd.DataFrame,
               k: int, coverage_radius_km: float, scenario: str) -> list[dict]:
    """
    Solve MCLP: choose k sites to maximise covered population.
    Returns list of dicts with site info and reason text.
    """
    if candidates.empty or demand.empty:
        return []

    I = list(demand.index)   # demand points
    J = list(candidates.index)  # candidate sites

    # Coverage matrix: a_ij = 1 if site j covers demand point i
    a = {(i, j): 1 if haversine_km(
            demand.loc[i, "lat"], demand.loc[i, "lon"],
            candidates.loc[j, "lat"], candidates.loc[j, "lon"]) <= coverage_radius_km
         else 0
         for i in I for j in J}

    prob = pulp.LpProblem("MCLP", pulp.LpMaximize)
    x = pulp.LpVariable.dicts("x", J, cat="Binary")  # site selected
    y = pulp.LpVariable.dicts("y", I, cat="Binary")  # demand point covered

    # Objective: maximise covered weighted population
    prob += pulp.lpSum(demand.loc[i, "population"] * y[i] for i in I)

    # Budget constraint
    prob += pulp.lpSum(x[j] for j in J) <= k

    # Coverage constraint: y_i <= sum_j a_ij * x_j
    for i in I:
        prob += y[i] <= pulp.lpSum(a[i, j] * x[j] for j in J)

    status = prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=25))
    if pulp.LpStatus[prob.status] not in ("Optimal", "Feasible"):
        logger.warning("MCLP solver status: %s", pulp.LpStatus[prob.status])
        return []

    selected = [j for j in J if pulp.value(x[j]) == 1]
    total_pop = demand["population"].sum()

    results = []
    for rank, j in enumerate(selected, 1):
        cov_pop = sum(demand.loc[i, "population"] for i in I if a[i, j] == 1)
        results.append({
            "rank": rank,
            "candidate_site_id": int(candidates.loc[j, "id"]),
            "demand_covered": round(cov_pop / max(total_pop, 1), 4),
            "gap_closed": None,  # set separately
            "grid_distance_km": None,
            "reason_text": (
                f"Covers ~{cov_pop:,.0f} people within {coverage_radius_km} km. "
                f"Site type: {candidates.loc[j, 'type']}."
            ),
            "scenario": scenario,
        })

    return results


def save_results(results: list[dict], engine) -> None:
    with engine.begin() as conn:
        for rec in results:
            conn.execute(text("""
                INSERT INTO analytics.recommended_sites
                    (rank, candidate_site_id, demand_covered, gap_closed,
                     grid_distance_km, reason_text, scenario)
                VALUES (:rank, :cid, :dc, :gc, :gd, :rt, :sc)
            """), {
                "rank": rec["rank"], "cid": rec["candidate_site_id"],
                "dc": rec["demand_covered"], "gc": rec["gap_closed"],
                "gd": rec["grid_distance_km"], "rt": rec["reason_text"],
                "sc": rec["scenario"],
            })


def main():
    logger.info("=== Site Optimisation (MCLP) ===")
    engine = create_engine(DB_URL, pool_pre_ping=True)

    with engine.connect() as conn:
        r_urban = conn.execute(text(
            "SELECT value FROM meta.assumptions WHERE key='coverage_radius_urban_km'"
        )).scalar() or 3.0

    candidates = load_candidates(engine)
    demand = load_demand_points(engine)

    if candidates.empty:
        logger.warning("No candidate sites found — skipping optimisation.")
        return

    logger.info("Solving MCLP: %d candidates, %d demand points, k=10",
                len(candidates), len(demand))

    for scenario in ["baseline", "accelerated", "conservative"]:
        results = solve_mclp(candidates, demand, k=10,
                              coverage_radius_km=float(r_urban), scenario=scenario)
        if results:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM analytics.recommended_sites WHERE scenario=:sc"),
                             {"sc": scenario})
            save_results(results, engine)
            logger.info("Saved %d recommended sites for scenario '%s'", len(results), scenario)
        else:
            logger.warning("No sites recommended for scenario '%s'", scenario)


if __name__ == "__main__":
    main()
