#!/usr/bin/env bash
# Demo runner (DESIGN_SPEC §10/§12, Phase-0 FROZEN).
# Scores a tiny sample, then opens the dashboard; pick "Demo" mode in the sidebar to
# auto-select the curated beef striploin capture and walk the 6-beat DEMO_SCRIPT with
# zero table interaction. Curated capture: 260612_office_backup/206/beef/striploin/251016.
set -euo pipefail
cd "$(dirname "$0")"
PY=".venv/bin/python"

"$PY" cli/run_pipeline.py --limit 4 --methods both
exec .venv/bin/streamlit run app/dashboard.py
