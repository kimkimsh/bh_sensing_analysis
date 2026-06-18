# bh_sensing_analysis

Local Streamlit analysis tool for charbroiler meat-doneness. It compares two ROI
sources over the same spectral captures — an AI segmentation ROI (meatSegNet ONNX)
versus a rule ROI — while the doneness cascade stays identical between them, so the
dashboard shows ROI **agreement, not accuracy**.

## Run order

The canonical golden path is a single command:

```bash
bash run.sh
```

This runs two steps in order:

1. **Pipeline** — `python cli/run_pipeline.py --limit 20 --methods both`
   Scans the data root into captures, runs both scorers (AI ROI + rule ROI) sharing
   one ONNX session, renders the cached overlay PNGs into `artifacts/overlays/`, and
   writes `captures` + `scores` into `scores.duckdb` (idempotent upsert).
2. **Dashboard** — `streamlit run app/dashboard.py`
   Opens `scores.duckdb` read-only. With no database present it shows a first-run
   guard instead of crashing.

`bash demo.sh` is the same flow with `--limit 4`; pick **Demo** mode in the sidebar
to walk the curated beef striploin capture.

### Pipeline flags

```
python cli/run_pipeline.py [--limit N] [--methods ai|conditional|both]
                           [--data-root DIR] [--db PATH] [--model PATH]
```

- `--limit` — score only the first N captures (smoke runs); default scores all.
- `--methods` — which scorer(s) to run; default `both`.
- `--data-root` — directory to scan; default `data`.
- `--db` — DuckDB output path; default `scores.duckdb`.

### Smoke test

```bash
PYTHONPATH=. .venv/bin/python cli/run_pipeline.py --limit 4 --methods both --data-root tests/fixtures
```

Always run Python through the uv-managed venv with `PYTHONPATH=.`:

```bash
cd /path/to/bh_sensing_analysis && PYTHONPATH=. .venv/bin/python ...
```
