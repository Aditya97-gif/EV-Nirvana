-- 001_extensions.sql
-- Enable required PostgreSQL extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- fuzzy text matching
CREATE EXTENSION IF NOT EXISTS unaccent;   -- accent-insensitive search
CREATE EXTENSION IF NOT EXISTS "uuid-ossp"; -- UUID generation
