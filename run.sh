#!/usr/bin/env bash
# Golden-path runner (DESIGN_SPEC §12, Phase-0 FROZEN).
# Canonical order: score a small beef sample into scores.duckdb, THEN launch the
# read_only dashboard. One command for the Phase-2 integrator in the riskiest window.
# Pipeline modules are created during the build (Phase 1/2); this script is committed
# early so the run order is never improvised on stage.
set -euo pipefail
cd "$(dirname "$0")"
PY=".venv/bin/python"

"$PY" cli/run_pipeline.py --limit 20 --methods both
exec .venv/bin/streamlit run app/dashboard.py
