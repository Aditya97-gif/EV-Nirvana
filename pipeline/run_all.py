"""
pipeline/run_all.py — Orchestrate the full pipeline end-to-end.
"""
import logging
import subprocess, sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

STEPS = [
    # Ingestion
    "pipeline.ingest.boundaries",
    "pipeline.ingest.osm_chargers",
    "pipeline.ingest.ocm_chargers",
    "pipeline.ingest.gov_chargers",
    "pipeline.ingest.vahan",
    "pipeline.ingest.roads",
    "pipeline.ingest.population",
    "pipeline.ingest.substations",
    "pipeline.ingest.nightlights",
    # Cleaning
    "pipeline.clean.normalise_chargers",
    "pipeline.clean.dedup_chargers",
    "pipeline.clean.rto_to_district",
    # Analytics
    "pipeline.analytics.corridor_gaps",
    "pipeline.analytics.gap_index",
    "pipeline.analytics.forecast",
    "pipeline.analytics.requirement",
    "pipeline.analytics.optimise_sites",
    "pipeline.analytics.validate",
]


def run_step(module: str) -> bool:
    logger.info(">>> Running %s", module)
    result = subprocess.run([sys.executable, "-m", module], capture_output=False)
    if result.returncode != 0:
        logger.error("Step FAILED: %s (exit %d)", module, result.returncode)
        return False
    logger.info("<<< Done: %s", module)
    return True


def main():
    logger.info("=== Full Pipeline Run ===")
    failed = []
    for step in STEPS:
        ok = run_step(step)
        if not ok:
            failed.append(step)

    if failed:
        logger.error("Pipeline completed with %d failed steps: %s", len(failed), failed)
        sys.exit(1)
    else:
        logger.info("All pipeline steps completed successfully.")


if __name__ == "__main__":
    main()
