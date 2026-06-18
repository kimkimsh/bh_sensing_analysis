-- DuckDB schema for bh_sensing_analysis (PLAN §5, Phase-0 FROZEN).
-- One writer (the pipeline process); the dashboard opens the DB read_only.

-- One physical capture = one (device, meat, cut, date, posIdx) group.
CREATE TABLE IF NOT EXISTS captures (
  capture_id    BIGINT PRIMARY KEY,   -- deterministic hash of the group key
  device_id     INTEGER,
  meat          VARCHAR,
  cut           VARCHAR,
  menu          VARCHAR,              -- meat || '/' || cut
  capture_date  DATE,                 -- 2000 + YY
  capture_index INTEGER,
  band_count    INTEGER,              -- per-capture dynamic count (8-16); never hardcoded
  frame_dir     VARCHAR,
  mask_path     VARCHAR,              -- npz bundle (mono_bg, onnx/rule mask + class_map) for the hero
  iou           DOUBLE,               -- ROI agreement (NULL when no overlapping ROI)
  dice          DOUBLE,
  area_delta_px INTEGER               -- signed ONNX-ROI px minus Rule-ROI px
);

-- One row per (capture, method) — the main table the dashboard aggregates.
-- menu/capture_date are denormalized here to accelerate GROUP BY.
CREATE TABLE IF NOT EXISTS scores (
  capture_id          BIGINT,
  method              VARCHAR,        -- 'ai' | 'conditional'
  menu                VARCHAR,
  capture_date        DATE,
  pixels_roi          INTEGER,
  pixels_not_done     INTEGER,        -- raw class counts feed the honest 4-way bar
  pixels_proper       INTEGER,        -- (DESIGN_SPEC §11: show absolute px next to %)
  pixels_slightly_burnt INTEGER,
  pixels_burnt        INTEGER,
  pct_proper          DOUBLE,
  pct_slightly_burnt  DOUBLE,
  pct_burnt           DOUBLE,
  pct_burnt_raw       DOUBLE,         -- pre-offset burnt %
  pct_not_done        DOUBLE,         -- ROI pixels that failed the live gate (often the largest bucket)
  cooking_score       DOUBLE,
  maillard_score      DOUBLE,         -- single-method view only; never a cross-method comparison axis
  grade               INTEGER,        -- grade 0 = COMPLETE
  grade_label         VARCHAR,
  instance_count      INTEGER,
  overlay_path        VARCHAR,        -- cached overlay PNG
  mono_path           VARCHAR,        -- mono background (ch3 / led10) PNG
  scored_at           TIMESTAMP DEFAULT now(),
  PRIMARY KEY (capture_id, method)
);

-- Optional AI per-instance drilldown (P2 — v1 cut candidate).
CREATE TABLE IF NOT EXISTS instances (
  capture_id         BIGINT,
  method             VARCHAR,
  instance_id        INTEGER,
  class_id           INTEGER,
  class_name         VARCHAR,
  pixel_count        INTEGER,
  bbox_x             INTEGER,
  bbox_y             INTEGER,
  bbox_w             INTEGER,
  bbox_h             INTEGER,
  pct_proper         DOUBLE,
  pct_slightly_burnt DOUBLE,
  pct_burnt          DOUBLE,
  maillard_score     DOUBLE
);
