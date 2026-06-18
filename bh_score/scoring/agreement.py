"""ROI agreement metrics (Phase-0 FROZEN; SCORING_SPEC §7). With no ground truth
these measure AGREEMENT between the two ROI masks, never accuracy. Zero-union returns
a sentinel string, never NaN/inf — a NaN here would crash the hero scorecard on stage.
"""
from __future__ import annotations

import numpy as np

STRONG_AGREEMENT_IOU = 0.90
AGREEMENT_NOISE_EPS_PTS = 1.0
NOT_DONE_DOMINANT_PCT = 60.0
NO_OVERLAP_SENTINEL = "No overlapping ROI"


def agreementMetrics(onnxMask, ruleMask):
    """Return a dict: iou, dice, area_delta_px, onnx_px, rule_px, inter_px, union_px.
    iou/dice are floats, or NO_OVERLAP_SENTINEL when both masks are empty."""
    a = onnxMask.astype(bool)
    b = ruleMask.astype(bool)
    aSum = int(a.sum())
    bSum = int(b.sum())
    inter = int(np.count_nonzero(a & b))
    union = int(np.count_nonzero(a | b))
    areaDelta = aSum - bSum

    if union == 0 or (aSum + bSum) == 0:
        iou = NO_OVERLAP_SENTINEL
        dice = NO_OVERLAP_SENTINEL
    else:
        iou = inter / union
        dice = 2.0 * inter / (aSum + bSum)

    return {
        "iou": iou,
        "dice": dice,
        "area_delta_px": areaDelta,
        "onnx_px": aSum,
        "rule_px": bSum,
        "inter_px": inter,
        "union_px": union,
    }
