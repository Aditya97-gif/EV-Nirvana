.PHONY: up down stop logs pipeline ingest clean-data analytics shell-db migrate clean reset

# ── Start / Stop ───────────────────────────────────────────────────────────────
up:
	@echo "🚀 Starting EV_Nirvana..."
	docker compose up -d
	@echo ""
	@echo "  Web App  →  http://localhost:5173"
	@echo "  API Docs →  http://localhost:8000/docs"

stop:
	docker compose down

logs:
	docker compose logs -f

# ── Full pipeline (first-time setup or after reset) ────────────────────────────
pipeline: ingest clean-data analytics
	@echo "✅ Pipeline complete. Open http://localhost:5173"

ingest:
	@echo "📥 Ingesting data..."
	docker compose exec api python /project/pipeline/ingest/boundaries.py
	docker compose exec api python /project/pipeline/ingest/ocm_chargers.py
	docker compose exec api python /project/pipeline/ingest/vahan.py
	docker compose exec api python /project/pipeline/ingest/population.py
	docker compose exec api python /project/pipeline/ingest/roads.py
	@echo "Ingestion complete."

clean-data:
	@echo "🧹 Cleaning data..."
	docker compose exec api python /project/pipeline/clean/normalise_chargers.py
	docker compose exec api python /project/pipeline/clean/dedup_chargers.py
	docker compose exec api python /project/pipeline/clean/rto_to_district.py
	@echo "Cleaning complete."

analytics:
	@echo "📊 Running analytics..."
	docker compose exec api python /project/pipeline/analytics/gap_index.py
	docker compose exec api python /project/pipeline/analytics/requirement.py
	docker compose exec api python /project/pipeline/analytics/forecast.py
	docker compose exec api python /project/pipeline/analytics/corridor_gaps.py
	docker compose exec api python /project/pipeline/analytics/optimise_sites.py
	docker compose exec api python /project/pipeline/analytics/validate.py
	@echo "Analytics complete."

# ── DB utilities ───────────────────────────────────────────────────────────────
shell-db:
	docker compose exec db psql -U evuser -d ev_infra

migrate:
	@echo "Re-initialising DB schema..."
	docker compose exec db psql -U evuser -d ev_infra -f /docker-entrypoint-initdb.d/001_extensions.sql
	docker compose exec db psql -U evuser -d ev_infra -f /docker-entrypoint-initdb.d/002_schemas.sql
	docker compose exec db psql -U evuser -d ev_infra -f /docker-entrypoint-initdb.d/003_tables.sql
	docker compose exec db psql -U evuser -d ev_infra -f /docker-entrypoint-initdb.d/004_indexes.sql
	docker compose exec db psql -U evuser -d ev_infra -f /docker-entrypoint-initdb.d/005_seed_assumptions.sql

test:
	docker compose exec api pytest /project/tests/ -v --tb=short

# ── Reset everything (deletes all data) ───────────────────────────────────────
reset:
	@echo "⚠️  This will delete all data. Ctrl+C to cancel..."
	@sleep 3
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
