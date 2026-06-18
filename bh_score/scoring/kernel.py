"""DonenessKernel (Phase-0 FROZEN) — counts class_map pixels, applies the live
per-menu offset ONCE, and computes the comparison-fair maillard score. Pure arrays,
golden-tested. Both scorers funnel through this, so percentages are bit-identical for
identical (roi_mask, class_map) — the guarantee that the ROI-diff comparison is fair.

Live global values (verified):
  offset   burnt -3.0 / slightly -1.5 / proper -5.0   (0 floor, applied ONCE)
  maillard proper*0.7 + slightly*1.5 + burnt*3.0       (OnnxInferenceOutput.h:93-95)
Per-menu offset channel policy comes from bh_score.bands.OFFSET_CHANNELS (beef: all
three; pork: burnt only — ComponentRecognizer_PorkBelly_Charcoal:408-415).
"""
from __future__ import annotations

import numpy as np

from bh_score.bands import OFFSET_CHANNELS
from bh_score.scoring.result import (
    BURNT,
    NOT_DONE,
    PROPER,
    SLIGHTLY_BURNT,
    ScoreResult,
)

BURNT_OFFSET_PTS = 3.0
SLIGHTLY_OFFSET_PTS = 1.5
PROPER_OFFSET_PTS = 5.0
MAILLARD_W_PROPER = 0.7
MAILLARD_W_SLIGHTLY = 1.5
MAILLARD_W_BURNT = 3.0
# Default offset policy for menus without an explicit entry (beef rules approximate).
_DEFAULT_OFFSET_CHANNELS = ("burnt", "slightly_burnt", "proper")


def offsetChannelsFor(menu):
    """Resolve the offset channel policy: exact menu, then by meat prefix, then the
    beef default."""
    if menu in OFFSET_CHANNELS:
        return OFFSET_CHANNELS[menu]
    meat = menu.split("/", 1)[0]
    for key, channels in OFFSET_CHANNELS.items():
        if key.split("/", 1)[0] == meat:
            return channels
    return _DEFAULT_OFFSET_CHANNELS


def _offset(pctRaw, points, channel, channels):
    if channel in channels:
        return max(pctRaw - points, 0.0)
    return pctRaw


def scoreFromClassMap(roiMask, classMap, menu, method, instanceCount):
    """Build a ScoreResult from a doneness class_map. roiMask bool[H, W]; classMap
    uint8[H, W] in {0..4}. Empty ROI yields all-zero scores, never NaN."""
    pixelsRoi = int(np.count_nonzero(roiMask))
    roiDiv = max(pixelsRoi, 1)

    cntNotDone = int(np.count_nonzero(classMap == NOT_DONE))
    cntProper = int(np.count_nonzero(classMap == PROPER))
    cntSlightly = int(np.count_nonzero(classMap == SLIGHTLY_BURNT))
    cntBurnt = int(np.count_nonzero(classMap == BURNT))

    pctNotDone = cntNotDone * 100.0 / roiDiv
    pctProperRaw = cntProper * 100.0 / roiDiv
    pctSlightlyRaw = cntSlightly * 100.0 / roiDiv
    pctBurntRaw = cntBurnt * 100.0 / roiDiv

    channels = offsetChannelsFor(menu)
    pctBurnt = _offset(pctBurntRaw, BURNT_OFFSET_PTS, "burnt", channels)
    pctSlightly = _offset(pctSlightlyRaw, SLIGHTLY_OFFSET_PTS, "slightly_burnt", channels)
    pctProper = _offset(pctProperRaw, PROPER_OFFSET_PTS, "proper", channels)

    cookingScore = pctProper
    maillardScore = (pctProper * MAILLARD_W_PROPER
                     + pctSlightly * MAILLARD_W_SLIGHTLY
                     + pctBurnt * MAILLARD_W_BURNT)

    return ScoreResult(
        method=method,
        menu=menu,
        pixels_roi=pixelsRoi,
        pixels_not_done=cntNotDone,
        pixels_proper=cntProper,
        pixels_slightly_burnt=cntSlightly,
        pixels_burnt=cntBurnt,
        pct_proper=pctProper,
        pct_slightly_burnt=pctSlightly,
        pct_burnt=pctBurnt,
        pct_burnt_raw=pctBurntRaw,
        pct_not_done=pctNotDone,
        cooking_score=cookingScore,
        maillard_score=maillardScore,
        grade=-1,
        grade_label="",
        instance_count=instanceCount,
    )
