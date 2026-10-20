"""Admin units router — serves state/district/city boundary data."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from db import get_db

router = APIRouter()


@router.get("")
def list_admin_units(
    level: Optional[str] = Query(None, description="Filter by level: state|district|city"),
    parent: Optional[int] = Query(None, description="Filter by parent admin unit ID"),
    db: Session = Depends(get_db),
):
    """Return admin units, optionally filtered by level and parent."""
    query = "SELECT id, level, name, parent_id, census_code, data_status FROM clean.admin_units WHERE 1=1"
    params = {}
    if level:
        query += " AND level = :level"
        params["level"] = level
    if parent:
        query += " AND parent_id = :parent"
        params["parent"] = parent
    from sqlalchemy import text
    rows = db.execute(text(query), params).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/{unit_id}/geom")
def get_admin_unit_geom(unit_id: int, db: Session = Depends(get_db)):
    """Return GeoJSON geometry for a specific admin unit."""
    from sqlalchemy import text
    row = db.execute(
        text("SELECT id, level, name, ST_AsGeoJSON(geom)::json as geometry FROM clean.admin_units WHERE id = :id"),
        {"id": unit_id},
    ).fetchone()
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Admin unit not found")
    return dict(row._mapping)
