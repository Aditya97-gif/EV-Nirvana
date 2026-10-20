"""Chargers router — serves EV charger location data."""
import math
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from db import get_db

router = APIRouter()


def _safe(val: Any) -> Any:
    """Convert DB values that JSON cannot handle (NaN, Decimal) to safe types."""
    if val is None:
        return None
    # Decimal / float NaN → None
    try:
        f = float(val)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except (TypeError, ValueError):
        pass
    return val


@router.get("")
def list_chargers(
    bbox: Optional[str] = Query(None, description="Bounding box: minLon,minLat,maxLon,maxLat"),
    source: Optional[str] = Query(None, description="Filter by data source: osm|ocm|gov"),
    min_kw: Optional[float] = Query(None, description="Minimum charger power in kW"),
    operator: Optional[str] = Query(None, description="Filter by operator name (fuzzy)"),
    limit: int = Query(500, le=5000),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """Return chargers with optional filters. Pagination via limit/offset."""
    conditions = ["1=1"]
    params: dict = {"limit": limit, "offset": offset}

    if bbox:
        parts = [float(x) for x in bbox.split(",")]
        conditions.append(
            "ST_Within(geom, ST_MakeEnvelope(:minlon,:minlat,:maxlon,:maxlat,4326))"
        )
        params.update({"minlon": parts[0], "minlat": parts[1],
                        "maxlon": parts[2], "maxlat": parts[3]})

    if min_kw is not None:
        conditions.append("max_power_kw >= :min_kw")
        params["min_kw"] = min_kw

    if operator:
        # Use simple ILIKE — similarity() needs pg_trgm which may not be enabled
        conditions.append("operator ILIKE :operator")
        params["operator"] = f"%{operator}%"

    where = " AND ".join(conditions)
    query = f"""
        SELECT id, name, operator,
               max_power_kw, current_type, connector_types,
               confidence, n_sources, data_status, last_verified,
               ST_AsGeoJSON(geom)::json AS geometry
        FROM clean.chargers
        WHERE {where}
        ORDER BY id
        LIMIT :limit OFFSET :offset
    """
    rows = db.execute(text(query), params).fetchall()

    result = []
    for r in rows:
        m = dict(r._mapping)
        # Sanitise non-JSON-safe values
        m["max_power_kw"] = _safe(m.get("max_power_kw"))
        m["confidence"]   = _safe(m.get("confidence"))
        # connector_types may be a list already (from psycopg2 array)
        ct = m.get("connector_types")
        if ct is not None and not isinstance(ct, list):
            m["connector_types"] = list(ct)
        # last_verified → ISO string
        lv = m.get("last_verified")
        m["last_verified"] = lv.isoformat() if lv and hasattr(lv, "isoformat") else lv
        result.append(m)

    return result
