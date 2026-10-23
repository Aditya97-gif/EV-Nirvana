<div align="center">

# ⚡ EV_Nirvana

### India's Open-Source EV Charging Infrastructure Intelligence Platform

*Map the gaps. Forecast demand. Optimise placement.*

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev)
[![PostgreSQL](https://img.shields.io/badge/PostGIS-15--3.4-336791?style=flat-square&logo=postgresql&logoColor=white)](https://postgis.net)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docs.docker.com/compose)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

<br/>

![EV_Nirvana Banner](https://img.shields.io/badge/Maharashtra-34%20Districts%20Analysed-ff6b35?style=for-the-badge)
![Chargers](https://img.shields.io/badge/Chargers-1%2C840%20Mapped-39d98a?style=for-the-badge)
![Forecasts](https://img.shields.io/badge/Forecasts-3%20Year%20Horizon-4da6ff?style=for-the-badge)

</div>

---

## 🗺️ What is EV_Nirvana?

EV_Nirvana is a **data-driven web platform** that maps India's EV charging infrastructure, identifies underserved districts, and generates intelligent site placement recommendations — powered entirely by open public data.

It combines real charger locations (OSM + Open Charge Map), EV registration records (VAHAN), population density, and National Highway road networks into a single interactive analytics dashboard.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🗺️ **Interactive Map** | CARTO Dark Matter vector basemap with 1,840+ real charger locations, clustered by zoom level |
| 📊 **Charging Gap Index** | Composite district-level score ranking infrastructure need (CGI) |
| 📈 **EV Demand Forecast** | Holt-Winters time-series model across 3 scenarios — baseline, accelerated, conservative |
| 🛣️ **Corridor Gap Analysis** | Flags National Highway segments with insufficient DC fast-charger coverage |
| 📍 **Site Optimisation** | MCLP solver recommends top 10 charger sites to maximise population coverage |
| 🎛️ **What-If Simulator** | Adjust CGI weights interactively and recompute rankings in real-time |
| 🔄 **Full Data Pipeline** | Automated ingestion → cleaning → dedup → analytics → validation |

---

## 🖥️ Tech Stack

```
┌─────────────────────────────────────────────────────┐
│                    EV_Nirvana                        │
├──────────────┬──────────────────┬───────────────────┤
│   Frontend   │     Backend      │     Database      │
│              │                  │                   │
│  React 18    │  FastAPI 0.115   │  PostgreSQL 15    │
│  TypeScript  │  SQLAlchemy      │  PostGIS 3.4      │
│  MapLibre GL │  Uvicorn         │                   │
│  Recharts    │  psycopg2        │                   │
├──────────────┴──────────────────┴───────────────────┤
│                    Data Pipeline                     │
│   GeoPandas · OSMnx · statsmodels · PuLP · Shapely  │
├─────────────────────────────────────────────────────┤
│              Infrastructure: Docker Compose          │
└─────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) 4.x
- Git

### 1 — Clone & Configure

```bash
git clone <repo-url> EV_Nirvana
cd EV_Nirvana

cp .env.example .env
# Edit .env — set your keys (see Configuration below)
```

### 2 — Start the App

```bash
make up
```

### 3 — (First time only) Run the Data Pipeline

```bash
make pipeline
```

> ☕ Takes ~5 minutes. Fetches boundaries, chargers, registrations, roads, and runs all analytics.

### 4 — Open in Browser

| | URL |
|---|---|
| 🌐 Web App | http://localhost:5173 |
| 📖 API Docs | http://localhost:8000/docs |
| 🐘 Database | `localhost:5432` · user: `evuser` |

---

## 🛠️ Daily Commands

```bash
make up          # Start the app
make stop        # Stop the app
make logs        # Tail all service logs
make shell-db    # Open a psql shell
make test        # Run test suite
make reset       # ⚠️  Wipe all data and start fresh
```

---

## 📁 Project Structure

```
EV_Nirvana/
│
├── 🌐 web/                    React + MapLibre GL frontend
│   └── src/App.tsx            Main app component
│
├── ⚡ api/                    FastAPI application
│   └── routers/               chargers · gaps · forecasts · sites · meta
│
├── 🔄 pipeline/
│   ├── ingest/                Boundaries · OCM · VAHAN · Population · Roads
│   ├── clean/                 Normalise · Dedup · RTO mapping
│   └── analytics/             Gap index · Forecast · Corridor gaps · MCLP
│
├── 🐘 db/                     PostgreSQL init scripts & schema
├── ⚙️  config/project.yaml    State, bounding box, CRS settings
├── 📊 reports/                Auto-generated pipeline reports
├── 🧪 tests/                  Unit and integration tests
├── 📚 docs/                   Technical documentation
│
├── docker-compose.yml
├── Makefile
└── .env
```

---

## 🗄️ Data Sources

| Source | Data | Licence |
|---|---|---|
| [Open Charge Map](https://openchargemap.org) | 1,840 charger POIs | CC BY-SA |
| [OpenStreetMap](https://www.openstreetmap.org) | Road network, amenities | ODbL |
| [VAHAN](https://vahan.parivahan.gov.in) | EV registration records | Govt. of India |
| [GADM](https://gadm.org) | Administrative boundaries | Academic use |
| [Overpass API](https://overpass-api.de) | National Highway geometries | ODbL |

---

## ⚙️ Configuration

**`.env`** — environment variables:

```bash
DB_PASSWORD=your_db_password
OCM_API_KEY=your_key        # https://openchargemap.org/site/develop
CARTO_API_KEY=your_key      # https://carto.com/developers/basemaps
```

**`config/project.yaml`** — geospatial settings:

```yaml
state: Maharashtra
bbox: [72.6, 15.6, 80.9, 22.1]
project_crs: EPSG:32643
```

---

## 📐 Methodology

The **Charging Gap Index (CGI)** is a weighted composite of:

| Indicator | Default Weight |
|---|---|
| EVs per charger | 30% |
| Population coverage | 25% |
| Demand score | 20% |
| Corridor gap | 15% |
| Growth rate | 10% |

Weights are user-adjustable via the **What-If Simulator** tab.

> See [docs/METHODOLOGY.md](docs/METHODOLOGY.md) for full details.

---

## 📚 Documentation

- [**Methodology**](docs/METHODOLOGY.md) — CGI formula, statistical model details
- [**Data Strategy**](docs/DATA_STRATEGY.md) — Source selection and quality assessment
- [**Assumptions**](docs/ASSUMPTIONS.md) — Model parameters and justifications
- [**Scalability Roadmap**](docs/SCALABILITY_ROADMAP.md) — Path to pan-India coverage

---

## 📜 License

MIT © EV_Nirvana Contributors

---

<div align="center">

*Built with 🔋 to accelerate India's EV transition*

</div>
