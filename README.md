# EV_Nirvana

A data-driven web platform mapping India's EV charging infrastructure, identifying underserved regions, and generating intelligent charger placement recommendations — powered entirely by open public data.

---

## Overview

EV_Nirvana analyses the gap between EV adoption and charging availability across Maharashtra, combining geospatial data, registration records, and population metrics into an interactive dashboard. The platform produces district-level gap scores, 3-year EV demand forecasts, and optimal site recommendations using the Maximal Covering Location Problem (MCLP).

---

## Features

- **Interactive Map** — CARTO Dark Matter basemap with 1,900+ real EV charger locations (OSM + Open Charge Map)
- **Charging Gap Index (CGI)** — Composite score ranking districts by infrastructure need
- **EV Demand Forecasting** — Holt-Winters time-series model across 3 scenarios (baseline, accelerated, conservative)
- **Corridor Gap Analysis** — Identifies National Highway segments with insufficient DC fast-charger coverage
- **Site Optimisation** — MCLP solver recommends optimal charger locations to maximise population coverage
- **What-If Simulator** — Adjustable weights for real-time CGI recomputation
- **Full Data Pipeline** — Automated ingestion from OSM, OCM, and population sources into PostGIS

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React + TypeScript + MapLibre GL JS + Recharts |
| **Backend** | FastAPI + SQLAlchemy + PostGIS |
| **Database** | PostgreSQL 15 + PostGIS 3 |
| **Pipeline** | Python (GeoPandas, OSMnx, statsmodels, PuLP) |
| **Infrastructure** | Docker Compose |
| **Map Tiles** | CARTO Dark Matter (vector) |

---

## Quick Start

### Prerequisites
- Docker Desktop 4.x
- Git

### Run

```bash
git clone <repo-url> EV_Nirvana
cd EV_Nirvana

# 1. Configure environment
cp .env.example .env
# Edit .env — set DB_PASSWORD, OCM_API_KEY, CARTO_API_KEY

# 2. Start services
docker compose up -d

# 3. Run the data pipeline
docker compose exec api python pipeline/ingest/boundaries.py
docker compose exec api python pipeline/ingest/chargers_osm.py
docker compose exec api python pipeline/ingest/chargers_ocm.py
docker compose exec api python pipeline/ingest/vahan.py
docker compose exec api python pipeline/ingest/population.py
docker compose exec api python pipeline/ingest/roads.py
docker compose exec api python pipeline/clean/normalise.py
docker compose exec api python pipeline/clean/dedup.py
docker compose exec api python pipeline/clean/rto_mapping.py
docker compose exec api python pipeline/analytics/gap_index.py
docker compose exec api python pipeline/analytics/requirements.py
docker compose exec api python pipeline/analytics/forecast.py
docker compose exec api python pipeline/analytics/corridor_gaps.py
docker compose exec api python pipeline/analytics/optimise_sites.py
docker compose exec api python pipeline/analytics/validate.py
```

### Access

| Service | URL |
|---|---|
| Web App | http://localhost:5173 |
| API Docs | http://localhost:8000/docs |
| Database | `localhost:5432` (user: `evuser`) |

---

## Project Structure

```
EV_Nirvana/
├── api/                  # FastAPI application
│   └── routers/          # Endpoint handlers (chargers, gaps, forecasts, ...)
├── pipeline/
│   ├── ingest/           # Data ingestion scripts
│   ├── clean/            # Normalisation, deduplication, mapping
│   └── analytics/        # Gap index, forecasting, optimisation, validation
├── web/                  # React frontend (Vite)
│   └── src/
│       └── App.tsx       # Main application component
├── db/                   # Database migrations and schema
├── config/
│   └── project.yaml      # State config, bounding box, CRS
├── data/                 # Raw and processed data (gitignored)
├── reports/              # Auto-generated pipeline reports
├── docs/                 # Technical documentation
├── tests/                # Unit and integration tests
├── docker-compose.yml
├── Makefile
└── .env.example
```

---

## Data Sources

| Source | Data | Licence |
|---|---|---|
| OpenStreetMap | Charger locations, road network | ODbL |
| Open Charge Map | Charger POIs, operator info | CC BY-SA |
| GADM / Geohacker | Administrative boundaries | Academic use |
| Overpass API | National Highway geometries | ODbL |

---

## API Reference

```
GET /chargers          All charger locations (supports bbox, min_kw filters)
GET /gaps              District-level Charging Gap Index scores
GET /forecasts         EV registration forecasts by district and scenario
GET /requirements      Charger requirement estimates per district
GET /recommend         Optimised site recommendations (MCLP)
GET /export/brief      Full data export (JSON)
GET /meta/assumptions  Model assumptions and parameters
```

Full interactive docs at **http://localhost:8000/docs**.

---

## Configuration

Key settings in `.env`:

```bash
DB_PASSWORD=your_password
OCM_API_KEY=your_open_charge_map_key   # https://openchargemap.org/site/develop
CARTO_API_KEY=your_carto_key           # https://carto.com
```

State and geospatial config in `config/project.yaml`:

```yaml
state: Maharashtra
bbox: [72.6, 15.6, 80.9, 22.1]
project_crs: EPSG:32643
```

---

## Docs

- [Methodology](docs/METHODOLOGY.md) — CGI formula, data processing decisions
- [Data Strategy](docs/DATA_STRATEGY.md) — Source selection and quality assessment
- [Assumptions](docs/ASSUMPTIONS.md) — Model parameters and justifications
- [Scalability Roadmap](docs/SCALABILITY_ROADMAP.md) — Path to national coverage

---

## License

MIT
