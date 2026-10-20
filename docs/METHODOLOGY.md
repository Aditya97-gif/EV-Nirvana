# Methodology

## 1. Data Integration

### 1.1 Charger Sources
Sources integrated in priority order:
1. **OpenStreetMap** (Overpass API) — mandatory baseline; ODbL licence
2. **Open Charge Map** (if API key provided) — CC BY-SA
3. **Government open data** (data.gov.in) — ingested if a usable CSV/JSON is found

Raw records stored immutably in `raw.chargers_raw` with `source`, `source_id`, `fetched_at`, and `raw_payload`.

### 1.2 Normalisation
- **Operator names:** alias dictionary (50+ entries) + rapidfuzz token_sort_ratio ≥ 80 threshold
- **Connector types:** mapped to canonical set: CCS2, CHAdeMO, Type2, GB/T, Bharat AC-001, Bharat DC-001, 3-pin
- **AC/DC inference:** based on connector type and power; DC connectors or power ≥ 22 kW → DC
- **Power:** extracted from `charging_station:output`, `maxpower`, or OCM `PowerKW`

### 1.3 Deduplication
- **Spatial clustering:** DBSCAN (ε = 75 m, min_samples=1) using haversine distance — configurable via `dedup_distance_m` assumption
- **Cluster acceptance:** within a cluster, records from different sources are merged if operator fuzzy similarity ≥ 80 OR distance < 25 m
- **Merge rule:** take most complete attribute set; union connector types; mean lat/lon

**Confidence score formula:**
```
confidence = 0.5 × min(n_sources / 3, 1.0)   # source agreement (max at 3+ sources)
           + 0.3 × attribute_completeness      # non-null rate of name, operator, power_kw, current_type
           + 0.2 × recency_score               # 1.0 if verified < 90 days ago, degrades linearly
```

### 1.4 Spatial Join
Each clean charger is spatially joined to `clean.admin_units` using `ST_Within` to assign `admin_unit_id`.

---

## 2. EV Registration Data

VAHAN data mapped from RTO codes to districts via `clean.rto_district_map`:
- Lookup by RTO code prefix (e.g. `MH-01` → Mumbai)
- Fuzzy fallback by RTO name
- Where one RTO spans multiple districts, split by `share` with `method=population_weighted`
- Unresolved RTOs logged to `docs/OPEN_QUESTIONS.md`

Vehicle class mapping:
| VAHAN class | Canonical |
|---|---|
| MOTOR CAR, CAR | 4W |
| MOTOR CYCLE, TWO WHEELER, SCOOTER | 2W |
| THREE WHEELER, AUTO RICKSHAW | 3W |
| BUS, MAXI CAB | bus |
| Others | other |

---

## 3. Gap Assessment

### 3.1 District-Level Indicators

| Indicator | Computation | Unit |
|---|---|---|
| EVs total | `SUM(count)` from `clean.ev_registrations` | vehicles |
| Public chargers | `COUNT(*)` from `clean.chargers` for district | units |
| DC fast chargers | count where `max_power_kw ≥ dc_fast_min_kw` | units |
| EVs per charger | EVs / max(chargers, 1) | ratio |
| Population coverage | Share of population within coverage radius of any charger | fraction |
| Growth rate | YoY change in EV registrations | fraction |

**Zero-charger rule:** When public_chargers = 0, EVs per charger is set to EVs (i.e. treated as maximum denominator-1 condition), not infinity.

### 3.2 Charging Gap Index (CGI)

```
CGI = w₁·norm(EVs/charger)
    + w₂·(1 − norm(coverage_pop_pct))
    + w₃·norm(demand_score)
    + w₄·norm(growth_rate)
    + w₅·norm(corridor_gap_score)
```

**Normalisation:** min-max across all districts in the same run. `weights_version` is stored per row.

Default weights (configurable from UI):
- w₁ = 0.30, w₂ = 0.25, w₃ = 0.20, w₄ = 0.10, w₅ = 0.15

### 3.3 Corridor Gap Analysis

For each NH road segment:
1. Find DC fast chargers within 1 km of the road
2. Project charger positions onto the road using `ST_LineLocatePoint`
3. Compute gaps between consecutive chargers (+ road endpoints)
4. Flag segments where max_gap_km > `corridor_gap_threshold_km` (default 50 km — **UNVERIFIED**)

---

## 4. Forecasting

- **Model:** Facebook Prophet with yearly seasonality
- **Minimum data requirement:** ≥ 24 months for district-level model; else use state-level model × district share from latest year
- **Scenarios:**
  - `baseline`: multiplier = 1.0 (continuation of trend)
  - `accelerated`: multiplier = 1.5 (policy incentives, PM E-DRIVE)
  - `conservative`: multiplier = 0.7 (market headwinds)
- **Intervals:** 95% prediction intervals (Prophet default)
- **Backtest:** train to 12-month cutoff, forecast 12 months, compute MAPE. Results in `reports/backtest.md`.

---

## 5. Charger Requirement Estimation

Formula (per district / scenario / horizon year / vehicle class / charger type):
```
daily_energy_kWh       = forecast_EVs × public_charging_share × avg_kWh_per_EV_per_day
energy_per_charger_day = charger_kW × utilisation_target × operating_hours × charger_efficiency
required_chargers      = ⌈daily_energy / energy_per_charger_day⌉
shortfall              = max(0, required_chargers − existing_chargers)
```

Sensitivity analysis: vary `utilisation_target` ±25%; saved to `reports/sensitivity.csv`.

---

## 6. Site Optimisation

Maximal Covering Location Problem (MCLP):
- **Decision variables:** binary — select k sites from candidate set
- **Objective:** maximise population-weighted coverage within radius R
- **Solver:** PuLP + CBC (open-source, time limit 25s)
- **Candidate set:** OSM fuel stations, malls, parking areas, highway services — filtered to exclude sites within 500m of existing DC charger
- **Demand points:** district centroids weighted by population

---

## 7. Validation

### 7.1 Dedup Validation
- Dedup report: records before/after, cluster size distribution (`reports/dedup_report.md`)
- A 100-pair labelled sample CSV is generated for manual review (human action required)

### 7.2 Rank Stability
Spearman correlation of district CGI ranks when each weight is perturbed ±25%.
Reported in `reports/validation_report.md`.

### 7.3 Backtest
MAPE on 12-month holdout, per district per vehicle class. `reports/backtest.md`.

---

## 8. Limitations

1. Boundaries use Census 2011 vintage — some districts have changed since
2. VAHAN data may be synthetic if not manually exported — clearly labelled
3. OSM charger data is user-contributed and may have gaps/errors
4. Corridor coverage radius for charger proximity is 1 km — a simplification
5. MoP guideline threshold figures are analyst assumptions pending verification
6. Prophet does not model structural breaks (new policies, COVID) explicitly
