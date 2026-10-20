"""Site recommendation router."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from db import get_db

router = APIRouter()


class RecommendRequest(BaseModel):
    admin_unit_id: int
    scenario: str = "baseline"
    k: int = 10


@router.post("/")
def recommend_sites(req: RecommendRequest, db: Session = Depends(get_db)):
    """Return top-k recommended sites for a given region and scenario."""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT r.rank, r.demand_covered, r.gap_closed, r.grid_distance_km,
               r.reason_text, r.scenario,
               c.name AS site_name, c.type AS site_type,
               ST_AsGeoJSON(c.geom)::json AS geometry
        FROM analytics.recommended_sites r
        JOIN clean.candidate_sites c ON c.id = r.candidate_site_id
        WHERE r.scenario = :scenario
        ORDER BY r.rank
        LIMIT :k
    """), {"scenario": req.scenario, "k": req.k}).fetchall()
    return [dict(r._mapping) for r in rows]
