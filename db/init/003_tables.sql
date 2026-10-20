-- 003_tables.sql
-- Full schema as defined in Section 5 of the Agent Brief.
-- All geometry stored in EPSG:4326. Distance calculations use ST_Transform to projected CRS.

-- ─── META ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS meta.assumptions (
    id          SERIAL PRIMARY KEY,
    key         TEXT NOT NULL UNIQUE,
    value       NUMERIC NOT NULL,
    unit        TEXT,
    source      TEXT,
    notes       TEXT,
    version     TEXT NOT NULL DEFAULT '1.0',
    data_status TEXT NOT NULL CHECK (data_status IN ('observed','derived','analyst_assumption','synthetic')),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meta.sources (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    url         TEXT,
    licence     TEXT,
    accessed_at DATE,
    notes       TEXT
);

-- ─── RAW ─────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS raw.ev_registrations_vahan (
    id            BIGSERIAL PRIMARY KEY,
    state         TEXT,
    rto_code      TEXT,
    rto_name      TEXT,
    year          SMALLINT,
    month         SMALLINT,
    fuel          TEXT,
    vehicle_class TEXT,
    count         INTEGER,
    source        TEXT,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw.chargers_raw (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,          -- 'osm' | 'ocm' | 'gov' | 'other'
    source_id       TEXT,
    name            TEXT,
    operator        TEXT,
    lat             DOUBLE PRECISION,
    lon             DOUBLE PRECISION,
    connector_types TEXT[],
    power_kw        NUMERIC,
    current_type    TEXT,                   -- 'AC' | 'DC' | 'AC/DC'
    status          TEXT,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_payload     JSONB
);

-- ─── CLEAN ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS clean.admin_units (
    id               BIGSERIAL PRIMARY KEY,
    level            TEXT NOT NULL CHECK (level IN ('state','district','city','taluka')),
    name             TEXT NOT NULL,
    name_local       TEXT,
    parent_id        BIGINT REFERENCES clean.admin_units(id),
    census_code      TEXT,
    geom             GEOMETRY(MULTIPOLYGON, 4326),
    boundary_vintage TEXT,
    data_status      TEXT NOT NULL CHECK (data_status IN ('observed','derived','synthetic'))
);

CREATE TABLE IF NOT EXISTS clean.rto_district_map (
    rto_code    TEXT NOT NULL,
    district_id BIGINT NOT NULL REFERENCES clean.admin_units(id),
    share       NUMERIC NOT NULL DEFAULT 1.0 CHECK (share > 0 AND share <= 1),
    method      TEXT,
    data_status TEXT NOT NULL CHECK (data_status IN ('observed','derived','synthetic')),
    PRIMARY KEY (rto_code, district_id)
);

CREATE TABLE IF NOT EXISTS clean.ev_registrations (
    id            BIGSERIAL PRIMARY KEY,
    admin_unit_id BIGINT NOT NULL REFERENCES clean.admin_units(id),
    year          SMALLINT NOT NULL,
    month         SMALLINT NOT NULL,
    vehicle_class TEXT NOT NULL CHECK (vehicle_class IN ('2W','3W','4W','bus','other')),
    count         INTEGER NOT NULL DEFAULT 0,
    data_status   TEXT NOT NULL CHECK (data_status IN ('observed','derived','synthetic'))
);

CREATE TABLE IF NOT EXISTS clean.chargers (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT,
    operator        TEXT,
    geom            GEOMETRY(POINT, 4326) NOT NULL,
    connector_types TEXT[],
    max_power_kw    NUMERIC,
    current_type    TEXT,
    admin_unit_id   BIGINT REFERENCES clean.admin_units(id),
    confidence      NUMERIC CHECK (confidence >= 0 AND confidence <= 1),
    n_sources       SMALLINT NOT NULL DEFAULT 1,
    merged_from     BIGINT[],
    last_verified   DATE,
    data_status     TEXT NOT NULL CHECK (data_status IN ('observed','derived','synthetic'))
);

CREATE TABLE IF NOT EXISTS clean.roads_nh (
    id         BIGSERIAL PRIMARY KEY,
    osm_id     BIGINT,
    ref        TEXT,           -- NH ref e.g. 'NH48'
    name       TEXT,
    geom       GEOMETRY(LINESTRING, 4326) NOT NULL,
    length_km  NUMERIC
);

CREATE TABLE IF NOT EXISTS clean.substations (
    id          BIGSERIAL PRIMARY KEY,
    osm_id      BIGINT,
    name        TEXT,
    voltage_kv  NUMERIC,
    geom        GEOMETRY(POINT, 4326) NOT NULL,
    data_status TEXT NOT NULL CHECK (data_status IN ('observed','derived','synthetic'))
);

CREATE TABLE IF NOT EXISTS clean.demand_features (
    admin_unit_id         BIGINT PRIMARY KEY REFERENCES clean.admin_units(id),
    population            BIGINT,
    urban_share           NUMERIC,
    night_light_mean      NUMERIC,
    poi_commercial_count  INTEGER,
    tourism_index         NUMERIC,
    data_status           TEXT NOT NULL CHECK (data_status IN ('observed','derived','synthetic'))
);

CREATE TABLE IF NOT EXISTS clean.candidate_sites (
    id          BIGSERIAL PRIMARY KEY,
    type        TEXT NOT NULL CHECK (type IN ('fuel','mall','parking','highway_service','other')),
    name        TEXT,
    geom        GEOMETRY(POINT, 4326) NOT NULL,
    source      TEXT
);

-- ─── ANALYTICS ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS analytics.gap_scores (
    id                 BIGSERIAL PRIMARY KEY,
    admin_unit_id      BIGINT NOT NULL REFERENCES clean.admin_units(id),
    as_of              DATE NOT NULL,
    evs_total          INTEGER,
    evs_2w             INTEGER,
    evs_4w             INTEGER,
    public_chargers    INTEGER,
    dc_fast_chargers   INTEGER,
    evs_per_charger    NUMERIC,
    coverage_pop_pct   NUMERIC,
    gap_index          NUMERIC,
    rank               INTEGER,
    weights_version    TEXT NOT NULL DEFAULT '1.0',
    UNIQUE (admin_unit_id, as_of, weights_version)
);

CREATE TABLE IF NOT EXISTS analytics.corridor_gaps (
    id              BIGSERIAL PRIMARY KEY,
    road_id         BIGINT REFERENCES clean.roads_nh(id),
    segment_id      INTEGER,
    geom            GEOMETRY(LINESTRING, 4326),
    max_gap_km      NUMERIC,
    n_dc_chargers   INTEGER,
    gap_flag        BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS analytics.forecasts (
    id            BIGSERIAL PRIMARY KEY,
    admin_unit_id BIGINT NOT NULL REFERENCES clean.admin_units(id),
    vehicle_class TEXT NOT NULL,
    scenario      TEXT NOT NULL CHECK (scenario IN ('baseline','accelerated','conservative')),
    period        DATE NOT NULL,            -- first day of the forecast month
    evs_pred      NUMERIC NOT NULL,
    lo            NUMERIC,
    hi            NUMERIC,
    model_version TEXT NOT NULL DEFAULT '1.0',
    UNIQUE (admin_unit_id, vehicle_class, scenario, period, model_version)
);

CREATE TABLE IF NOT EXISTS analytics.requirements (
    id                 BIGSERIAL PRIMARY KEY,
    admin_unit_id      BIGINT NOT NULL REFERENCES clean.admin_units(id),
    scenario           TEXT NOT NULL,
    horizon_year       SMALLINT NOT NULL,
    vehicle_class      TEXT NOT NULL,
    charger_type       TEXT NOT NULL CHECK (charger_type IN ('AC','DC')),
    required_count     INTEGER NOT NULL,
    existing_count     INTEGER NOT NULL,
    shortfall          INTEGER NOT NULL,
    assumptions_version TEXT NOT NULL DEFAULT '1.0',
    UNIQUE (admin_unit_id, scenario, horizon_year, vehicle_class, charger_type, assumptions_version)
);

CREATE TABLE IF NOT EXISTS analytics.recommended_sites (
    id                 BIGSERIAL PRIMARY KEY,
    run_id             UUID NOT NULL DEFAULT uuid_generate_v4(),
    rank               INTEGER NOT NULL,
    candidate_site_id  BIGINT REFERENCES clean.candidate_sites(id),
    demand_covered     NUMERIC,
    gap_closed         NUMERIC,
    grid_distance_km   NUMERIC,
    reason_text        TEXT,
    scenario           TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
