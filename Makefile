.PHONY: up down ingest analytics test demo clean logs shell-db

# ── Docker ─────────────────────────────────────────────────────────────────────
up:
	@echo "Starting all services..."
	docker compose up -d
	@echo "Services up. API: http://localhost:8000  Web: http://localhost:5173"

down:
	docker compose down

logs:
	docker compose logs -f

# ── Pipeline ───────────────────────────────────────────────────────────────────
ingest:
	@echo "Running ingestion pipeline..."
	docker compose exec api python /app/pipeline/ingest/boundaries.py
	docker compose exec api python /app/pipeline/ingest/osm_chargers.py
	docker compose exec api python /app/pipeline/ingest/ocm_chargers.py
	docker compose exec api python /app/pipeline/ingest/gov_chargers.py
	docker compose exec api python /app/pipeline/ingest/vahan.py
	docker compose exec api python /app/pipeline/ingest/roads.py
	docker compose exec api python /app/pipeline/ingest/population.py
	docker compose exec api python /app/pipeline/ingest/substations.py
	docker compose exec api python /app/pipeline/ingest/nightlights.py
	docker compose exec api python /app/pipeline/ingest/candidate_sites.py
	@echo "Ingestion complete."

clean-data:
	@echo "Running cleaning pipeline..."
	docker compose exec api python /app/pipeline/clean/normalise_chargers.py
	docker compose exec api python /app/pipeline/clean/dedup_chargers.py
	docker compose exec api python /app/pipeline/clean/rto_to_district.py
	@echo "Cleaning complete."

analytics:
	@echo "Running analytics pipeline..."
	docker compose exec api python /app/pipeline/analytics/gap_index.py
	docker compose exec api python /app/pipeline/analytics/corridor_gaps.py
	docker compose exec api python /app/pipeline/analytics/forecast.py
	docker compose exec api python /app/pipeline/analytics/requirement.py
	docker compose exec api python /app/pipeline/analytics/optimise_sites.py
	docker compose exec api python /app/pipeline/analytics/validate.py
	@echo "Analytics complete."

run-all:
	docker compose exec api python /app/pipeline/run_all.py

# ── Testing ────────────────────────────────────────────────────────────────────
test:
	docker compose exec api pytest /app/tests/ -v --tb=short

lint:
	docker compose exec api ruff check /app/
	docker compose exec api mypy /app/ --ignore-missing-imports

# ── DB utilities ───────────────────────────────────────────────────────────────
shell-db:
	docker compose exec db psql -U evuser -d ev_infra

migrate:
	@echo "Re-initialising DB schema (idempotent)..."
	docker compose exec db psql -U evuser -d ev_infra -f /docker-entrypoint-initdb.d/001_extensions.sql
	docker compose exec db psql -U evuser -d ev_infra -f /docker-entrypoint-initdb.d/002_schemas.sql
	docker compose exec db psql -U evuser -d ev_infra -f /docker-entrypoint-initdb.d/003_tables.sql
	docker compose exec db psql -U evuser -d ev_infra -f /docker-entrypoint-initdb.d/004_indexes.sql
	docker compose exec db psql -U evuser -d ev_infra -f /docker-entrypoint-initdb.d/005_seed_assumptions.sql

# ── Demo ───────────────────────────────────────────────────────────────────────
demo:
	@echo "Starting full demo pipeline for the configured demo state..."
	$(MAKE) up
	@sleep 5
	$(MAKE) ingest
	$(MAKE) clean-data
	$(MAKE) analytics
	@echo "Demo pipeline done. Open http://localhost:5173 to view."

# ── Housekeeping ───────────────────────────────────────────────────────────────
clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
