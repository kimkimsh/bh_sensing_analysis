"""Shared doneness cascade (Phase-0 FROZEN) — direct port of the live beef recognizer
ComponentRecognizer_BeefStripLoin_CharBroiler.h:112-158. Classifies every ROI pixel
into NOT_DONE / PROPER / SLIGHTLY_BURNT / BURNT via the spectral gate + cascade.

Both the ONNX-ROI scorer and the Rule-ROI scorer call this identical function, so the
comparison is apples-to-apples: only the ROI mask differs. Non-beef menus reuse this
beef cascade as a labelled approximation (the live engine also routes LAMB/CHICKEN to
the beef recognizer; PORK has its own cascade that is out of scope for v1).

Bands used (ledId): 410(0), 440(1), 520(4), 585(5), 650(8), 720(10), 930(14).
460(2)/800(11) are loaded by the live engine but unused by the cascade.
Priority is burnt > slightly > proper, matching the live else-if chain.
"""
from __future__ import annotations

import numpy as np

from bh_score.scoring.result import (
    BURNT,
    NOT_DONE,
    NOT_ROI,
    PROPER,
    SLIGHTLY_BURNT,
)


class MissingBandError(ValueError):
    """A band the cascade requires is absent. Substituting 0 is forbidden: the live
    gate (v410<=7 | v440<=7) would then pass every pixel and inflate the score."""


def _reqBand(cube, ledId):
    img = cube.imageByLed(ledId)
    if img is None:
        raise MissingBandError(f"cascade requires ledId {ledId}, which is absent")
    return img.astype(np.int32)


def classifyDonenessBeef(cube, roiMask):
    """Return class_map uint8[H, W] in {NOT_ROI, NOT_DONE, PROPER, SLIGHTLY_BURNT,
    BURNT}. roiMask is bool[H, W]; out-of-ROI pixels stay NOT_ROI."""
    v410 = _reqBand(cube, 0)
    v440 = _reqBand(cube, 1)
    v520 = _reqBand(cube, 4)
    v585 = _reqBand(cube, 5)
    v650 = _reqBand(cube, 8)
    v720 = _reqBand(cube, 10)
    v930 = _reqBand(cube, 14)

    gate = ((v410 <= 10) & (v440 <= 15)) | (v410 <= 7) | (v440 <= 7)
    burnt = gate & (v650 <= 30) & (v720 <= 40) & (v930 >= 50)
    slightly = gate & (v585 <= 20) & (v650 <= 40) & (v720 <= 60) & (v930 >= 50)
    properLean = gate & (v585 <= 25) & (v650 <= 50) & (v720 <= 80) & (v930 >= 50)
    properFat = gate & (v520 <= 30) & (v650 > 50) & (v930 >= 70) & (v720 > 70)
    proper = properLean | properFat

    inRoi = roiMask.astype(bool)
    classMap = np.full(inRoi.shape, NOT_ROI, dtype=np.uint8)
    classMap[inRoi] = NOT_DONE
    classMap[inRoi & proper] = PROPER
    classMap[inRoi & slightly] = SLIGHTLY_BURNT
    classMap[inRoi & burnt] = BURNT
    return classMap
