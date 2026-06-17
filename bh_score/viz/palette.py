"""Color constants for bh_sensing_analysis (DESIGN_SPEC §3, Phase-0 FROZEN).

Three DISJOINT color spaces that must never be mixed: a viewer who sees the
"burnt" red of the doneness ramp inside the ROI-diff hero would confuse it with
the "Rule-only" region. Shared by Stream B (AI overlay) and Stream D (Rule
overlay + charts + hero) so the legend cannot drift between methods.

  1. MASK     — faithful C++ OnnxVisualization overlay (the only place the
                green/yellow/red ramp survives, because it ports the live engine).
  2. CHART    — CVD-safe, lightness-ordered doneness ramp for every Plotly chart
                and legend; mirrored in .streamlit/config.toml chartCategoricalColors.
  3. ROI_DIFF — the hero overlap-map (source disagreement, NOT doneness).
"""

# 1. MASK palette — faithful port of OnnxVisualization (verified BGR tuples).
#    Doneness pixel priority: burnt > slightly > proper > class color.
MASK_CLASS_BGR = {
    "BEEF": (173, 72, 0),
    "CHICKEN": (34, 120, 236),
    "LAMB": (220, 220, 220),
    "PORK": (220, 160, 230),
}
MASK_DONENESS_BGR = {
    "PROPER": (11, 238, 34),
    "SLIGHTLY_BURNT": (0, 200, 255),
    "BURNT": (0, 5, 255),
}
MASK_CLASS_ALPHA = 0.45
MASK_DONENESS_ALPHA = 0.30
MONO_BACKGROUND_LED = 10  # ch3 / led10 (peak 740) — grayscale background for all overlays

# 2. CHART palette — CVD-safe, ordered by MONOTONIC LIGHTNESS so the order survives
#    both grayscale projection and deuteranopia. Hex order MUST equal config.toml
#    chartCategoricalColors. NOT_DONE is a neutral grey so the dominant gate-failed
#    bucket recedes instead of grabbing attention. Redundant (non-color) encoding is
#    mandatory: a letter chip AND a Plotly pattern_shape per level (WCAG 1.4.1).
DONENESS_ORDER = ("NOT_DONE", "PROPER", "SLIGHTLY_BURNT", "BURNT")
DONENESS_RAMP_HEX = {
    "NOT_DONE": "#9AA0AC",        # neutral grey — dominant bucket recedes
    "PROPER": "#1B9E77",
    "SLIGHTLY_BURNT": "#E69F00",
    "BURNT": "#7A2200",           # darkest — keeps the "char" semantic
}
DONENESS_CHIP = {
    "NOT_DONE": "ND",
    "PROPER": "P",
    "SLIGHTLY_BURNT": "S",
    "BURNT": "B",
}
DONENESS_PATTERN = {
    "NOT_DONE": ".",
    "PROPER": "",
    "SLIGHTLY_BURNT": "/",
    "BURNT": "x",
}
# Convenience list in canonical order for Plotly color_discrete_sequence parity.
CHART_CATEGORICAL_COLORS = [DONENESS_RAMP_HEX[k] for k in DONENESS_ORDER]

# 3. ROI_DIFF palette — the hero overlap-map. Source disagreement, not doneness.
#    Okabe-Ito cyan/vermilion are a colorblind-safe pair.
ROI_DIFF = {
    "BOTH": {"hex": "#5A5A5A", "alpha": 0.18, "contour": None},        # both methods agree
    "ONNX_ONLY": {"hex": "#56B4E9", "alpha": 0.45, "contour": "solid"},
    "RULE_ONLY": {"hex": "#D55E00", "alpha": 0.45, "contour": "dashed"},  # hatched fill
}
ROI_DIFF_CONTOUR_PX = 2
