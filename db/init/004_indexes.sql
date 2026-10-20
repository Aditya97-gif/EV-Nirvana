-- 004_indexes.sql
-- Performance indexes as specified in the brief

-- GiST indexes on all geometry columns
CREATE INDEX IF NOT EXISTS idx_admin_units_geom          ON clean.admin_units        USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_chargers_geom             ON clean.chargers           USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_roads_nh_geom             ON clean.roads_nh           USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_substations_geom          ON clean.substations        USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_candidate_sites_geom      ON clean.candidate_sites    USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_corridor_gaps_geom        ON analytics.corridor_gaps  USING GIST (geom);

-- btree indexes on frequently filtered columns
CREATE INDEX IF NOT EXISTS idx_chargers_admin_unit       ON clean.chargers           (admin_unit_id);
CREATE INDEX IF NOT EXISTS idx_chargers_source           ON raw.chargers_raw         (source);
CREATE INDEX IF NOT EXISTS idx_ev_reg_admin_unit         ON clean.ev_registrations   (admin_unit_id);
CREATE INDEX IF NOT EXISTS idx_ev_reg_year_month         ON clean.ev_registrations   (year, month);
CREATE INDEX IF NOT EXISTS idx_gap_scores_admin_unit     ON analytics.gap_scores     (admin_unit_id);
CREATE INDEX IF NOT EXISTS idx_forecasts_admin_unit      ON analytics.forecasts      (admin_unit_id, vehicle_class, scenario);
CREATE INDEX IF NOT EXISTS idx_requirements_admin_unit   ON analytics.requirements   (admin_unit_id, scenario, horizon_year);
CREATE INDEX IF NOT EXISTS idx_admin_units_level         ON clean.admin_units        (level);
CREATE INDEX IF NOT EXISTS idx_admin_units_parent        ON clean.admin_units        (parent_id);

-- Trigram index for fuzzy operator name matching
CREATE INDEX IF NOT EXISTS idx_chargers_operator_trgm   ON clean.chargers           USING GIN (operator gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_admin_units_name_trgm    ON clean.admin_units        USING GIN (name gin_trgm_ops);
