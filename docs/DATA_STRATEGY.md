# Data Strategy

See `docs/ROUND1_SUBMISSION.md` Section 3 (Data Strategy table) for the summary.

## Source Priority

1. **VAHAN** (MoRTH) — authoritative EV registration data. Manual export until API access.
2. **OpenStreetMap** — charger locations (ODbL, free). Mandatory baseline.
3. **Open Charge Map** — supplementary charger data (CC BY-SA, free API key).
4. **data.gov.in** — supplementary government charger lists (if available).
5. **Census 2011** — district population (public domain).
6. **WorldPop** — updated population raster (CC BY 4.0, free download).

## Fallback Chain

| Primary | Fallback | Status |
|---|---|---|
| VAHAN API | Manual CSV export | Documented in VAHAN_MANUAL_EXPORT.md |
| Manual VAHAN export | Synthetic allocation by population share | Active (labelled synthetic) |
| DataMeet boundaries | GADM Level 2 | Implemented |
| OCM API | OSM-only | Active if no key |
| WorldPop raster | Census 2011 totals | Active |
| Night lights | POI count proxy | Active |

## Data Quality Controls

- All raw files saved immutably with timestamp
- `data_status` field on every record
- Dedup confidence scores
- Automated sanity checks in validate.py
- OPEN_QUESTIONS.md for all unresolved blockers
