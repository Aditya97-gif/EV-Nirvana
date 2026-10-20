"""Forecasts router."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from db import get_db

router = APIRouter()


@router.get("")
def get_forecasts(
    unit: Optional[int] = Query(None, description="Admin unit ID"),
    scenario: str = Query("baseline", description="baseline|accelerated|conservative"),
    db: Session = Depends(get_db),
):
    from sqlalchemy import text
    conditions = ["scenario = :scenario"]
    params: dict = {"scenario": scenario}
    if unit:
        conditions.append("admin_unit_id = :unit")
        params["unit"] = unit
    where = " AND ".join(conditions)
    rows = db.execute(text(f"""
        SELECT admin_unit_id, vehicle_class, scenario, period,
               evs_pred, lo, hi, model_version
        FROM analytics.forecasts WHERE {where}
        ORDER BY admin_unit_id, vehicle_class, period
    """), params).fetchall()
    return [dict(r._mapping) for r in rows]
