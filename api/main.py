"""
EV_Nirvana — FastAPI Application Root
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routers import chargers, admin_units, gaps, forecasts, requirements, sites, export, meta as meta_router
from db import engine, Base

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("EV Infra API starting up")
    yield
    logger.info("EV Infra API shutting down")


app = FastAPI(
    title="EV_Nirvana API",
    description=(
        "Data-driven EV charging infrastructure planning platform for India. "
        "An open-source EV charging infrastructure analytics platform for India."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    redirect_slashes=False,   # prevent 307 redirects that break fetch() calls
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(admin_units.router, prefix="/admin-units", tags=["Admin Units"])
app.include_router(chargers.router,    prefix="/chargers",    tags=["Chargers"])
app.include_router(gaps.router,        prefix="/gaps",         tags=["Gap Analysis"])
app.include_router(forecasts.router,   prefix="/forecasts",    tags=["Forecasts"])
app.include_router(requirements.router,prefix="/requirements", tags=["Requirements"])
app.include_router(sites.router,       prefix="/recommend",    tags=["Site Recommendations"])
app.include_router(export.router,      prefix="/export",       tags=["Export"])
app.include_router(meta_router.router, prefix="/meta",         tags=["Metadata"])


@app.get("/", include_in_schema=False)
async def root():
    return {"status": "ok", "message": "EV_Nirvana API", "docs": "/docs"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
