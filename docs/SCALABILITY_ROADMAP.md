# Scalability Roadmap

## Current State (Prototype)
- Single state (Maharashtra) — 36 districts
- ~500–5000 charger records; synthetic VAHAN data
- Single-machine Docker Compose
- GeoJSON for map tiles

---

## Phase 1 → Pilot State (Done)
- Pipeline parameterised by `state` in config
- All code state-agnostic
- Schema supports multiple states

## Phase 2 → 3–5 States (3 months post-finale)
- Run pipeline per state; partition `clean` and `analytics` tables by `state_code`
- Replace GeoJSON layers with **pg_tileserv** or **Martin** vector tile server for performance
- Add **state-level** boundaries as a second tier in `clean.admin_units`
- Estimated data: ~25,000 chargers; ~50M EV registration records/year

## Phase 3 → National (6 months)
- **Automated ingestion:** Apache Airflow or Prefect DAGs replacing manual `make ingest` calls
  - Nightly OSM incremental updates via Overpass changesets
  - Weekly OCM sync
  - Monthly VAHAN refresh (pending API access from MoRTH)
- **Incremental dedup:** compare new raw records against existing clean layer using spatial index; only re-merge changed clusters
- **Data quality checks:** automated null-rate, outlier, and geometry-validity checks per run; alerts on regression
- **Versioned snapshots:** tag each pipeline run with a version; allow time-travel queries

## Data Partnerships (critical path)
- **MoRTH/VAHAN API:** formal data access agreement — real-time RTO registration data
- **BEE EVSE Registry:** official feed of certified charging points
- **DISCOM tie-ups:** substation capacity data (not just location) for grid-aware site selection
- **CPO APIs (ChargeZone, Tata Power, Statiq, etc.):** OCPI-compatible live charger status feed
- **Municipal bodies:** parking and fuel-station GIS layers

## Modelling Upgrades
- **Hierarchical forecasting:** national → state → district coherence using statsforecast
- **Traffic-flow demand:** integrate NHAI traffic count data for corridor prioritisation
- **Grid-capacity-aware optimisation:** add substation capacity constraints to MCLP
- **Equity indicators:** add socioeconomic index (SECC/NSS data) to gap scoring — flag areas where low income and low coverage overlap

## Deployment & Users
- **Cloud:** GCP / AWS — managed Cloud SQL for PostGIS, Cloud Run / ECS for API, Cloud CDN for tiles
- **Role-based access:** MHI (national view), ICAT (technical reports), State Nodal Agencies (state filter), ULBs (city filter)
- **Planning-brief automation:** scheduled PDF reports for each district — auto-emailed to state EV cells
- **Audit trail:** all assumption changes and re-runs logged with user, timestamp, and diff

## Governance
- All assumption changes version-tracked in `meta.assumptions` (version field)
- Source licence changes flagged automatically
- Annual data-quality audit against ground-truth sample

## Phased timeline

| Horizon | Scope | Key additions |
|---|---|---|
| Jan 2027 | 5 states | pg_tileserv, state partitioning, Airflow |
| Jun 2027 | 15 states | VAHAN API, BEE feed, DISCOM data |
| Dec 2027 | All 28 states | CPO live feeds, hierarchical forecasting |
| 2028+ | Live platform | Role-based access, planning-brief automation |
