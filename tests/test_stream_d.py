"""Offline Stream D test — runs WITHOUT launching Streamlit.

Validates the pure viz functions on synthetic data (hero has cyan AND vermilion
pixels from a partial-overlap mask pair, mask overlay returns RGB, every chart
returns a Plotly Figure) and byte-compiles app/dashboard.py for syntax errors.
"""
import os
import py_compile
import sys

import numpy as np
import plotly.graph_objects as go
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bh_score.scoring import result as scoreResult
from bh_score.viz import charts, overlay, palette


def _hexToRgb(hexStr):
    tHex = hexStr.lstrip("#")
    return (int(tHex[0:2], 16), int(tHex[2:4], 16), int(tHex[4:6], 16))


def _colorPresent(rgbImage, rgbColor, tolerance):
    tDiff = np.abs(rgbImage.astype(np.int32) - np.array(rgbColor, dtype=np.int32))
    tMatch = np.all(tDiff <= tolerance, axis=-1)
    return bool(tMatch.any())


def _synthMasks(h, w):
    tOnnx = np.zeros((h, w), dtype=bool)
    tRule = np.zeros((h, w), dtype=bool)
    # Two overlapping rectangles -> both / onnx_only / rule_only all non-empty.
    tOnnx[60:300, 80:360] = True
    tRule[160:400, 200:520] = True
    return tOnnx, tRule


def testRoiDiffHero():
    tH, tW = 480, 640
    tMono = (np.random.default_rng(0).integers(0, 200, size=(tH, tW))).astype(np.uint8)
    tOnnx, tRule = _synthMasks(tH, tW)
    tHero = overlay.renderRoiDiffHero(tMono, tOnnx, tRule)

    assert tHero.shape == (tH, tW, 3), "hero shape mismatch: " + str(tHero.shape)
    assert tHero.dtype == np.uint8, "hero dtype mismatch: " + str(tHero.dtype)

    tCyan = _hexToRgb(palette.ROI_DIFF["ONNX_ONLY"]["hex"])
    tVermilion = _hexToRgb(palette.ROI_DIFF["RULE_ONLY"]["hex"])
    # Contours are drawn at full color -> exact-ish match expected; allow blend tol.
    assert _colorPresent(tHero, tCyan, 60), "cyan (AI-only) pixels missing from hero"
    assert _colorPresent(tHero, tVermilion, 60), "vermilion (Rule-only) pixels missing from hero"
    print("PASS testRoiDiffHero — hero is HxWx3 uint8 with cyan AND vermilion present")


def testMaskOverlay():
    tH, tW = 480, 640
    tMono = (np.random.default_rng(1).integers(0, 200, size=(tH, tW))).astype(np.uint8)
    tRoi = np.zeros((tH, tW), dtype=bool)
    tRoi[100:300, 100:400] = True
    tClass = np.zeros((tH, tW), dtype=np.uint8)
    tClass[100:160, 100:400] = scoreResult.PROPER
    tClass[160:220, 100:400] = scoreResult.SLIGHTLY_BURNT
    tClass[220:300, 100:400] = scoreResult.BURNT
    tOverlay = overlay.renderMaskOverlay(tMono, tRoi, tClass)
    assert tOverlay.shape == (tH, tW, 3), "mask overlay shape mismatch"
    assert tOverlay.dtype == np.uint8, "mask overlay dtype mismatch"
    print("PASS testMaskOverlay — returns HxWx3 uint8")


def testCharts():
    tPanelCounts = {
        "AI ROI": {"NOT_DONE": 1200, "PROPER": 800, "SLIGHTLY_BURNT": 300, "BURNT": 120},
        "Rule ROI": {"NOT_DONE": 1500, "PROPER": 600, "SLIGHTLY_BURNT": 250, "BURNT": 90},
    }
    tBar = charts.fourWayStackedBar(tPanelCounts)
    assert isinstance(tBar, go.Figure), "fourWayStackedBar did not return a Figure"

    tDateDf = pd.DataFrame(
        {
            "capture_date": ["2025-09-01", "2025-09-02", "2025-09-01", "2025-09-02"],
            "method": ["ai", "ai", "conditional", "conditional"],
            "class": ["BURNT", "BURNT", "BURNT", "BURNT"],
            "pct_value": [12.0, 14.5, 10.0, 13.0],
        }
    )
    tLines = charts.byDateLines(tDateDf)
    assert isinstance(tLines, go.Figure), "byDateLines did not return a Figure"

    tMenuDf = pd.DataFrame(
        {
            "menu": ["beef/striploin", "beef/striploin", "pork/belly", "pork/belly"],
            "method": ["ai", "conditional", "ai", "conditional"],
            "value": [22.0, 18.0, 15.0, 17.0],
        }
    )
    tBars = charts.byMenuBars(tMenuDf)
    assert isinstance(tBars, go.Figure), "byMenuBars did not return a Figure"

    tScatterDf = pd.DataFrame(
        {
            "onnx_pct": [12.0, 18.0, 25.0],
            "rule_pct": [10.0, 19.0, 22.0],
            "iou": [0.91, 0.82, 0.95],
        }
    )
    tScatter = charts.aiVsRuleScatter(tScatterDf)
    assert isinstance(tScatter, go.Figure), "aiVsRuleScatter did not return a Figure"

    # Empty-data guards must not crash.
    for tFn in (charts.byDateLines, charts.byMenuBars, charts.aiVsRuleScatter):
        assert isinstance(tFn(pd.DataFrame()), go.Figure), "empty-df guard failed"

    print("PASS testCharts — all four chart builders return Plotly Figures (incl. empty-df guards)")


def testDashboardCompiles():
    tPath = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "dashboard.py"
    )
    py_compile.compile(tPath, doraise=True)
    print("PASS testDashboardCompiles — app/dashboard.py byte-compiles (no syntax errors)")


def main():
    testRoiDiffHero()
    testMaskOverlay()
    testCharts()
    testDashboardCompiles()
    print("ALL STREAM-D TESTS PASSED")


if __name__ == "__main__":
    main()
