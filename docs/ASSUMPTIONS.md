# Assumptions Register

All model assumptions with their values, units, sources, and data_status.
Generated from `config/assumptions.yaml` and `meta.assumptions` table.

> **ANALYST ASSUMPTION** = placeholder value requiring verification/replacement with sourced data.
> **UNVERIFIED** = value may be correct but source has not been confirmed from original document.

| Key | Value | Unit | Data Status | Source | Notes |
|---|---|---|---|---|---|
| dedup_distance_m | 75 | metres | analyst_assumption | — | Tune on labelled sample |
| dc_fast_min_kw | 30 | kW | analyst_assumption | — | UNVERIFIED — check BEE/MoP |
| coverage_radius_urban_km | 3 | km | analyst_assumption | — | UNVERIFIED — check MoP CPO guidelines |
| coverage_radius_highway_km | 25 | km | analyst_assumption | — | UNVERIFIED |
| corridor_gap_threshold_km | 50 | km | analyst_assumption | — | UNVERIFIED — check MoP 2023 |
| public_charging_share_2w | 0.10 | fraction | analyst_assumption | — | Most 2W charge at home |
| public_charging_share_3w | 0.40 | fraction | analyst_assumption | — | e-Rickshaw commercial charging |
| public_charging_share_4w | 0.30 | fraction | analyst_assumption | CEEW/RMI indicative | Range 0.20–0.40 |
| public_charging_share_bus | 0.20 | fraction | analyst_assumption | — | Most e-buses use depot |
| kwh_per_day_2w | 1.5 | kWh/veh/day | analyst_assumption | — | ~50 km × 30 Wh/km |
| kwh_per_day_3w | 6.0 | kWh/veh/day | analyst_assumption | — | ~120 km × 50 Wh/km |
| kwh_per_day_4w | 8.0 | kWh/veh/day | analyst_assumption | — | ~50 km × 160 Wh/km |
| kwh_per_day_bus | 150.0 | kWh/veh/day | analyst_assumption | — | ~250 km × 600 Wh/km |
| charger_kw_ac | 7.4 | kW | analyst_assumption | — | Typical Type 2 AC |
| charger_kw_dc | 30.0 | kW | analyst_assumption | — | UNVERIFIED min DC |
| utilisation_target | 0.15 | fraction | analyst_assumption | — | Industry avg India 2023-24 |
| operating_hours_per_day | 20 | hours | analyst_assumption | — | — |
| charger_efficiency | 0.90 | fraction | analyst_assumption | — | Mfr specs 88–95% |
| cgi_weight_evs_per_charger | 0.30 | fraction | analyst_assumption | — | Adjustable in UI |
| cgi_weight_coverage | 0.25 | fraction | analyst_assumption | — | Adjustable in UI |
| cgi_weight_demand_score | 0.20 | fraction | analyst_assumption | — | Adjustable in UI |
| cgi_weight_growth_rate | 0.10 | fraction | analyst_assumption | — | Adjustable in UI |
| cgi_weight_corridor_gap | 0.15 | fraction | analyst_assumption | — | Adjustable in UI |

_All values are editable via `config/assumptions.yaml` → re-seed with `make migrate`._
