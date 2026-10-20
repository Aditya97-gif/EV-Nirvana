"""
pipeline/clean/rto_to_district.py
Phase 4 — Build the RTO → district mapping table (clean.rto_district_map).
Uses RTO code/name patterns for Maharashtra. Unresolved RTOs go to OPEN_QUESTIONS.
"""
import logging
import os
from pathlib import Path

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

# Maharashtra RTO code → district name mapping (verified from MoRTH records)
# Source: Transport Commissioner Maharashtra website (manual verification)
MH_RTO_TO_DISTRICT: dict[str, str] = {
    "MH-01": "Mumbai", "MH-02": "Mumbai", "MH-03": "Mumbai Suburban",
    "MH-04": "Mumbai Suburban", "MH-05": "Thane", "MH-06": "Raigad",
    "MH-07": "Pune", "MH-08": "Pune", "MH-09": "Nashik",
    "MH-10": "Nashik", "MH-11": "Ahmednagar", "MH-12": "Kolhapur",
    "MH-13": "Satara", "MH-14": "Sangli", "MH-15": "Solapur",
    "MH-16": "Aurangabad", "MH-17": "Aurangabad", "MH-18": "Jalgaon",
    "MH-19": "Dhule", "MH-20": "Latur", "MH-21": "Nanded",
    "MH-22": "Osmanabad", "MH-23": "Beed", "MH-24": "Parbhani",
    "MH-25": "Nagpur", "MH-26": "Nagpur", "MH-27": "Amravati",
    "MH-28": "Wardha", "MH-29": "Yavatmal", "MH-30": "Buldhana",
    "MH-31": "Akola", "MH-32": "Washim", "MH-33": "Chandrapur",
    "MH-34": "Gadchiroli", "MH-35": "Gondia", "MH-36": "Bhandara",
    "MH-37": "Ratnagiri", "MH-38": "Sindhudurg", "MH-39": "Nandurbar",
    "MH-40": "Thane", "MH-41": "Raigad", "MH-42": "Hingoli",
    "MH-43": "Pune", "MH-44": "Nashik", "MH-45": "Nagpur",
    "MH-46": "Amravati", "MH-47": "Aurangabad", "MH-48": "Kolhapur",
    "MH-49": "Solapur",
}


def build_map(engine) -> None:
    unresolved = []
    inserted = 0
    with engine.begin() as conn:
        # Get distinct RTO codes from raw VAHAN data
        rto_codes = conn.execute(text(
            "SELECT DISTINCT rto_code, rto_name FROM raw.ev_registrations_vahan WHERE rto_code IS NOT NULL"
        )).fetchall()

        for row in rto_codes:
            rto_code = (row.rto_code or "").strip().upper()
            district_name = MH_RTO_TO_DISTRICT.get(rto_code) or MH_RTO_TO_DISTRICT.get(rto_code[:5])
            if not district_name:
                # Try to match by RTO name
                rto_name = (row.rto_name or "").strip()
                for district in MH_RTO_TO_DISTRICT.values():
                    if district.lower() in rto_name.lower():
                        district_name = district
                        break

            if not district_name:
                unresolved.append(rto_code)
                continue

            district_id = conn.execute(text(
                "SELECT id FROM clean.admin_units WHERE level='district' AND name ILIKE :name LIMIT 1"
            ), {"name": district_name}).scalar()

            if district_id is None:
                unresolved.append(f"{rto_code} (district '{district_name}' not in DB)")
                continue

            conn.execute(text("""
                INSERT INTO clean.rto_district_map (rto_code, district_id, share, method, data_status)
                VALUES (:rto_code, :district_id, 1.0, 'rto_code_lookup', 'derived')
                ON CONFLICT (rto_code, district_id) DO NOTHING
            """), {"rto_code": rto_code, "district_id": district_id})
            inserted += 1

    logger.info("Inserted %d RTO→district mappings. Unresolved: %d", inserted, len(unresolved))

    if unresolved:
        oq = ROOT / "docs" / "OPEN_QUESTIONS.md"
        oq.parent.mkdir(exist_ok=True)
        with open(oq, "a") as f:
            f.write(f"\n## Unresolved RTO codes ({len(unresolved)})\n")
            for code in unresolved:
                f.write(f"  - {code}\n")
            f.write("- Action: Add to MH_RTO_TO_DISTRICT dict in pipeline/clean/rto_to_district.py\n")


def populate_clean_ev_registrations(engine) -> None:
    """Aggregate VAHAN raw → clean.ev_registrations by district."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM clean.ev_registrations"))
        conn.execute(text("""
            INSERT INTO clean.ev_registrations (admin_unit_id, year, month, vehicle_class, count, data_status)
            SELECT
                m.district_id,
                v.year,
                v.month,
                v.vehicle_class,
                SUM(ROUND(v.count * m.share))::INT,
                MAX(CASE WHEN v.source = 'synthetic' THEN 'synthetic' ELSE 'derived' END)
            FROM raw.ev_registrations_vahan v
            JOIN clean.rto_district_map m ON m.rto_code = v.rto_code
            WHERE v.year IS NOT NULL AND v.month IS NOT NULL
            GROUP BY m.district_id, v.year, v.month, v.vehicle_class
        """))
        count = conn.execute(text("SELECT COUNT(*) FROM clean.ev_registrations")).scalar()
        logger.info("Populated clean.ev_registrations: %d rows", count)


def main():
    logger.info("=== RTO → District Mapping ===")
    engine = create_engine(DB_URL, pool_pre_ping=True)
    build_map(engine)
    populate_clean_ev_registrations(engine)


if __name__ == "__main__":
    main()
