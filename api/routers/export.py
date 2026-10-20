"""Export router — district planning briefs as PDF or CSV."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional
import io, csv
from db import get_db

router = APIRouter()


@router.get("/brief")
def export_brief(
    unit: int = Query(..., description="Admin unit ID"),
    format: str = Query("csv", description="csv|pdf"),
    db: Session = Depends(get_db),
):
    """Export a district planning brief for the given admin unit."""
    from sqlalchemy import text
    row = db.execute(text("""
        SELECT a.name, g.evs_total, g.public_chargers, g.dc_fast_chargers,
               g.evs_per_charger, g.coverage_pop_pct, g.gap_index, g.rank,
               g.as_of
        FROM analytics.gap_scores g
        JOIN clean.admin_units a ON a.id = g.admin_unit_id
        WHERE g.admin_unit_id = :unit
        ORDER BY g.as_of DESC LIMIT 1
    """), {"unit": unit}).fetchone()

    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No gap score found for this unit")

    data = dict(row._mapping)

    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data.keys())
        writer.writeheader()
        writer.writerow(data)
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=brief_{unit}.csv"},
        )

    # PDF: basic stub — full implementation in Phase 12
    return {"status": "pdf_not_yet_implemented", "data": data}
