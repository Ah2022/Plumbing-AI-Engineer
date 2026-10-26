-- =====================================================================
-- PLUMBING DESIGN ENGINE — DATABASE SCHEMA
-- SQLite (Phase 1). Designed to migrate cleanly to PostgreSQL later:
-- no SQLite-only features are used beyond AUTOINCREMENT / TEXT dates.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 1. CODE / RULE DATABASE  (populated from the supplied rules JSON)
-- ---------------------------------------------------------------------

CREATE TABLE codes (
    code_id         TEXT PRIMARY KEY,      -- e.g. 'IPC', 'UPC', 'EGYPT_LOCAL', 'SAUDI_SBC_701'
    code_name       TEXT NOT NULL,         -- e.g. '2024 International Plumbing Code (IPC)'
    jurisdiction    TEXT,                  -- e.g. 'US model code', 'Egypt', 'Saudi Arabia'
    schema_version  TEXT,
    notes           TEXT
);

-- Qualitative / condition-action compliance rules (source: rules JSON).
-- These drive the COMPLIANCE / QA-QC engine, NOT the numeric sizing engine.
CREATE TABLE code_rules (
    rule_id         TEXT PRIMARY KEY,      -- e.g. 'IPC-W-002'
    code_id         TEXT NOT NULL REFERENCES codes(code_id),
    domain          TEXT NOT NULL CHECK (domain IN ('water','drainage','vent','storm','hot_water','tank','pump')),
    severity        TEXT NOT NULL CHECK (severity IN ('error','warning','info')),
    condition_text  TEXT NOT NULL,         -- human-readable condition to evaluate
    action_text     TEXT NOT NULL,         -- expected checker response
    reference       TEXT,                  -- code chapter/section
    source_note     TEXT,
    parameters_json TEXT,                  -- optional JSON of numeric parameters, e.g. {"static_pressure_threshold_psi": 80}
    has_predicate    INTEGER NOT NULL DEFAULT 0  -- 1 if compliance/rule_registry.py has a coded predicate for this rule_id
);

-- Numeric design tables (fixture-unit-to-demand curves, DFU tables,
-- velocity limits, min slopes, vent length/diameter tables, rainfall
-- intensity tables, etc.). EMPTY BY DESIGN until the engineer supplies
-- values from the licensed code text or confirmed project criteria.
CREATE TABLE design_tables (
    table_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    code_id         TEXT NOT NULL REFERENCES codes(code_id),
    domain          TEXT NOT NULL,
    table_name      TEXT NOT NULL,         -- e.g. 'Water Supply Fixture Units to Demand'
    description     TEXT,
    reference        TEXT,                  -- code table/section number
    status          TEXT NOT NULL DEFAULT 'CODE_DATA_REQUIRED'
                        CHECK (status IN ('CODE_DATA_REQUIRED','PARTIAL','POPULATED')),
    UNIQUE(code_id, domain, table_name)
);

-- Long/tidy format: one row per (source data-row, column). This is what
-- lets a single table shape hold fixture-record tables (many mixed
-- attribute columns), 2-D lookup tables (row x column matrices), and
-- flat parameter lists (IPC/UPC/BS_EN/Egypt velocity-limit sheets, whose
-- column sets all genuinely differ) without forcing a rigid schema per
-- domain. row_key identifies the source spreadsheet row (stable within
-- a table_id); col_key is the column header text as supplied.
CREATE TABLE design_table_values (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id              INTEGER NOT NULL REFERENCES design_tables(table_id),
    row_key               TEXT NOT NULL,
    col_key               TEXT NOT NULL,
    value_num             REAL,            -- populated when the cell parses as a clean number
    value_text            TEXT,            -- populated otherwise (ranges like "1.2-2.4", "No limit", labels)
    unit                  TEXT,
    source_classification TEXT NOT NULL DEFAULT 'CODE'
                        CHECK (source_classification IN ('CODE','PROJECT','USER_INPUT','MANUFACTURER','ASSUMED')),
    confidence            TEXT NOT NULL DEFAULT 'CONFIRMED'
                        CHECK (confidence IN ('CONFIRMED','FLAGGED')),
    notes                 TEXT
);

-- ---------------------------------------------------------------------
-- 2. PROJECT / DESIGN BASIS
-- ---------------------------------------------------------------------

CREATE TABLE projects (
    project_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name        TEXT NOT NULL,
    project_number      TEXT,
    project_location    TEXT,
    building_type       TEXT NOT NULL,
    gross_area_m2       REAL,
    num_floors          INTEGER,
    floor_to_floor_m    REAL,
    occupancy           INTEGER,
    design_stage        TEXT,
    code_id             TEXT REFERENCES codes(code_id),
    code_edition        TEXT,
    water_material_id   INTEGER,
    drainage_material_id INTEGER,
    storm_material_id   INTEGER,
    hotwater_material_id INTEGER,
    design_engineer     TEXT,
    client              TEXT,
    consultant          TEXT,
    revision            TEXT,
    project_date        TEXT
);

CREATE TABLE design_basis_items (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id            INTEGER NOT NULL REFERENCES projects(project_id),
    item_key               TEXT NOT NULL,    -- e.g. 'rainfall_intensity', 'hot_water_temp_c'
    item_value              TEXT NOT NULL,
    unit                   TEXT,
    source_classification  TEXT NOT NULL DEFAULT 'ASSUMED'
                        CHECK (source_classification IN ('CODE','PROJECT','USER_INPUT','MANUFACTURER','ASSUMED')),
    status                 TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING','APPROVED','REJECTED'))
);

-- ---------------------------------------------------------------------
-- 3. FIXTURES / MATERIALS / PIPE SIZES
-- ---------------------------------------------------------------------

CREATE TABLE fixtures (
    fixture_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code_id                TEXT REFERENCES codes(code_id),
    fixture_name            TEXT NOT NULL,     -- 'WC', 'Lavatory', 'Urinal', ...
    fixture_type             TEXT,
    cold_fu                 REAL,
    hot_fu                   REAL,
    dfu                      REAL,
    flow_rate_lps            REAL,
    temp_requirement_c        REAL,
    reference                TEXT,
    building_type_applicability TEXT,
    source_classification     TEXT NOT NULL DEFAULT 'CODE_DATA_REQUIRED'
);

CREATE TABLE materials (
    material_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    material_name            TEXT NOT NULL,     -- 'PPR-PN16', 'uPVC Class 4', 'HDPE', ...
    category                 TEXT NOT NULL CHECK (category IN ('water','hot_water','drainage','storm')),
    pipe_standard             TEXT,
    roughness_value           REAL,             -- Hazen-Williams C or Darcy-Weisbach absolute roughness (mm)
    roughness_model            TEXT CHECK (roughness_model IN ('hazen_williams_C','darcy_weisbach_mm')),
    pressure_rating_bar        REAL,
    temp_rating_c              REAL,
    joining_method              TEXT,
    manufacturer                TEXT,
    code_applicability           TEXT,
    source_classification        TEXT NOT NULL DEFAULT 'ASSUMED'
);

CREATE TABLE pipe_sizes (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id            INTEGER NOT NULL REFERENCES materials(material_id),
    nominal_diameter_mm      REAL NOT NULL,
    internal_diameter_mm      REAL NOT NULL,
    external_diameter_mm      REAL,
    schedule_class              TEXT,
    source                       TEXT
);

-- ---------------------------------------------------------------------
-- 4. NETWORK ELEMENTS (pipes, tanks, pumps) — project-specific
-- ---------------------------------------------------------------------

CREATE TABLE pipes (
    pipe_id               TEXT PRIMARY KEY,       -- e.g. 'CW-P-001'
    project_id              INTEGER NOT NULL REFERENCES projects(project_id),
    system                   TEXT NOT NULL CHECK (system IN ('cold_water','hot_water','drainage','vent','storm')),
    from_node                 TEXT,
    to_node                    TEXT,
    length_m                    REAL,
    material_id                 INTEGER REFERENCES materials(material_id),
    nominal_diameter_mm          REAL,
    flow_lps                     REAL,
    elevation_diff_m               REAL,
    level                          TEXT,
    revit_element_id                TEXT,          -- link back to the Revit model
    slope_percent                    REAL           -- drainage/storm only
);

CREATE TABLE tanks (
    tank_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id                INTEGER NOT NULL REFERENCES projects(project_id),
    tank_type                   TEXT NOT NULL,      -- 'domestic_cold', 'break_tank', 'hot_water_storage', 'other'
    required_volume_m3            REAL,
    selected_volume_m3              REAL,
    freeboard_m                      REAL,
    storage_duration_hr                REAL,
    dimensions                          TEXT,
    status                                TEXT DEFAULT 'CALCULATED',
    revit_element_id                       TEXT           -- link back to the Revit model (Phase 7)
);

CREATE TABLE pumps (
    pump_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id                 INTEGER NOT NULL REFERENCES projects(project_id),
    duty_flow_lps                 REAL,
    duty_head_m                     REAL,
    efficiency                       REAL,
    required_power_kw                  REAL,
    selected_pump                        TEXT,
    motor_power_kw                        REAL,
    status                                  TEXT DEFAULT 'CALCULATED',
    revit_element_id                          TEXT        -- link back to the Revit model (Phase 7)
);

-- ---------------------------------------------------------------------
-- 5. CALCULATIONS / COMPLIANCE / QA-QC / ASSUMPTIONS
-- ---------------------------------------------------------------------

CREATE TABLE calculations (
    calc_id                TEXT PRIMARY KEY,        -- e.g. 'CW-001'
    project_id                INTEGER NOT NULL REFERENCES projects(project_id),
    calc_type                   TEXT NOT NULL,        -- 'cold_water_pipe_sizing', 'tdh', ...
    target_type                  TEXT,                 -- 'pipe','tank','pump', ...
    target_id                     TEXT,
    formula                        TEXT NOT NULL,
    inputs_json                     TEXT NOT NULL,
    intermediate_json                 TEXT,
    result_value                       REAL,
    result_unit                          TEXT,
    required_value                        REAL,
    selected_value                          REAL,
    status                                    TEXT NOT NULL
                        CHECK (status IN ('PASS','FAIL','WARNING','ASSUMED','MISSING_DATA','CALCULATED_NOT_APPROVED')),
    code_rule_id                              TEXT REFERENCES code_rules(rule_id),
    reference                                  TEXT,
    created_at                                   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE compliance_checks (
    check_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id                 INTEGER NOT NULL REFERENCES projects(project_id),
    rule_id                      TEXT NOT NULL REFERENCES code_rules(rule_id),
    target_type                   TEXT,
    target_id                      TEXT,
    actual_value                    TEXT,
    required_value                   TEXT,
    status                             TEXT NOT NULL CHECK (status IN ('PASS','FAIL','WARNING','NOT_EVALUATED')),
    reason                              TEXT,
    created_at                            TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE assumptions (
    assumption_id            TEXT PRIMARY KEY,        -- e.g. 'A-001'
    project_id                  INTEGER NOT NULL REFERENCES projects(project_id),
    description                   TEXT NOT NULL,
    value                           TEXT,
    status                            TEXT NOT NULL DEFAULT 'PENDING_ENGINEER_APPROVAL'
                        CHECK (status IN ('PENDING_ENGINEER_APPROVAL','APPROVED','EDITED','REJECTED')),
    approved_by                        TEXT,
    approved_date                        TEXT
);

CREATE TABLE qaqc_results (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id                INTEGER NOT NULL REFERENCES projects(project_id),
    check_name                  TEXT NOT NULL,
    category                      TEXT,
    status                          TEXT NOT NULL CHECK (status IN ('PASS','WARNING','FAIL','ASSUMED','MISSING_DATA')),
    details                          TEXT,
    created_at                          TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- 6. REVIT / BIM LINK
-- ---------------------------------------------------------------------

CREATE TABLE revit_elements (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id                 INTEGER NOT NULL REFERENCES projects(project_id),
    element_id                    TEXT NOT NULL,
    category                        TEXT,
    system                            TEXT,
    family                              TEXT,
    type_name                            TEXT,
    level                                  TEXT,
    parameters_json                          TEXT,
    last_synced                                TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_rules_code_domain ON code_rules(code_id, domain);
CREATE INDEX idx_calc_project ON calculations(project_id);
CREATE INDEX idx_compliance_project ON compliance_checks(project_id);
CREATE INDEX idx_pipes_project ON pipes(project_id, system);
