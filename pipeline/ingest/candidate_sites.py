"""
pipeline/ingest/candidate_sites.py
Thin wrapper — candidate sites are ingested inside substations.py.
Kept as a separate entry point for Makefile compatibility.
"""
from pipeline.ingest.substations import main
if __name__ == "__main__":
    main()
