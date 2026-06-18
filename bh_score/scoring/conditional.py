"""Rule-ROI conditional scorer (Stream A). Produces the same ScoreResult contract as
the AI scorer; only the ROI source differs. The ROI is a morphology approximation of
the live beef rule-ROI seed (SCORING_SPEC §3 — NOT a faithful port of the 12-stage
GridBasedAlgorithm pipeline). Doneness reuses the shared frozen cascade, so the two
methods stay apples-to-apples.
"""
from __future__ import annotations

import cv2
import numpy as np

from bh_score.ingest.cube import FRAME_HEIGHT, FRAME_WIDTH
from bh_score.scoring import cascade, grades, kernel
from bh_score.scoring.base import Scorer
from bh_score.scoring.result import METHOD_CONDITIONAL
from bh_score.viz.palette import MONO_BACKGROUND_LED

# Bands the rule-ROI seed reads (ledId). All are gate/cascade inputs; a missing one
# must NOT be zero-filled (zero-fill makes the live gate pass everything).
_ROI_LED_V410 = 0
_ROI_LED_V440 = 1
_ROI_LED_V520 = 4
_ROI_LED_V650 = 8
_ROI_LED_V720 = 10
_ROI_LED_V930 = 14
_REQUIRED_ROI_LEDS = (
    _ROI_LED_V410,
    _ROI_LED_V440,
    _ROI_LED_V520,
    _ROI_LED_V650,
    _ROI_LED_V720,
    _ROI_LED_V930,
)

# Seed gate / branch thresholds, ported from the live recognizeROI (SCORING_SPEC §3).
_GATE_V410_MAX = 30
_GATE_V440_MAX = 30
_GATE_V930_MIN = 40
_GATE_V930_MAX = 140
_B1_V520_MIN = 60
_B1_V520_TO_V720 = 1.8
_B1_V440_TO_V520 = 2
_B1_V930_MIN = 100
_B2_V650_MAX = 80
_B2_V520_TO_V720 = 2.0
_B2_V520_MIN = 40
_B2_V520_MAX = 60
_B2_V520_TO_V930 = 2.2
_B2_V650_SLACK = 20
_B3_V650_MAX = 80
_B3_V520_TO_V720 = 2.5
_B3_V520_MAX = 40
_B3_V520_TO_V930 = 2

_SEED_ON = 255
# Morphology + component filtering (SCORING_SPEC §3).
_MORPH_KERNEL = (5, 5)
_TRAY_ZONE_START_COL = 560      # right ~80 cols are the tray; zeroed before components.
_MIN_COMPONENT_AREA = 500
_CC_CONNECTIVITY = 8
_CC_STATS_AREA_COL = cv2.CC_STAT_AREA

_INSTANCE_COUNT = 1


class ConditionalScorer(Scorer):
    """Scorer whose ROI is the morphology-approximated live beef rule seed."""

    def score(self, cube, capture):
        tRoiMask = self.ruleRoiMask(cube)
        if tRoiMask is None or not tRoiMask.any():
            return self._emptyResult(cube, capture, tRoiMask)

        tClassMap = cascade.classifyDonenessBeef(cube, tRoiMask)
        tResult = kernel.scoreFromClassMap(
            tRoiMask, tClassMap, capture.menu, METHOD_CONDITIONAL, _INSTANCE_COUNT
        )
        self._applyGrade(tResult, capture.menu)
        tResult.roi_mask = tRoiMask
        tResult.class_map = tClassMap
        tResult.mono_bg = cube.imageByLed(MONO_BACKGROUND_LED)
        return tResult

    def ruleRoiMask(self, cube):
        """Return the bool[H, W] rule ROI mask, or None if a required band is absent
        (zero-filling a gate band is forbidden — it would inflate the ROI)."""
        tBands = self._loadRequiredBands(cube)
        if tBands is None:
            return None

        v410 = tBands[_ROI_LED_V410]
        v440 = tBands[_ROI_LED_V440]
        v520 = tBands[_ROI_LED_V520]
        v650 = tBands[_ROI_LED_V650]
        v720 = tBands[_ROI_LED_V720]
        v930 = tBands[_ROI_LED_V930]

        gate = (v410 <= _GATE_V410_MAX) & (v440 <= _GATE_V440_MAX) \
            & (v930 > _GATE_V930_MIN) & (v930 < _GATE_V930_MAX)
        b1 = (v520 >= _B1_V520_MIN) & (v440 * _B1_V440_TO_V520 < v520) \
            & (v520 * _B1_V520_TO_V720 < v720) & (v930 > _B1_V930_MIN)
        b2 = (v650 < _B2_V650_MAX) & (v520 * _B2_V520_TO_V720 < v720) \
            & (v520 >= _B2_V520_MIN) & (v520 < _B2_V520_MAX) \
            & (v520 * _B2_V520_TO_V930 < v930) & (v520 >= v650 - _B2_V650_SLACK)
        b3 = (v650 < _B3_V650_MAX) & (v520 * _B3_V520_TO_V720 < v720) \
            & (v520 < _B3_V520_MAX) & (v520 * _B3_V520_TO_V930 < v930)

        tSeed = (gate & (b1 | b2 | b3)).astype(np.uint8) * _SEED_ON
        return self._refineSeed(tSeed)

    def _loadRequiredBands(self, cube):
        tBands = {}
        for tLed in _REQUIRED_ROI_LEDS:
            tImage = cube.imageByLed(tLed)
            if tImage is None:
                return None
            tBands[tLed] = tImage.astype(np.int32)
        return tBands

    def _refineSeed(self, seed):
        tKernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, _MORPH_KERNEL)
        tClosed = cv2.morphologyEx(seed, cv2.MORPH_CLOSE, tKernel)
        tOpened = cv2.morphologyEx(tClosed, cv2.MORPH_OPEN, tKernel)
        tOpened[:, _TRAY_ZONE_START_COL:] = 0
        return self._keepLargeComponents(tOpened)

    def _keepLargeComponents(self, mask):
        tCount, tLabels, tStats, _centroids = cv2.connectedComponentsWithStats(
            mask, connectivity=_CC_CONNECTIVITY
        )
        tKeep = np.zeros(mask.shape, dtype=bool)
        # Label 0 is the background component; skip it.
        for tLabel in range(1, tCount):
            tArea = int(tStats[tLabel, _CC_STATS_AREA_COL])
            if tArea >= _MIN_COMPONENT_AREA:
                tKeep[tLabels == tLabel] = True
        return tKeep

    def _applyGrade(self, result, menu):
        tGrade, tLabel = grades.gradeFor(
            menu,
            {
                "maillard_score": result.maillard_score,
                "slightly_burnt": result.pct_slightly_burnt,
                "burnt_score": result.pct_burnt_raw,
            },
        )
        result.grade = tGrade
        result.grade_label = tLabel

    def _emptyResult(self, cube, capture, roiMask):
        tShape = self._frameShape(cube, roiMask)
        tEmptyRoi = np.zeros(tShape, dtype=bool)
        tEmptyClassMap = np.zeros(tShape, dtype=np.uint8)
        tResult = kernel.scoreFromClassMap(
            tEmptyRoi, tEmptyClassMap, capture.menu, METHOD_CONDITIONAL, _INSTANCE_COUNT
        )
        self._applyGrade(tResult, capture.menu)
        tResult.roi_mask = tEmptyRoi
        tResult.class_map = tEmptyClassMap
        tResult.mono_bg = cube.imageByLed(MONO_BACKGROUND_LED)
        return tResult

    def _frameShape(self, cube, roiMask):
        if roiMask is not None:
            return roiMask.shape
        tMono = cube.imageByLed(MONO_BACKGROUND_LED)
        if tMono is not None:
            return tMono.shape
        return (FRAME_HEIGHT, FRAME_WIDTH)
