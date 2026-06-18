"""Plotly figure builders (Stream D). Charts inherit the CVD-safe doneness ramp
from .streamlit/config.toml chartCategoricalColors, so no per-figure color args are
passed except where series ordering must be pinned to the canonical doneness order
(then color_discrete_sequence = palette.CHART_CATEGORICAL_COLORS).

Honesty guardrails (DESIGN_SPEC §11): the 4-way bar always keeps NOT_DONE in the
denominator (it only recedes to grey), redundant pattern_shape + letter chips
encode each level without relying on color, and maillard_score is never a
cross-method comparison axis.
"""
from __future__ import annotations

import math

import plotly.graph_objects as go

from bh_score.viz import palette


def _isFinite(value):
    """True for a real (non-NaN) number. A NULL DuckDB FILTER aggregate (a capture
    scored by only one method) arrives as NaN, which Plotly rejects for coordinates,
    sizes, and colorscale values."""
    return isinstance(value, (int, float)) and not math.isnan(float(value))


def _finiteIou(value):
    """A finite IoU float, or None when missing/NaN (empty-overlap captures store a
    NULL iou)."""
    return float(value) if _isFinite(value) else None

# Method line styles for the by-date trend (method = dash, class = color).
_METHOD_DASH = {"ai": "solid", "conditional": "dash"}
_AI_VS_RULE_REF_COLOR = "#9AA0AC"
_SCATTER_MARKER_MIN_PX = 6
_SCATTER_MARKER_MAX_PX = 22
_DEFAULT_TREND_CLASS = "BURNT"


def _chipLabel(level):
    """'<chip> <Level Title>' e.g. 'B BURNT' for legend/axis labels."""
    return palette.DONENESS_CHIP[level] + " " + level


def fourWayStackedBar(perPanelCounts):
    """4-way stacked bar (NOT_DONE / PROPER / SLIGHTLY_BURNT / BURNT) from RAW pixel
    counts so each panel's bar sums to 100%. perPanelCounts maps a panel label to a
    dict of {level: pixel_count} for the four DONENESS_ORDER levels.

    Series are added in canonical doneness order with pattern_shape + chip labels;
    color comes from CHART_CATEGORICAL_COLORS (parity with config inheritance).
    """
    tPanels = list(perPanelCounts.keys())
    tFig = go.Figure()
    for tIndex, tLevel in enumerate(palette.DONENESS_ORDER):
        tCounts = [float(perPanelCounts[tPanel].get(tLevel, 0)) for tPanel in tPanels]
        tTotals = [
            max(sum(perPanelCounts[tPanel].get(tL, 0) for tL in palette.DONENESS_ORDER), 1)
            for tPanel in tPanels
        ]
        tPercents = [100.0 * tCounts[tI] / tTotals[tI] for tI in range(len(tPanels))]
        tFig.add_trace(
            go.Bar(
                name=_chipLabel(tLevel),
                x=tPercents,
                y=tPanels,
                orientation="h",
                marker_color=palette.CHART_CATEGORICAL_COLORS[tIndex],
                marker_pattern_shape=palette.DONENESS_PATTERN[tLevel],
                customdata=tCounts,
                hovertemplate="%{x:.1f}%% (%{customdata:.0f} px)<extra>" + _chipLabel(tLevel) + "</extra>",
            )
        )
    tFig.update_layout(
        barmode="stack",
        xaxis_title="% of ROI pixels",
        legend_title="Doneness",
        margin=dict(l=8, r=8, t=8, b=8),
    )
    tFig.update_xaxes(range=[0, 100])
    return tFig


def byDateLines(df):
    """Date-trend line chart: class = color, method = line style (ai solid /
    conditional dashed). df is expected to carry columns
    capture_date, method, and one percent column per class; the default view shows
    a single class (burnt) to avoid a 6-series tangle.

    The caller pre-filters df to the chosen class column 'pct_value' with a 'class'
    label column; this builder only styles. Empty df -> empty figure (no crash).
    """
    tFig = go.Figure()
    if df is None or len(df) == 0:
        tFig.update_layout(margin=dict(l=8, r=8, t=8, b=8))
        return tFig
    tClasses = sorted(df["class"].unique()) if "class" in df.columns else [_DEFAULT_TREND_CLASS]
    tMethods = sorted(df["method"].unique()) if "method" in df.columns else ["ai", "conditional"]
    for tClassName in tClasses:
        tColor = palette.DONENESS_RAMP_HEX.get(tClassName)
        for tMethod in tMethods:
            tSub = df
            if "class" in df.columns:
                tSub = tSub[tSub["class"] == tClassName]
            if "method" in df.columns:
                tSub = tSub[tSub["method"] == tMethod]
            if len(tSub) == 0:
                continue
            tFig.add_trace(
                go.Scatter(
                    x=tSub["capture_date"],
                    y=tSub["pct_value"],
                    mode="lines+markers",
                    name=tClassName + " / " + tMethod,
                    line=dict(color=tColor, dash=_METHOD_DASH.get(tMethod, "solid")),
                )
            )
    tFig.update_layout(
        xaxis_title="Date",
        yaxis_title="% of ROI pixels",
        margin=dict(l=8, r=8, t=8, b=8),
    )
    return tFig


def byMenuBars(df):
    """Grouped bars of a mean score per menu, grouped by method. df carries columns
    menu, method, value. Color encodes method via CHART_CATEGORICAL_COLORS ordering.
    Empty df -> empty figure.
    """
    tFig = go.Figure()
    if df is None or len(df) == 0:
        tFig.update_layout(margin=dict(l=8, r=8, t=8, b=8))
        return tFig
    tMenus = list(dict.fromkeys(df["menu"].tolist()))
    tMethods = sorted(df["method"].unique()) if "method" in df.columns else ["ai", "conditional"]
    for tIndex, tMethod in enumerate(tMethods):
        tSub = df[df["method"] == tMethod] if "method" in df.columns else df
        tByMenu = {tRow["menu"]: tRow["value"] for _, tRow in tSub.iterrows()}
        tValues = [tByMenu.get(tMenu) for tMenu in tMenus]
        tFig.add_trace(
            go.Bar(
                name=tMethod,
                x=tMenus,
                y=tValues,
                marker_color=palette.CHART_CATEGORICAL_COLORS[tIndex % len(palette.CHART_CATEGORICAL_COLORS)],
            )
        )
    tFig.update_layout(
        barmode="group",
        xaxis_title="Menu",
        yaxis_title="Mean score",
        legend_title="Method",
        margin=dict(l=8, r=8, t=8, b=8),
    )
    return tFig


def aiVsRuleScatter(df):
    """AI vs Rule per-capture scatter: x = ONNX %, y = Rule %, with a y=x reference
    line; point color/size encode ROI-IoU so spread reads as segmentation
    disagreement. df carries columns onnx_pct, rule_pct, iou. A MAE(pts) caption is
    placed in the title. Empty df -> empty figure.
    """
    tFig = go.Figure()
    if df is None or len(df) == 0:
        tFig.update_layout(margin=dict(l=8, r=8, t=8, b=8))
        return tFig

    tOnnxRaw = df["onnx_pct"].tolist()
    tRuleRaw = df["rule_pct"].tolist()
    tIouRaw = df["iou"].tolist() if "iou" in df.columns else [None] * len(tOnnxRaw)
    # A capture scored by only one method (--methods ai|conditional, or a scorer
    # skipped) has a NaN percentage for the missing method — not a paired comparison
    # point, so drop it rather than poison the MAE and the marker coordinates.
    tValid = [tI for tI in range(len(tOnnxRaw)) if _isFinite(tOnnxRaw[tI]) and _isFinite(tRuleRaw[tI])]
    if not tValid:
        tFig.update_layout(margin=dict(l=8, r=8, t=8, b=8))
        return tFig
    tOnnx = [tOnnxRaw[tI] for tI in tValid]
    tRule = [tRuleRaw[tI] for tI in tValid]
    tIou = [_finiteIou(tIouRaw[tI]) for tI in tValid]
    tMae = sum(abs(tOnnx[tI] - tRule[tI]) for tI in range(len(tOnnx))) / len(tOnnx)

    tLo = min(min(tOnnx), min(tRule), 0.0)
    tHi = max(max(tOnnx), max(tRule), 100.0)
    tFig.add_trace(
        go.Scatter(
            x=[tLo, tHi],
            y=[tLo, tHi],
            mode="lines",
            name="y = x",
            line=dict(color=_AI_VS_RULE_REF_COLOR, dash="dot"),
            hoverinfo="skip",
        )
    )

    # Two marker traces: captures with a real ROI overlap (colored/sized by IoU) and
    # no-overlap captures (NULL IoU) shown neutrally — a numeric colorscale rejects
    # None, and a (0,0) point with no IoU should not borrow a color it does not have.
    tHasIou = [tI for tI in range(len(tIou)) if tIou[tI] is not None]
    tNoIou = [tI for tI in range(len(tIou)) if tIou[tI] is None]
    if tHasIou:
        tFig.add_trace(
            go.Scatter(
                x=[tOnnx[tI] for tI in tHasIou],
                y=[tRule[tI] for tI in tHasIou],
                mode="markers",
                name="captures",
                marker=dict(
                    size=[_iouSize(tIou[tI]) for tI in tHasIou],
                    color=[tIou[tI] for tI in tHasIou],
                    colorscale="Cividis",
                    showscale=True,
                    colorbar=dict(title="ROI IoU"),
                    cmin=0.0,
                    cmax=1.0,
                ),
                customdata=[tIou[tI] for tI in tHasIou],
                hovertemplate="AI %{x:.1f}% / Rule %{y:.1f}% / IoU %{customdata:.2f}<extra></extra>",
            )
        )
    if tNoIou:
        tFig.add_trace(
            go.Scatter(
                x=[tOnnx[tI] for tI in tNoIou],
                y=[tRule[tI] for tI in tNoIou],
                mode="markers",
                name="no ROI overlap",
                marker=dict(size=_SCATTER_MARKER_MIN_PX, color=_AI_VS_RULE_REF_COLOR, symbol="x"),
                hovertemplate="AI %{x:.1f}% / Rule %{y:.1f}% / no ROI overlap<extra></extra>",
            )
        )
    # Legend as a horizontal strip below the plot so it never collides with the
    # right-edge IoU colorbar (which otherwise overlaps the trace legend entries).
    tFig.update_layout(
        title="AI vs Rule per-class % (agreement) — MAE " + format(tMae, ".1f") + " pts",
        xaxis_title="ONNX ROI %",
        yaxis_title="Rule ROI %",
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5),
        margin=dict(l=8, r=8, t=44, b=56),
    )
    return tFig


def _iouSize(value):
    """Map a finite IoU in [0,1] to a marker size; non-finite -> minimum size."""
    tFinite = _finiteIou(value)
    if tFinite is None:
        return _SCATTER_MARKER_MIN_PX
    tClamped = min(max(tFinite, 0.0), 1.0)
    return _SCATTER_MARKER_MIN_PX + tClamped * (_SCATTER_MARKER_MAX_PX - _SCATTER_MARKER_MIN_PX)
