"""BH Sensing dashboard (Stream D) — Streamlit read_only reader over scores.duckdb.

Single-hero IA (DESIGN_SPEC §6/§7/§8): the Compare tab leads with the ROI-diff
overlap-map hero + agreement scorecard; per-panel detail is folded into an
expander. Trends and Explore are context/secondary.

Honesty (DESIGN_SPEC §11): copy says "agreement", never "accuracy/better"; never
"AI doneness"; all deltas are sign-only and neutral-colored; per-class % always
shows the absolute pixel count beside it.

This module is a reader only. It opens DuckDB read_only and never writes. The
aggregation queries come from bh_score.persist.queries.AggregationQueries (Stream
C), imported lazily so a missing query module degrades to a guard screen instead of
crashing at import time.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import streamlit as st

# Make the repo-root packages importable when launched as `streamlit run
# app/dashboard.py`: the script's own dir (app/), not the repo root, is on sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bh_score.scoring import agreement as agreementMod
from bh_score.viz import charts, overlay, palette

DEFAULT_DB_PATH = "scores.duckdb"

# Curated demo capture (DEMO_SCRIPT, Phase-0 gate): device 206 beef/striploin
# 250903 posIdx 1 — non-trivial, story-consistent ROI disagreement.
DEMO_DEVICE_ID = 206
DEMO_MENU = "beef/striploin"
DEMO_DATE = "2025-09-03"
DEMO_CAPTURE_INDEX = 1

DEMO_SCRIPT_BEATS = (
    "Hook — a pitmaster judges char on the charbroiler by eye. Quantify it across 11 wavelengths.",
    "Frame — the mono led10 (740nm) grayscale frame is what the sensor sees.",
    "Hero reveal — where AI segmentation (cyan) and the rule ROI (vermilion) diverge.",
    "The one number — IoU and signed area delta. Same rules, cleaner AI ROI, no tuning.",
    "Why it matters — 11 wavelengths: AI segments, rules decide.",
    "Close — no ground-truth labels, so this shows agreement, not accuracy.",
)

DELTA_NEUTRAL_COLOR = "off"

# Mono background dimension fallback when no cached image is available.
_FALLBACK_H = 480
_FALLBACK_W = 640


def queryEngine(dbPath):
    """Construct the read_only AggregationQueries, or return None if the DB file is
    absent or the query module is not yet available. Cached as a resource so the
    DuckDB connection is created once per session (NF-2)."""
    if not os.path.exists(dbPath):
        return None
    try:
        from bh_score.persist.queries import AggregationQueries
    except Exception:
        return None
    try:
        return AggregationQueries(dbPath)
    except Exception:
        return None


queryEngine = st.cache_resource(queryEngine)


def _callOptional(engine, names, *args):
    """Call the first existing method on engine from names with args; return None on
    absence or failure. Tolerates small naming differences in the Stream C API
    without crashing the reader."""
    if engine is None:
        return None
    for tName in names:
        tFn = getattr(engine, tName, None)
        if tFn is None:
            continue
        try:
            return tFn(*args)
        except Exception:
            return None
    return None


def hasScores(engine):
    """True when the scores table exists and holds at least one row."""
    if engine is None:
        return False
    tResult = _callOptional(engine, ("hasScores", "has_scores", "scoreCount", "score_count"))
    if isinstance(tResult, bool):
        return tResult
    if isinstance(tResult, (int, float)):
        return tResult > 0
    return False


@st.cache_data
def _loadMaskBundleCached(_engine, captureId):
    """Return a dict with mono_bg uint8[H,W], onnx_mask/rule_mask bool[H,W] and
    onnx_class_map/rule_class_map uint8[H,W] for a capture, or None if unavailable.

    Cached by capture_id only (NF-2): the _engine parameter is underscore-prefixed
    so Streamlit excludes the unhashable DuckDB connection from the cache key. The
    Stream C/A render-contract loader is invoked through a tolerant adapter; on
    absence the caller falls back to a guard."""
    return _callOptional(
        _engine, ("maskBundle", "mask_bundle", "renderInputs", "render_inputs"), captureId
    )


def _signed(value):
    """Sign-only string for a delta (DESIGN_SPEC §11 — never green=good)."""
    tVal = int(value)
    if tVal > 0:
        return "+" + str(tVal)
    return str(tVal)


def _iouCaption(iou):
    """Plain-language IoU caption; threshold-driven (STRONG_AGREEMENT_IOU)."""
    if not isinstance(iou, (int, float)):
        return agreementMod.NO_OVERLAP_SENTINEL + " — IoU undefined"
    tThreshold = format(agreementMod.STRONG_AGREEMENT_IOU, ".2f")
    if iou >= agreementMod.STRONG_AGREEMENT_IOU:
        tTag = " — both pick nearly the same region; >" + tThreshold + " = strong agreement"
    elif iou >= agreementMod.MODERATE_AGREEMENT_IOU:
        tTag = " — substantial overlap; the ROIs differ mainly at the boundary"
    else:
        tTag = " — the two ROI masks diverge here"
    return "IoU " + format(iou, ".2f") + tTag


def _legendKey():
    """Render the doneness legend chip key (chip + name + pattern) in the sidebar."""
    st.caption("Doneness legend (charts)")
    for tLevel in palette.DONENESS_ORDER:
        tChip = palette.DONENESS_CHIP[tLevel]
        tHex = palette.DONENESS_RAMP_HEX[tLevel]
        tPattern = palette.DONENESS_PATTERN[tLevel] or "solid"
        st.markdown(
            "<span style='display:inline-block;width:0.8rem;height:0.8rem;"
            "background:" + tHex + ";border:1px solid #2A313D;margin-right:0.4rem;"
            "vertical-align:middle'></span>"
            "<span style='font-family:monospace'>" + tChip + "</span> "
            + tLevel + " (" + tPattern + ")",
            unsafe_allow_html=True,
        )
    st.caption("ROI-diff hero: Both grey / AI-only cyan / Rule-only vermilion")


def _renderSidebar(engine):
    """Build the persistent nav rail and return the selected mode + filters dict."""
    with st.sidebar:
        try:
            st.logo(":material/sensors:")
        except Exception:
            pass
        st.title("BH Sensing")
        st.caption("AI ROI vs Rule ROI — agreement, not accuracy")

        tMode = st.radio("Mode", ("Demo", "Explore"), index=0, horizontal=True)

        tMenus = _callOptional(engine, ("menuInventory", "menu_inventory", "menus"))
        tMenuOptions = list(tMenus) if tMenus else [DEMO_MENU]
        tSelectedMenus = st.multiselect("Menu", tMenuOptions, default=tMenuOptions[:1])

        tDateRange = _callOptional(engine, ("dateRange", "date_range"))
        if isinstance(tDateRange, (tuple, list)) and len(tDateRange) == 2:
            tStart, tEnd = tDateRange
            tSelectedDates = st.date_input("Date range", (tStart, tEnd))
        else:
            tSelectedDates = st.date_input("Date range", ())

        tCaptureId = None
        if tMode == "Explore":
            tCaptures = _callOptional(
                engine, ("captureTable", "capture_table", "captures"), tSelectedMenus
            )
            tCaptureId = st.session_state.get("selected_capture_id")
            st.caption("Pick a capture in the Explore tab table.")

        st.divider()
        _legendKey()

    tFilters = {
        "menus": tSelectedMenus,
        "dates": tSelectedDates,
        "capture_id": tCaptureId,
    }
    return tMode, tFilters


def _emptyMono():
    return np.zeros((_FALLBACK_H, _FALLBACK_W), dtype=np.uint8)


def _renderHero(engine, captureId, demoMode):
    """PRIMARY hero (full width) + SECONDARY scorecard + TERTIARY per-panel detail.

    Builds the ROI-diff overlap-map from the capture's masks; computes agreement
    metrics via the frozen agreementMod; never produces NaN (zero-union sentinel).
    """
    tBundle = _loadMaskBundleCached(engine, captureId) if captureId is not None else None
    # _loadMaskBundleCached keys on captureId; engine is the underscore-excluded arg.
    if tBundle is None:
        st.warning(
            "No cached ROI masks for this capture — run the pipeline to populate "
            "overlays (`python cli/run_pipeline.py --limit 20`)."
        )
        return

    tMono = tBundle.get("mono_bg")
    tOnnx = tBundle.get("onnx_mask")
    tRule = tBundle.get("rule_mask")
    if tMono is None:
        tMono = _emptyMono()
    if tOnnx is None:
        tOnnx = np.zeros(tMono.shape[:2], dtype=bool)
    if tRule is None:
        tRule = np.zeros(tMono.shape[:2], dtype=bool)

    tMetrics = agreementMod.agreementMetrics(tOnnx, tRule)
    if tMetrics["onnx_px"] == 0 and tMetrics["rule_px"] == 0:
        st.warning("No ROI found by either method — IoU undefined.")
    elif tMetrics["rule_px"] == 0:
        st.warning("Rule ROI is empty for this capture — only the AI ROI is shown (IoU undefined).")
    elif tMetrics["onnx_px"] == 0:
        st.warning("AI ROI is empty for this capture — only the Rule ROI is shown.")

    # PRIMARY — the hero, full content width.
    st.subheader("ROI-diff overlap-map")
    tHero = overlay.renderRoiDiffHero(tMono, tOnnx, tRule)
    st.image(tHero, width="stretch", caption="Same doneness rules. Different ROI mask.")

    # SECONDARY — agreement scorecard.
    tIou = tMetrics["iou"]
    tDice = tMetrics["dice"]
    with st.container(horizontal=True, border=True):
        tIouText = tIou if isinstance(tIou, str) else format(tIou, ".2f")
        tDiceText = tDice if isinstance(tDice, str) else format(tDice, ".2f")
        st.metric("IoU", tIouText)
        st.metric("Dice", tDiceText)
        st.metric("Area delta (px)", _signed(tMetrics["area_delta_px"]), delta_color=DELTA_NEUTRAL_COLOR)
    st.caption(_iouCaption(tIou))

    # NOT_DONE-dominant banner (honesty guard).
    _maybeNotDoneBanner(engine, captureId)

    # TERTIARY — per-panel detail, folded.
    with st.expander("Per-panel detail", expanded=False):
        _renderPerPanel(engine, captureId, tBundle, tMono)


def _maybeNotDoneBanner(engine, captureId):
    tPaired = _callOptional(engine, ("pairedScores", "paired_scores", "paired"), captureId)
    if not tPaired:
        return
    tRows = tPaired if isinstance(tPaired, (list, tuple)) else [tPaired]
    for tRow in tRows:
        tNotDone = _rowGet(tRow, "pct_not_done")
        if isinstance(tNotDone, (int, float)) and tNotDone > agreementMod.NOT_DONE_DOMINANT_PCT:
            st.warning(
                "NOT_DONE-dominant: most ROI pixels failed the live doneness gate "
                "(" + format(tNotDone, ".0f") + "%). Doneness percentages read off a small base."
            )
            return


def _rowGet(row, key):
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _renderPerPanel(engine, captureId, bundle, mono):
    """original | AI | Rule 3-split + shared 4-way stacked bar + per-class % with
    absolute pixel counts."""
    tOnnxClass = bundle.get("onnx_class_map")
    tRuleClass = bundle.get("rule_class_map")
    tOnnxMask = bundle.get("onnx_mask")
    tRuleMask = bundle.get("rule_mask")

    tCols = st.columns(3)
    with tCols[0]:
        st.caption("Original (mono led10)")
        st.image(overlay.monoToRgb(mono), width="stretch")
    with tCols[1]:
        st.caption("AI ROI overlay")
        if tOnnxClass is not None and tOnnxMask is not None:
            st.image(overlay.renderMaskOverlay(mono, tOnnxMask, tOnnxClass), width="stretch")
        else:
            st.image(overlay.monoToRgb(mono), width="stretch")
    with tCols[2]:
        st.caption("Rule ROI overlay")
        if tRuleClass is not None and tRuleMask is not None:
            st.image(overlay.renderMaskOverlay(mono, tRuleMask, tRuleClass), width="stretch")
        else:
            st.image(overlay.monoToRgb(mono), width="stretch")

    tPaired = _callOptional(engine, ("pairedScores", "paired_scores", "paired"), captureId)
    tPanelCounts = _panelCountsFromPaired(tPaired)
    if tPanelCounts:
        st.plotly_chart(charts.fourWayStackedBar(tPanelCounts), width="stretch")
        _renderPerClassTable(tPanelCounts)


def _panelCountsFromPaired(paired):
    """Build {method_label: {level: pixel_count}} from paired score rows."""
    if not paired:
        return {}
    tRows = paired if isinstance(paired, (list, tuple)) else [paired]
    tOut = {}
    tLabelByMethod = {"ai": "AI ROI", "conditional": "Rule ROI"}
    for tRow in tRows:
        tMethod = _rowGet(tRow, "method") or "method"
        tLabel = tLabelByMethod.get(tMethod, tMethod)
        tOut[tLabel] = {
            "NOT_DONE": _rowGet(tRow, "pixels_not_done") or 0,
            "PROPER": _rowGet(tRow, "pixels_proper") or 0,
            "SLIGHTLY_BURNT": _rowGet(tRow, "pixels_slightly_burnt") or 0,
            "BURNT": _rowGet(tRow, "pixels_burnt") or 0,
        }
    return tOut


def _renderPerClassTable(panelCounts):
    """Per-class % WITH absolute pixel counts (honesty guard: amplification check)."""
    st.caption("Per-class % (absolute pixel count)")
    for tLabel, tCounts in panelCounts.items():
        tTotal = max(sum(tCounts.values()), 1)
        tParts = []
        for tLevel in palette.DONENESS_ORDER:
            tCount = tCounts.get(tLevel, 0)
            tPct = 100.0 * tCount / tTotal
            tParts.append(
                palette.DONENESS_CHIP[tLevel] + " " + format(tPct, ".0f") + "% (" + str(int(tCount)) + " px)"
            )
        st.markdown("**" + tLabel + "** — " + "  ·  ".join(tParts))


def _renderCompareTab(engine, mode, filters):
    if mode == "Demo":
        st.info("Demo mode — curated capture: device 206 beef/striploin 250903 pos 1.")
        tCaptureId = _resolveDemoCapture(engine)
        for tIndex, tBeat in enumerate(DEMO_SCRIPT_BEATS, start=1):
            st.caption(str(tIndex) + ". " + tBeat)
    else:
        tCaptureId = filters.get("capture_id") or st.session_state.get("selected_capture_id")
        if tCaptureId is None:
            st.info("Pick a capture in the Explore tab to compare AI vs Rule ROI.")
            return
    _renderHero(engine, tCaptureId, mode == "Demo")


def _resolveDemoCapture(engine):
    tId = _callOptional(
        engine,
        ("captureIdFor", "capture_id_for", "demoCapture", "demo_capture"),
        DEMO_DEVICE_ID,
        DEMO_MENU,
        DEMO_DATE,
        DEMO_CAPTURE_INDEX,
    )
    return tId


_TREND_CLASS_OPTIONS = ("burnt", "slightly_burnt", "proper", "not_done")


def _trendClassLabel(classKey):
    return classKey.replace("_", " ").upper()


def _renderTrendsTab(engine, filters):
    st.subheader("By-date trends")
    tClass = st.radio(
        "Doneness class",
        _TREND_CLASS_OPTIONS,
        index=0,
        horizontal=True,
        format_func=_trendClassLabel,
    )
    tDf = _callOptional(
        engine, ("byDate", "by_date"), filters.get("menus"), filters.get("dates"), tClass
    )
    st.plotly_chart(charts.byDateLines(tDf), width="stretch")
    st.caption("Class = color, method = line style (AI solid / Rule dashed). One class at a time keeps it readable.")


def _renderExploreTab(engine, filters):
    st.subheader("AI vs Rule (agreement)")
    tScatterDf = _callOptional(engine, ("aiVsCond", "ai_vs_cond", "paired"), filters.get("menus"))
    st.plotly_chart(charts.aiVsRuleScatter(tScatterDf), width="stretch")

    st.subheader("By menu")
    tMenuDf = _callOptional(engine, ("byMenu", "by_menu"), filters.get("menus"))
    st.plotly_chart(charts.byMenuBars(tMenuDf), width="stretch")

    st.subheader("Captures")
    tTable = _callOptional(engine, ("captureTable", "capture_table", "captures"), filters.get("menus"))
    if tTable is not None:
        tEvent = st.dataframe(
            tTable,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            key="capture_table",
        )
        _captureFromSelection(tTable, tEvent)
    else:
        st.caption("No capture table available yet.")


def _captureFromSelection(table, event):
    try:
        tRows = event.selection.rows
    except Exception:
        return
    if not tRows:
        return
    tIndex = tRows[0]
    try:
        tCaptureId = int(table.iloc[tIndex]["capture_id"])
    except Exception:
        return
    st.session_state["selected_capture_id"] = tCaptureId


def main():
    st.set_page_config(
        layout="wide",
        page_title="BH Sensing",
        page_icon=":material/sensors:",
        initial_sidebar_state="expanded",
    )

    tDbPath = os.environ.get("BH_SCORES_DB", DEFAULT_DB_PATH)
    tEngine = queryEngine(tDbPath)

    if not hasScores(tEngine):
        st.title("BH Sensing")
        st.info(
            "No scores yet — run `bash run.sh` (or `python cli/run_pipeline.py "
            "--limit 20`), or pick Demo mode once the DB is populated."
        )
        return

    tMode, tFilters = _renderSidebar(tEngine)

    tCompare, tTrends, tExplore = st.tabs(("Compare", "Trends", "Explore"))
    with tCompare:
        _renderCompareTab(tEngine, tMode, tFilters)
    with tTrends:
        _renderTrendsTab(tEngine, tFilters)
    with tExplore:
        _renderExploreTab(tEngine, tFilters)


if __name__ == "__main__":
    main()
