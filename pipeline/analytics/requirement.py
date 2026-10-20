"""
pipeline/analytics/requirement.py
Phase 8 — Charger requirement estimation per district/scenario/horizon year.

Formula (from Section 8 of brief):
  daily_energy_kWh       = forecast_EVs * public_charging_share * avg_kWh_per_EV_per_day
  energy_per_charger_day = charger_kW * utilisation * operating_hours * efficiency
  required_chargers      = ceil(daily_energy_kWh / energy_per_charger_day)
  shortfall              = max(0, required_chargers - existing_chargers)

All parameters from meta.assumptions. Sensitivity table stored in reports/.
"""
import logging
import math
import os
from pathlib import Path

import pandas as pd
import yaml
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(os.environ.get("PROJECT_ROOT", str(Path(__file__).resolve().parents[3])))
with open(ROOT / "config" / "project.yaml") as f:
    CONFIG = yaml.safe_load(f)

DB_URL = (
    f"postgresql+psycopg2://{os.environ.get('DB_USER','evuser')}:"
    f"{os.environ.get('DB_PASSWORD','password')}@"
    f"{os.environ.get('DB_HOST','db')}:"
    f"{os.environ.get('DB_PORT','5432')}/"
    f"{os.environ.get('DB_NAME','ev_infra')}"
)

HORIZON_YEARS = [2027, 2030]
SCENARIOS = ["baseline", "accelerated", "conservative"]
VEHICLE_CLASSES = ["2W", "3W", "4W", "bus"]
ASSUMPTIONS_VERSION = "1.0"


def load_all_assumptions(conn) -> dict:
    rows = conn.execute(text("SELECT key, value FROM meta.assumptions")).fetchall()
    return {r.key: float(r.value) for r in rows}


def required_chargers(evs: float, pub_share: float, kwh_per_ev: float,
                      charger_kw: float, utilisation: float,
                      op_hours: float, efficiency: float) -> int:
    daily_energy = evs * pub_share * kwh_per_ev
    energy_per_charger = charger_kw * utilisation * op_hours * efficiency
    if energy_per_charger == 0:
        return 0
    return math.ceil(daily_energy / energy_per_charger)


def main():
    logger.info("=== Charger Requirement Estimation ===")
    engine = create_engine(DB_URL, pool_pre_ping=True)

    with engine.connect() as conn:
        A = load_all_assumptions(conn)

        # Load existing charger counts per district per type
        existing = {}
        rows = conn.execute(text("""
            SELECT admin_unit_id,
                   SUM(CASE WHEN max_power_kw >= :dc THEN 1 ELSE 0 END) AS dc,
                   SUM(CASE WHEN max_power_kw < :dc OR max_power_kw IS NULL THEN 1 ELSE 0 END) AS ac
            FROM clean.chargers WHERE admin_unit_id IS NOT NULL
            GROUP BY admin_unit_id
        """), {"dc": A.get("dc_fast_min_kw", 30)}).fetchall()
        for r in rows:
            existing[r.admin_unit_id] = {"DC": int(r.dc), "AC": int(r.ac)}

        districts = conn.execute(text(
            "SELECT id FROM clean.admin_units WHERE level='district'"
        )).fetchall()

    inserted = 0
    sensitivity_rows = []

    for dist in districts:
        uid = dist.id
        ex = existing.get(uid, {"DC": 0, "AC": 0})

        for scenario in SCENARIOS:
            for horizon in HORIZON_YEARS:
                for vc in VEHICLE_CLASSES:
                    # Get forecast EV count for horizon year
                    with engine.connect() as conn:
                        evs_pred = conn.execute(text("""
                            SELECT COALESCE(SUM(evs_pred), 0) FROM analytics.forecasts
                            WHERE admin_unit_id=:uid AND vehicle_class=:vc AND scenario=:sc
                              AND EXTRACT(YEAR FROM period)=:yr
                        """), {"uid": uid, "vc": vc, "sc": scenario, "yr": horizon}).scalar() or 0.0

                    for charger_type, charger_kw_key in [("AC", "charger_kw_ac"), ("DC", "charger_kw_dc")]:
                        pub_share = A.get(f"public_charging_share_{vc}", 0.20)
                        kwh_per_ev = A.get(f"kwh_per_day_{vc}", 5.0)
                        charger_kw = A.get(charger_kw_key, 7.4 if charger_type == "AC" else 30)
                        util = A.get("utilisation_target", 0.15)
                        op_h = A.get("operating_hours_per_day", 20)
                        eff  = A.get("charger_efficiency", 0.90)

                        req = required_chargers(evs_pred, pub_share, kwh_per_ev, charger_kw, util, op_h, eff)
                        exist_cnt = ex.get(charger_type, 0)
                        shortfall = max(0, req - exist_cnt)

                        with engine.begin() as conn:
                            conn.execute(text("""
                                INSERT INTO analytics.requirements
                                    (admin_unit_id, scenario, horizon_year, vehicle_class,
                                     charger_type, required_count, existing_count, shortfall, assumptions_version)
                                VALUES
                                    (:uid, :sc, :yr, :vc, :ct, :req, :ex, :sf, :av)
                                ON CONFLICT (admin_unit_id, scenario, horizon_year, vehicle_class, charger_type, assumptions_version)
                                DO UPDATE SET required_count=EXCLUDED.required_count,
                                             existing_count=EXCLUDED.existing_count,
                                             shortfall=EXCLUDED.shortfall
                            """), {
                                "uid": uid, "sc": scenario, "yr": horizon, "vc": vc,
                                "ct": charger_type, "req": req, "ex": exist_cnt, "sf": shortfall,
                                "av": ASSUMPTIONS_VERSION,
                            })
                            inserted += 1

                        # Sensitivity: vary utilisation ±25%
                        for delta_label, delta in [("-25%", 0.75), ("+25%", 1.25)]:
                            req_s = required_chargers(evs_pred, pub_share, kwh_per_ev,
                                                       charger_kw, util * delta, op_h, eff)
                            sensitivity_rows.append({
                                "admin_unit_id": uid, "scenario": scenario, "horizon": horizon,
                                "vehicle_class": vc, "charger_type": charger_type,
                                "parameter": "utilisation", "delta": delta_label,
                                "required_count": req_s,
                            })

    # Save sensitivity table
    if sensitivity_rows:
        reports_dir = ROOT / "reports"
        reports_dir.mkdir(exist_ok=True)
        pd.DataFrame(sensitivity_rows).to_csv(reports_dir / "sensitivity.csv", index=False)
        logger.info("Sensitivity table saved to reports/sensitivity.csv")

    logger.info("Requirement estimation complete — %d rows inserted.", inserted)


if __name__ == "__main__":
    main()
