"""Gaps router — serves gap scores and corridor gap data."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from db import get_db

router = APIRouter()


@router.get("")
def list_gaps(
    level: Optional[str] = Query("district"),
    as_of: Optional[str] = Query(None, description="Date YYYY-MM-DD"),
    weights_version: str = Query("1.0"),
    db: Session = Depends(get_db),
):
    """Return gap scores per admin unit with optional weight override."""
    from sqlalchemy import text
    query = """
        SELECT g.admin_unit_id, a.name, a.level,
               g.evs_total, g.public_chargers, g.dc_fast_chargers,
               g.evs_per_charger, g.coverage_pop_pct, g.gap_index, g.rank,
               g.as_of, g.weights_version
        FROM analytics.gap_scores g
        JOIN clean.admin_units a ON a.id = g.admin_unit_id
        WHERE a.level = :level AND g.weights_version = :wv
    """
    params: dict = {"level": level, "wv": weights_version}
    if as_of:
        query += " AND g.as_of = :as_of"
        params["as_of"] = as_of
    query += " ORDER BY g.rank"
    rows = db.execute(text(query), params).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/corridors")
def corridor_gaps(db: Session = Depends(get_db)):
    """Return corridor gap segments flagged as exceeding the threshold."""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT c.id, c.road_id, r.ref AS road_ref, c.segment_id,
               c.max_gap_km, c.n_dc_chargers, c.gap_flag,
               ST_AsGeoJSON(c.geom)::json AS geometry
        FROM analytics.corridor_gaps c
        LEFT JOIN clean.roads_nh r ON r.id = c.road_id
        WHERE c.gap_flag = TRUE
        ORDER BY c.max_gap_km DESC
    """)).fetchall()
    return [dict(r._mapping) for r in rows]
