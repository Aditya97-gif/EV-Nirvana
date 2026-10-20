"""Meta router — sources and assumptions endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db import get_db

router = APIRouter()


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    from sqlalchemy import text
    rows = db.execute(text("SELECT * FROM meta.sources ORDER BY id")).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/assumptions")
def list_assumptions(db: Session = Depends(get_db)):
    from sqlalchemy import text
    rows = db.execute(text("SELECT * FROM meta.assumptions ORDER BY key")).fetchall()
    return [dict(r._mapping) for r in rows]
