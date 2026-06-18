# 2026-06-18 — Implement ONNX-ROI vs Rule-ROI comparison dashboard

## Context
Pre-build prep was complete (frozen design docs + scaffold). This session implemented
the full tool: scan spectral captures → score doneness via two ROI sources (AI
meatSegNet ROI vs rule-morphology ROI) sharing one cascade → DuckDB → Streamlit
dashboard whose hero is the ROI-diff overlap-map ("agreement, not accuracy"). Built
Phase-0 contracts by hand, then fanned out 4 parallel streams via a dynamic Workflow,
then integrated + reviewed.

## Files changed
- **Phase-0 (hand-written, the shared synchronization point):** `bh_score/scoring/{result,base,cascade,kernel,grades,agreement}.py`, `bh_score/ingest/types.py`; `tests/test_{kernel_golden,cascade_golden,symmetry,agreement_guard}.py`; extended `bh_score/persist/schema.sql` (raw class-pixel-count columns; captures `mask_path`/`iou`/`dice`/`area_delta_px`).
- **Phase-1 streams (Workflow):** `ingest/scanner.py`, `ingest/cube.py`, `scoring/conditional.py`, `segment/meatsegnet.py`, `scoring/ai.py`, `persist/repository.py`, `persist/queries.py`, `viz/overlay.py`, `viz/charts.py`, `app/dashboard.py` + per-stream tests.
- **Phase-2 + integration:** `cli/run_pipeline.py`, `README.md`; reconciled the C↔D seam.
- **Docs:** curated capture `251016`→`250903` in DEMO_SCRIPT/DESIGN_SPEC/FEATURES_SPEC/demo.sh; added `250903` fixture.

## Why (key decisions)
- **Ported the cascade/meatSegNet from the live C++ headers directly** (cross-reference rule), not spec prose. Confirmed meatSegNet layout `[box4,obj1,cls4,mask32]` + class encoding `0=BEEF` by real inference.
- **Curated capture 251016 was dead** (zero AI detections — flat spectral signal). Replaced with `250903` (IoU 0.893). This is the exact failure the DEMO_SCRIPT visual gate exists to catch.
- **NOT_DONE bucket + raw pixel counts persisted** (the live engine zeroes not_done — a quirk) for the honest 4-way bar + absolute-count guard (DESIGN_SPEC §11).
- **Persisted boolean masks as per-capture npz** so the read-only dashboard renders the hero live; agreement recomputed from masks (single source of truth).

## Verification
- All 8 offline tests PASS (`PYTHONPATH=. .venv/bin/python tests/test_*.py`), incl. live ONNX inference.
- Pipeline smoke (`--limit 4 --data-root tests/fixtures`): 6 rows; 250903 AI 32991px / Rule 30576px (matches hand-validation), 251016 empty handled, no NaN.
- Full scan of `data/`: 2978 captures, all 10 menus incl. underscore cuts (t_bone, combo_belly_loin_cut, …).
- Dashboard boots HTTP 200, renders REAL data; hero screenshot visually confirms grey/cyan/orange ROI-diff narrative.
- Code review (10-angle finder fan-out) → fixed: **scanner regex dropped underscore-cut menus** (now path-derived meat/cut), `_parseDate` crash guard, scatter NaN from single-method captures, magic `+1`→`AI_LABEL_OFFSET`, caption `0.90`→constant, `aiVsCond` qualified WHERE, honest one-sided empty-ROI warnings.

## Follow-ups
- Accepted-as-faithful (not bugs): meatSegNet zero-fills a missing input band (matches live C++ `OnnxROIRecognizer.h:111-114`, unlike the cascade gate-band rule); cascade thresholds inline (verbatim transcription of the live header for verifiability).
- Minor/deferred: ai.py↔conditional.py share near-identical connected-component filtering (kept separate — different return needs); DuckDB write-lock vs a live read-only dashboard (mitigated by the documented sequential run order); P1/P2 dashboard items (opacity slider, pixel inspector, export) per the cut-line.
- Work is uncommitted on `main` (no commit requested).
