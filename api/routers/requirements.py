"""Requirements router."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from db import get_db

router = APIRouter()


@router.get("")
def get_requirements(
    unit: Optional[int] = Query(None),
    scenario: str = Query("baseline"),
    year: int = Query(2030),
    db: Session = Depends(get_db),
):
    from sqlalchemy import text
    conditions = ["scenario = :scenario", "horizon_year = :year"]
    params: dict = {"scenario": scenario, "year": year}
    if unit:
        conditions.append("admin_unit_id = :unit")
        params["unit"] = unit
    where = " AND ".join(conditions)
    rows = db.execute(text(f"""
        SELECT admin_unit_id, scenario, horizon_year, vehicle_class,
               charger_type, required_count, existing_count, shortfall,
               assumptions_version
        FROM analytics.requirements WHERE {where}
        ORDER BY admin_unit_id, vehicle_class, charger_type
    """), params).fetchall()
    return [dict(r._mapping) for r in rows]
